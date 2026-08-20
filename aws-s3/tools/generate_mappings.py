#!/usr/bin/env python3
"""Generate language-neutral S3 and boto3 Runtime Conditions mappings.

The AWS service model supplies the operation inventory and input shapes. The
small semantic-annotation file supplies the Runtime Conditions decisions that
cannot be inferred safely from the service model alone.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any


EXTENSION_ID = "https://runtimeconditions.io/extensions/aws-s3/v1alpha1/runtimeconditions.extension.yaml"


def read_json(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def operation_fingerprint(names: list[str]) -> str:
    payload = "\n".join(names) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def python_name(name: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def input_members(model: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    input_name = operation.get("input", {}).get("shape", "")
    return model.get("shapes", {}).get(input_name, {}).get("members", {})


def validate_input_path(
    model: dict[str, Any], operation_name: str, operation: dict[str, Any], path: str
) -> None:
    shape_name = operation.get("input", {}).get("shape", "")
    for segment in path.split("."):
        is_list = segment.endswith("[]")
        member_name = segment[:-2] if is_list else segment
        shape = model.get("shapes", {}).get(shape_name, {})
        member = shape.get("members", {}).get(member_name)
        if member is None:
            raise ValueError(f"{operation_name}: input path {path!r} does not resolve at {member_name!r}")
        shape_name = member.get("shape", "")
        if is_list:
            list_shape = model.get("shapes", {}).get(shape_name, {})
            if list_shape.get("type") != "list":
                raise ValueError(f"{operation_name}: input path {path!r} marks non-list {member_name!r} as a list")
            shape_name = list_shape.get("member", {}).get("shape", "")


def primary_condition(
    operation_name: str,
    operation: dict[str, Any],
    model: dict[str, Any],
    annotations: dict[str, Any],
) -> dict[str, Any]:
    override = annotations["scopeOverrides"].get(operation_name)
    if override:
        condition: dict[str, Any] = {
            "kind": "aws.s3",
            "interfaceType": override["interfaceType"],
            "operation": {"name": operation_name},
        }
        if override.get("identityPath"):
            validate_input_path(model, operation_name, operation, override["identityPath"])
            condition["identity"] = {"source": "input", "path": override["identityPath"]}
        return condition

    default = annotations["defaultBucketCondition"]
    if default["whenInputContains"] not in input_members(model, operation):
        raise ValueError(f"{operation_name}: no scope override and no modeled Bucket input")
    condition = {
        "kind": default["kind"],
        "interfaceType": default["interfaceType"],
        "identity": {"source": "input", "path": default["identityPath"]},
        "operation": {"name": operation_name},
    }
    validate_input_path(model, operation_name, operation, default["identityPath"])
    role = annotations.get("primaryOperationRoles", {}).get(operation_name)
    if role:
        condition["operation"]["role"] = role
    return condition


def secondary_conditions(
    operation_name: str,
    operation: dict[str, Any],
    model: dict[str, Any],
    annotations: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in annotations.get("secondaryBucketConditions", {}).get(operation_name, []):
        validate_input_path(model, operation_name, operation, item["identityPath"])
        identity = {"source": "input", "path": item["identityPath"]}
        if item.get("identityEncoding"):
            identity["encoding"] = item["identityEncoding"]
        result.append(
            {
                "kind": "aws.s3",
                "interfaceType": "bucket",
                "identity": identity,
                "operation": {"name": operation_name, "role": item["operationRole"]},
                "conditional": True,
            }
        )
    return result


def validate_model(model: dict[str, Any], annotations: dict[str, Any]) -> list[str]:
    metadata = model.get("metadata", {})
    names = sorted(model.get("operations", {}))
    checks = {
        "serviceId": (metadata.get("serviceId"), annotations["expectedServiceId"]),
        "apiVersion": (metadata.get("apiVersion"), annotations["expectedApiVersion"]),
        "operation count": (len(names), annotations["expectedOperationCount"]),
        "operation fingerprint": (
            operation_fingerprint(names),
            annotations["expectedOperationNamesSha256"],
        ),
    }
    failures = [f"{label}: got {actual!r}, expected {expected!r}" for label, (actual, expected) in checks.items() if actual != expected]
    if failures:
        raise ValueError("service model changed; review it before regenerating:\n" + "\n".join(failures))
    annotated_operations = set(annotations["scopeOverrides"])
    annotated_operations.update(annotations.get("primaryOperationRoles", {}))
    annotated_operations.update(annotations.get("secondaryBucketConditions", {}))
    unknown = sorted(annotated_operations - set(names))
    if unknown:
        raise ValueError(f"semantic annotations reference unknown operations: {', '.join(unknown)}")
    return names


def service_mapping(model: dict[str, Any], annotations: dict[str, Any]) -> dict[str, Any]:
    names = validate_model(model, annotations)
    operations = []
    for name in names:
        operation = model["operations"][name]
        conditions = [primary_condition(name, operation, model, annotations)]
        conditions.extend(secondary_conditions(name, operation, model, annotations))
        operations.append({"name": name, "conditions": conditions})
    metadata = model["metadata"]
    return {
        "apiVersion": "runtimeconditions.io/v1alpha1",
        "kind": "RuntimeConditionsServiceMappingCandidate",
        "metadata": {
            "service": annotations["service"],
            "serviceId": metadata["serviceId"],
            "apiVersion": metadata["apiVersion"],
            "sourceModelUid": metadata.get("uid", ""),
            "operationNamesSha256": operation_fingerprint(names),
        },
        "extension": {"id": EXTENSION_ID},
        "operations": operations,
    }


def resource_actions(resource_model: dict[str, Any] | None) -> list[dict[str, str]]:
    if not resource_model:
        return []
    result: list[dict[str, str]] = []
    for resource_name, resource in sorted(resource_model.get("resources", {}).items()):
        for group in ("actions", "batchActions"):
            for action_name, action in sorted(resource.get(group, {}).items()):
                operation = action.get("request", {}).get("operation")
                if operation:
                    result.append(
                        {
                            "resource": resource_name,
                            "action": action_name,
                            "method": python_name(action_name),
                            "actionType": group,
                            "canonicalOperation": operation,
                        }
                    )
    for action_name, action in sorted(resource_model.get("service", {}).get("actions", {}).items()):
        operation = action.get("request", {}).get("operation")
        if operation:
            result.append(
                {
                    "resource": "ServiceResource",
                    "action": action_name,
                    "method": python_name(action_name),
                    "actionType": "actions",
                    "canonicalOperation": operation,
                }
            )
    return result


def boto3_mapping(
    mapping: dict[str, Any],
    boto3_version: str,
    botocore_version: str,
    resources: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "apiVersion": "runtimeconditions.io/v1alpha1",
        "kind": "RuntimeConditionsSDKMappingCandidate",
        "metadata": {
            "sdk": "boto3",
            "language": "python",
            "boto3Version": boto3_version,
            "botocoreVersion": botocore_version,
            "service": "s3",
            "generatedFromOperationNamesSha256": mapping["metadata"]["operationNamesSha256"],
        },
        "extension": mapping["extension"],
        "python": {
            "package": "boto3",
            "clientFactories": [
                {"symbol": "boto3.client", "serviceNameArgument": 0, "serviceName": "s3"},
                {
                    "symbol": "boto3.session.Session.client",
                    "serviceNameArgument": 0,
                    "serviceName": "s3",
                },
            ],
            "clientOperations": [
                {
                    "method": python_name(operation["name"]),
                    "canonicalOperation": operation["name"],
                    "conditions": operation["conditions"],
                }
                for operation in mapping["operations"]
            ],
            "resourceActions": resource_actions(resources),
        },
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-model", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--resource-model", type=Path)
    parser.add_argument("--service-output", type=Path, required=True)
    parser.add_argument("--boto3-output", type=Path)
    parser.add_argument("--boto3-version")
    parser.add_argument("--botocore-version")
    args = parser.parse_args()

    model = read_json(args.service_model)
    annotations = read_json(args.annotations)
    resources = read_json(args.resource_model) if args.resource_model else None
    service = service_mapping(model, annotations)
    write_json(args.service_output, service)
    if args.boto3_output:
        if not args.boto3_version or not args.botocore_version:
            parser.error("--boto3-output requires --boto3-version and --botocore-version")
        boto3 = boto3_mapping(service, args.boto3_version, args.botocore_version, resources)
        write_json(args.boto3_output, boto3)


if __name__ == "__main__":
    main()

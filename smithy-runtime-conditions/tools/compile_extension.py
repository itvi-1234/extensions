#!/usr/bin/env python3
"""Compile a Runtime Conditions extension from an authoritative Smithy model and reviewed YAML overlays."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from serialization import read_document, write_yaml


SERVICE_TRAIT = "runtimeconditions.smithy#serviceSemantics"
OPERATION_TRAIT = "runtimeconditions.smithy#operationSemantics"
SERVICE_MAPPING_API_VERSION = "runtimeconditions.io/service-mapping/v1alpha1"
SERVICE_MAPPING_KIND = "RuntimeConditionsServiceMapping"
EXTENSION_API_VERSION = "runtimeconditions.io/v1alpha1"
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


class ModelDrift(RuntimeError):
    def __init__(self, message: str, operation_names: List[str]) -> None:
        super().__init__(message)
        self.operation_names = operation_names


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def semantic_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def operation_fingerprint(names: Iterable[str]) -> str:
    return sha256_bytes(("\n".join(names) + "\n").encode("utf-8"))


def shape_name(shape_id: str) -> str:
    return shape_id.rsplit("#", 1)[-1]


def merge_overlays(model: Dict[str, Any], overlays: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    source_shapes = model.get("shapes", {})
    if not isinstance(source_shapes, dict):
        raise ValueError("Smithy model shapes must be an object")
    merged = json.loads(json.dumps(source_shapes))
    trait_definitions: Dict[str, Any] = {}
    for overlay in overlays:
        if str(overlay.get("smithy", "")).split(".", 1)[0] != str(model.get("smithy", "")).split(".", 1)[0]:
            raise ValueError("Smithy model and overlay major versions do not match")
        for target, value in overlay.get("shapes", {}).items():
            if value.get("type") == "apply":
                if target not in merged:
                    raise ValueError(f"overlay applies traits to unknown shape {target}")
                traits = merged[target].setdefault("traits", {})
                for trait, trait_value in value.get("traits", {}).items():
                    if trait in traits and traits[trait] != trait_value:
                        raise ValueError(f"conflicting trait {trait} on {target}")
                    traits[trait] = trait_value
            else:
                if target in merged and merged[target] != value:
                    raise ValueError(f"overlay redefines source shape {target}")
                trait_definitions[target] = value
    for trait in (SERVICE_TRAIT, OPERATION_TRAIT):
        definition = trait_definitions.get(trait)
        if not definition or "smithy.api#trait" not in definition.get("traits", {}):
            raise ValueError(f"missing Smithy trait definition {trait}")
    return merged, trait_definitions


def service_operation_ids(service: Dict[str, Any]) -> List[str]:
    operation_ids = [item.get("target") for item in service.get("operations", [])]
    if not operation_ids or any(not isinstance(item, str) for item in operation_ids):
        raise ValueError("selected Smithy service does not declare an operation closure")
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("selected Smithy service contains duplicate operation references")
    return sorted(operation_ids, key=shape_name)


def validate_identity_path(shapes: Dict[str, Any], operation_id: str, path: str) -> None:
    operation = shapes[operation_id]
    shape_id = operation.get("input", {}).get("target")
    if not shape_id:
        raise ValueError(f"{shape_name(operation_id)}: identity path {path!r} requires an operation input")
    for segment in path.split("."):
        is_list = segment.endswith("[]")
        member_name = segment[:-2] if is_list else segment
        shape = shapes.get(shape_id)
        if not shape or shape.get("type") != "structure":
            raise ValueError(f"{shape_name(operation_id)}: identity path {path!r} reached non-structure {shape_id}")
        member = shape.get("members", {}).get(member_name)
        if not member:
            raise ValueError(f"{shape_name(operation_id)}: identity path {path!r} does not resolve at {member_name!r}")
        shape_id = member.get("target")
        if is_list:
            list_shape = shapes.get(shape_id)
            if not list_shape or list_shape.get("type") != "list":
                raise ValueError(f"{shape_name(operation_id)}: identity path {path!r} marks non-list {member_name!r} as a list")
            shape_id = list_shape.get("member", {}).get("target")


def condition_template(
    shapes: Dict[str, Any],
    operation_id: str,
    operation_name: str,
    kind: str,
    source: Dict[str, Any],
    additional: bool,
) -> Dict[str, Any]:
    interface_type = source.get("interfaceType")
    if not isinstance(interface_type, str) or not interface_type:
        raise ValueError(f"{operation_name}: Condition template requires interfaceType")
    result: Dict[str, Any] = {
        "kind": kind,
        "interfaceType": interface_type,
        "operation": {"name": operation_name},
    }
    identity_path = source.get("identityPath")
    if identity_path is not None:
        if not isinstance(identity_path, str) or not identity_path:
            raise ValueError(f"{operation_name}: identityPath must be a non-empty string")
        validate_identity_path(shapes, operation_id, identity_path)
        identity: Dict[str, Any] = {"source": "input", "path": identity_path}
        if source.get("identityEncoding"):
            identity["encoding"] = source["identityEncoding"]
        result["identity"] = identity
    elif source.get("identityEncoding"):
        raise ValueError(f"{operation_name}: identityEncoding requires identityPath")
    if source.get("operationRole"):
        result["operation"]["role"] = source["operationRole"]
    if additional or source.get("conditional"):
        result["conditional"] = True
    return result


def build_operations(
    shapes: Dict[str, Any], service: Dict[str, Any], semantics: Dict[str, Any]
) -> List[Dict[str, Any]]:
    operation_ids = service_operation_ids(service)
    names = [shape_name(item) for item in operation_ids]
    expected_count = semantics.get("reviewedOperationCount")
    expected_digest = semantics.get("reviewedOperationNamesSha256")
    actual_digest = operation_fingerprint(names)
    if len(names) != expected_count or actual_digest != expected_digest:
        raise ModelDrift(
            f"authoritative operation set changed: got {len(names)} operations and {actual_digest}; reviewed overlay expects {expected_count} and {expected_digest}",
            names,
        )
    known = set(operation_ids)
    annotated = {
        shape_id
        for shape_id, shape in shapes.items()
        if OPERATION_TRAIT in shape.get("traits", {})
    }
    unknown = sorted(annotated - known)
    if unknown:
        raise ValueError(f"operation semantics target shapes outside the service closure: {', '.join(unknown)}")
    default_condition = semantics.get("defaultCondition")
    if not isinstance(default_condition, dict):
        raise ValueError("service semantics require defaultCondition")
    kind = semantics.get("conditionKind")
    if not isinstance(kind, str) or not kind:
        raise ValueError("service semantics require conditionKind")
    result = []
    for operation_id in operation_ids:
        operation_name = shape_name(operation_id)
        operation_semantics = shapes[operation_id].get("traits", {}).get(OPERATION_TRAIT, {})
        primary = operation_semantics.get("primaryCondition", default_condition)
        conditions = [condition_template(shapes, operation_id, operation_name, kind, primary, False)]
        for additional in operation_semantics.get("additionalConditions", []):
            conditions.append(condition_template(shapes, operation_id, operation_name, kind, additional, True))
        result.append({"name": operation_name, "shapeId": operation_id, "conditions": conditions})
    return result


def interface_inventory(operations: List[Dict[str, Any]]) -> "OrderedDict[str, Dict[str, Any]]":
    inventory: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for operation in operations:
        for condition in operation["conditions"]:
            interface_type = condition["interfaceType"]
            current = inventory.setdefault(interface_type, {"operations": set(), "roles": set()})
            current["operations"].add(operation["name"])
            role = condition.get("operation", {}).get("role")
            if role:
                current["roles"].add(role)
    return inventory


def operation_schema(
    kind: str,
    interface_type: str,
    operation_variants: Dict[str, Dict[str, Any]],
    display_name: str,
) -> Dict[str, Any]:
    item_variants = []
    for operation_name, variant in operation_variants.items():
        properties: Dict[str, Any] = {"name": {"const": operation_name}}
        required = ["name"]
        roles = variant["roles"]
        if roles:
            properties["role"] = {"enum": roles}
            if not variant["allowsNoRole"]:
                required.append("role")
        item_variants.append(
            {
                "type": "object",
                "required": required,
                "properties": properties,
                "additionalProperties": False,
            }
        )
    return {
        "id": f"{kind.replace('.', '-')}-{interface_type.replace('_', '-')}-interface",
        "appliesToKind": kind,
        "appliesToInterfaceType": interface_type,
        "description": f"Validates a {display_name} {interface_type.replace('_', ' ')} requirement and its canonical API operations.",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["kind", "interface"],
            "properties": {
                "kind": {"const": kind},
                "interface": {
                    "type": "object",
                    "required": ["type", "operations"],
                    "properties": {
                        "type": {"const": interface_type},
                        "operations": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"oneOf": item_variants},
                        },
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
    }


def build_extension_spec(semantics: Dict[str, Any], operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    kind = semantics["conditionKind"]
    display_name = semantics["displayName"]
    inventory = interface_inventory(operations)
    interface_types = list(inventory)
    field_values: List[Dict[str, Any]] = []
    schemas: List[Dict[str, Any]] = []
    for interface_type, values in inventory.items():
        operation_names = sorted(values["operations"])
        roles = sorted(values["roles"])
        operation_variants: Dict[str, Dict[str, Any]] = OrderedDict()
        for operation in operations:
            relevant = [condition for condition in operation["conditions"] if condition["interfaceType"] == interface_type]
            if not relevant:
                continue
            operation_roles = sorted(
                {
                    condition["operation"]["role"]
                    for condition in relevant
                    if "role" in condition["operation"]
                }
            )
            operation_variants[operation["name"]] = {
                "roles": operation_roles,
                "allowsNoRole": any("role" not in condition["operation"] for condition in relevant),
            }
        field_values.append(
            {
                "field": "interface.operations[].name",
                "targetKind": kind,
                "targetType": interface_type,
                "values": operation_names,
            }
        )
        if roles:
            field_values.append(
                {
                    "field": "interface.operations[].role",
                    "targetKind": kind,
                    "targetType": interface_type,
                    "values": roles,
                }
            )
        schemas.append(operation_schema(kind, interface_type, operation_variants, display_name))
    return {
        "kinds": [{"name": kind}],
        "interfaceTypes": [{"name": item, "targetKind": kind} for item in interface_types],
        "interfaceFields": [
            {"name": "operations", "targetKind": kind, "targetType": item}
            for item in interface_types
        ],
        "fieldValues": field_values,
        "schemas": schemas,
    }


def build_outputs(
    model_path: Path,
    source_repository: str,
    source_revision: str,
    source_path: str,
    service_shape: str,
    shapes: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    service = shapes.get(service_shape)
    if not service or service.get("type") != "service":
        raise ValueError(f"selected shape is not a Smithy service: {service_shape}")
    semantics = service.get("traits", {}).get(SERVICE_TRAIT)
    if not isinstance(semantics, dict):
        raise ValueError(f"selected service does not carry {SERVICE_TRAIT}")
    version = semantics.get("extensionVersion")
    extension_id = semantics.get("extensionId")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValueError(f"invalid extension semantic version: {version!r}")
    if not isinstance(extension_id, str) or f"/{version}/" not in extension_id:
        raise ValueError("extensionId must contain the exact extensionVersion as a path segment")
    try:
        operations = build_operations(shapes, service, semantics)
    except ModelDrift:
        raise
    except ValueError as error:
        names = [shape_name(item) for item in service_operation_ids(service)]
        raise ModelDrift(
            "authoritative model no longer satisfies the reviewed Runtime Conditions semantics: "
            + str(error),
            names,
        ) from error
    spec = build_extension_spec(semantics, operations)
    spec_digest = semantic_sha256(spec)
    model_digest = sha256_file(model_path)
    provenance = {
        "repository": source_repository,
        "revision": source_revision,
        "path": source_path,
        "sha256": model_digest,
        "smithyVersion": "2.0",
        "serviceShape": service_shape,
        "serviceVersion": service.get("version"),
    }
    extension = {
        "apiVersion": EXTENSION_API_VERSION,
        "kind": "RuntimeConditionsExtensionDefinition",
        "metadata": {
            "id": extension_id,
            "version": version,
            "semanticSha256": spec_digest,
            "provenance": provenance,
        },
        "spec": spec,
    }
    service_trait = service.get("traits", {}).get("aws.api#service", {})
    names = [item["name"] for item in operations]
    mapping_operations = [
        {"name": item["name"], "shapeId": item["shapeId"], "conditions": item["conditions"]}
        for item in operations
    ]
    mapping = {
        "apiVersion": SERVICE_MAPPING_API_VERSION,
        "kind": SERVICE_MAPPING_KIND,
        "metadata": {
            "name": f"aws.{semantics['serviceKey']}",
            "service": semantics["serviceKey"],
            "serviceId": service_trait.get("sdkId", shape_name(service_shape)),
            "serviceShape": service_shape,
            "serviceVersion": service.get("version"),
            "operationCount": len(names),
            "operationNamesSha256": operation_fingerprint(names),
            "semanticSha256": semantic_sha256(mapping_operations),
            "source": provenance,
        },
        "extension": {
            "id": extension_id,
            "version": version,
            "semanticSha256": spec_digest,
        },
        "operations": mapping_operations,
    }
    return extension, mapping, semantics


def baseline_operations(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    return {item["name"]: item for item in read_document(path).get("operations", [])}


def review_markdown(
    classification: str,
    message: str,
    source_repository: str,
    source_revision: str,
    source_path: str,
    model_digest: str,
    operation_names: List[str],
    baseline: Dict[str, Any],
    extension: Optional[Dict[str, Any]] = None,
    mapping: Optional[Dict[str, Any]] = None,
) -> str:
    current = set(operation_names)
    previous = set(baseline)
    added = sorted(current - previous) if baseline else []
    removed = sorted(previous - current) if baseline else []
    lines = [
        "# Smithy extension maintenance review",
        "",
        f"**Classification: `{classification}`**",
        "",
        message,
        "",
        "## Authoritative input",
        "",
        f"- Repository: `{source_repository}`",
        f"- Revision: `{source_revision}`",
        f"- Path: `{source_path}`",
        f"- SHA-256: `{model_digest}`",
        f"- Canonical operations: {len(operation_names)}",
        f"- Operation-name SHA-256: `{operation_fingerprint(operation_names)}`",
    ]
    if extension and mapping:
        inventory = interface_inventory(mapping["operations"])
        lines.extend(
            [
                "",
                "## Generated semantic release",
                "",
                f"- Extension: `{extension['metadata']['id']}`",
                f"- Extension version: `{extension['metadata']['version']}`",
                f"- Extension semantic SHA-256: `{extension['metadata']['semanticSha256']}`",
                f"- Service-mapping semantic SHA-256: `{mapping['metadata']['semanticSha256']}`",
                "",
                "## Interface inventory",
                "",
                "| Interface | Operations | Roles |",
                "| --- | ---: | --- |",
            ]
        )
        for interface_type, values in inventory.items():
            roles = ", ".join(sorted(values["roles"])) or "none"
            lines.append(f"| `{interface_type}` | {len(values['operations'])} | {roles} |")
    if baseline:
        lines.extend(["", "## Operation-set change", ""])
        lines.append(f"- Added: {', '.join(f'`{item}`' for item in added) if added else 'none'}")
        lines.append(f"- Removed: {', '.join(f'`{item}`' for item in removed) if removed else 'none'}")
    lines.extend(
        [
            "",
            "## Maintainer decision",
            "",
            "Review only changes to operation classification, resource identity paths, roles, cross-service dependencies, and representative profile meaning. Generated extension and mapping artifacts are machine review output, not line-by-line human review surfaces.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--traits", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, action="append", required=True)
    parser.add_argument("--service-shape", required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--extension-output", type=Path, required=True)
    parser.add_argument("--service-mapping-output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
    parser.add_argument("--baseline-service-mapping", type=Path)
    args = parser.parse_args()

    model = read_document(args.model)
    overlay_documents = [read_document(args.traits)] + [read_document(path) for path in args.overlay]
    shapes, _ = merge_overlays(model, overlay_documents)
    baseline = baseline_operations(args.baseline_service_mapping)
    model_digest = sha256_file(args.model)
    try:
        extension, mapping, _ = build_outputs(
            args.model,
            args.source_repository,
            args.source_revision,
            args.source_path,
            args.service_shape,
            shapes,
        )
    except ModelDrift as error:
        args.review_output.parent.mkdir(parents=True, exist_ok=True)
        args.review_output.write_text(
            review_markdown(
                "extension-review-required",
                str(error),
                args.source_repository,
                args.source_revision,
                args.source_path,
                model_digest,
                error.operation_names,
                baseline,
            ),
            encoding="utf-8",
        )
        print(f"classification: extension-review-required", file=sys.stderr)
        print(error, file=sys.stderr)
        return 2
    write_yaml(args.extension_output, extension)
    write_yaml(args.service_mapping_output, mapping)
    names = [item["name"] for item in mapping["operations"]]
    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.write_text(
        review_markdown(
            "automatic",
            "The authoritative Smithy operation inventory matches the reviewed Runtime Conditions overlay, and deterministic extension and service-mapping artifacts were generated successfully.",
            args.source_repository,
            args.source_revision,
            args.source_path,
            model_digest,
            names,
            baseline,
            extension,
            mapping,
        ),
        encoding="utf-8",
    )
    print("classification: automatic")
    print(f"extension: {extension['metadata']['id']}")
    print(f"canonical operations: {len(names)}")
    print(f"extension semantic sha256: {extension['metadata']['semanticSha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

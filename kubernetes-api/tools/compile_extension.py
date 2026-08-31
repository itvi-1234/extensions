#!/usr/bin/env python3
"""Compile the Kubernetes API extension release and language-neutral service mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from serialization import read_document, write_yaml


EXTENSION_API_VERSION = "runtimeconditions.io/v1alpha1"
SERVICE_MAPPING_API_VERSION = "runtimeconditions.io/service-mapping/v1alpha1"
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
DNS_SUBDOMAIN_OR_EMPTY = r"^(?:|[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?)$"
DNS_LABEL = r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def semantic_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def require_string(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{description} must be a non-empty string")
    return value


def require_string_list(value: Any, description: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{description} must be a non-empty list of strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{description} contains duplicates")
    return value


def operation_schema(verbs: list[str], scopes: list[str], methods: list[str]) -> dict[str, Any]:
    ordinary_verbs = [verb for verb in verbs if verb != "connect"]
    coordinate_properties = {
        "apiGroup": {"type": "string", "maxLength": 253, "pattern": DNS_SUBDOMAIN_OR_EMPTY},
        "apiVersion": {"type": "string", "maxLength": 63, "pattern": DNS_LABEL},
        "resource": {"type": "string", "maxLength": 63, "pattern": DNS_LABEL},
        "scope": {"enum": scopes},
        "subresource": {"type": "string", "maxLength": 63, "pattern": DNS_LABEL},
    }
    ordinary_resource = {
        "type": "object",
        "required": ["verb", "apiGroup", "apiVersion", "resource", "scope"],
        "properties": {"verb": {"enum": ordinary_verbs}, **coordinate_properties},
        "additionalProperties": False,
    }
    connect_resource = {
        "type": "object",
        "required": ["verb", "method", "apiGroup", "apiVersion", "resource", "scope"],
        "properties": {"verb": {"const": "connect"}, "method": {"enum": methods}, **coordinate_properties},
        "additionalProperties": False,
    }
    non_resource = {
        "type": "object",
        "required": ["path", "method"],
        "properties": {
            "path": {"type": "string", "minLength": 1, "pattern": "^/"},
            "method": {"enum": methods},
        },
        "additionalProperties": False,
    }
    return {"oneOf": [ordinary_resource, connect_resource, non_resource]}


def build_spec(semantics: dict[str, Any]) -> dict[str, Any]:
    extension = semantics.get("extension", {})
    kind = require_string(extension.get("conditionKind"), "extension.conditionKind")
    interface_type = require_string(extension.get("interfaceType"), "extension.interfaceType")
    verbs = require_string_list(semantics.get("resourceOperations", {}).get("verbs"), "resourceOperations.verbs")
    scopes = require_string_list(semantics.get("resourceOperations", {}).get("scopes"), "resourceOperations.scopes")
    methods = require_string_list(semantics.get("nonResourceOperations", {}).get("httpMethods"), "nonResourceOperations.httpMethods")
    if "connect" not in verbs or semantics.get("resourceOperations", {}).get("connectRequiresHttpMethod") is not True:
        raise ValueError("resourceOperations must preserve connect with a required HTTP method")
    condition_schema = {
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
                        "items": operation_schema(verbs, scopes, methods),
                    },
                },
                "additionalProperties": False,
            },
        },
    }
    Draft202012Validator.check_schema(condition_schema)
    return {
        "kinds": [{"name": kind}],
        "interfaceTypes": [{"name": interface_type, "targetKind": kind}],
        "interfaceFields": [{"name": "operations", "targetKind": kind, "targetType": interface_type}],
        "fieldValues": [
            {"field": "interface.operations[].verb", "targetKind": kind, "targetType": interface_type, "values": verbs},
            {"field": "interface.operations[].scope", "targetKind": kind, "targetType": interface_type, "values": scopes},
            {"field": "interface.operations[].method", "targetKind": kind, "targetType": interface_type, "values": methods},
        ],
        "schemas": [
            {
                "id": "kubernetes-api-interface",
                "appliesToKind": kind,
                "appliesToInterfaceType": interface_type,
                "description": "Validates Kubernetes resource, connect, and non-resource API requirements.",
                "schema": condition_schema,
            }
        ],
    }


def profile_operation(inventory_operation: dict[str, Any]) -> dict[str, Any]:
    projection = inventory_operation.get("projection", {})
    form = projection.get("form")
    if form == "non_resource":
        return {"path": require_string(projection.get("path"), "non-resource path"), "method": require_string(projection.get("method"), "non-resource method")}
    if form != "resource":
        raise ValueError(f"{inventory_operation.get('operationId')}: unknown projection form {form!r}")
    result = {key: projection[key] for key in ("verb", "apiGroup", "apiVersion", "resource", "scope")}
    if projection.get("subresource"):
        result["subresource"] = projection["subresource"]
    if projection.get("verb") == "connect":
        result["method"] = require_string(inventory_operation.get("method"), "connect HTTP method")
    return result


def validate_inventory(inventory: dict[str, Any], semantics: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    reviewed = semantics.get("reviewedInventory", {})
    metadata = inventory.get("metadata", {})
    for field in ("operationCount", "operationIdsSha256", "semanticSha256"):
        if metadata.get(field) != reviewed.get(field):
            raise ValueError(f"authoritative inventory {field} changed: got {metadata.get(field)!r}, reviewed {reviewed.get(field)!r}")
    extension = semantics["extension"]
    validator = Draft202012Validator(spec["schemas"][0]["schema"])
    mapping_operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in inventory.get("operations", []):
        name = require_string(item.get("operationId"), "inventory operationId")
        if name in seen:
            raise ValueError(f"duplicate authoritative operation {name}")
        seen.add(name)
        operation = profile_operation(item)
        condition = {"kind": extension["conditionKind"], "interface": {"type": extension["interfaceType"], "operations": [operation]}}
        errors = sorted(validator.iter_errors(condition), key=lambda error: list(error.path))
        if errors:
            raise ValueError(f"{name}: operation is not valid extension vocabulary: {errors[0].message}")
        mapping_operations.append(
            {
                "name": name,
                "endpoint": {"path": item["path"], "method": item["method"]},
                "conditions": [{"kind": extension["conditionKind"], "interfaceType": extension["interfaceType"], "operation": operation}],
            }
        )
    if len(mapping_operations) != reviewed["operationCount"]:
        raise ValueError("authoritative inventory operation list does not match reviewed count")
    return mapping_operations


def discovery_resources(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    operations: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for item in inventory.get("operations", []):
        projection = item.get("projection", {})
        group_version_kind = item.get("source", {}).get("groupVersionKind")
        if projection.get("form") != "resource" or projection.get("subresource") or not isinstance(group_version_kind, dict):
            continue
        selector = tuple(group_version_kind.get(field) for field in ("group", "version", "kind"))
        if not all(isinstance(value, str) for value in selector):
            raise ValueError(f"{item.get('operationId')}: base resource has an invalid group/version/kind selector")
        identity = {
            "apiGroup": projection["apiGroup"],
            "apiVersion": projection["apiVersion"],
            "kind": group_version_kind["kind"],
            "resource": projection["resource"],
        }
        previous = indexed.get(selector)
        if previous is not None and previous != identity:
            raise ValueError(f"ambiguous discovery resource selector {selector!r}: {previous!r} and {identity!r}")
        indexed[selector] = identity
        operations[selector][projection["verb"]].add(projection["scope"])

    resources: list[dict[str, Any]] = []
    for selector in sorted(indexed):
        scopes = {scope for values in operations[selector].values() for scope in values}
        namespaced = bool(scopes.intersection({"namespaced", "all_namespaces"}))
        if namespaced and "cluster" in scopes:
            raise ValueError(f"discovery resource selector {selector!r} mixes cluster and namespaced access")
        resources.append(
            {
                **indexed[selector],
                "namespaced": namespaced,
                "operations": [
                    {"verb": verb, "scopes": sorted(operations[selector][verb])}
                    for verb in sorted(operations[selector])
                ],
            }
        )
    if not resources:
        raise ValueError("authoritative inventory contains no discoverable base resources")
    return resources


def build_outputs(inventory: dict[str, Any], semantics: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    extension_config = semantics.get("extension", {})
    extension_id = require_string(extension_config.get("id"), "extension.id")
    version = require_string(extension_config.get("version"), "extension.version")
    if not SEMVER.fullmatch(version) or f"/{version}/" not in extension_id:
        raise ValueError("extension id and semantic version do not identify the same release")
    spec = build_spec(semantics)
    mapping_operations = validate_inventory(inventory, semantics, spec)
    resources = discovery_resources(inventory)
    source = inventory["metadata"]["source"]
    spec_digest = semantic_sha256(spec)
    extension = {
        "apiVersion": EXTENSION_API_VERSION,
        "kind": "RuntimeConditionsExtensionDefinition",
        "metadata": {
            "id": extension_id,
            "version": version,
            "semanticSha256": spec_digest,
            "provenance": {
                "repository": source["repository"],
                "revision": source["revision"],
                "ref": source["ref"],
                "path": source["path"],
                "sha256": source["sha256"],
                "semanticSha256": source["semanticSha256"],
                "inventorySemanticSha256": inventory["metadata"]["semanticSha256"],
            },
        },
        "spec": spec,
    }
    service_mapping = {
        "apiVersion": SERVICE_MAPPING_API_VERSION,
        "kind": "RuntimeConditionsServiceMapping",
        "metadata": {
            "name": "kubernetes.api",
            "service": "kubernetes-api",
            "apiVersion": source["ref"],
            "operationCount": len(mapping_operations),
            "operationIdsSha256": inventory["metadata"]["operationIdsSha256"],
            "sourceInventorySemanticSha256": inventory["metadata"]["semanticSha256"],
            "resourceCount": len(resources),
            "semanticSha256": semantic_sha256({"operations": mapping_operations, "resources": resources}),
            "source": source,
        },
        "extension": {"id": extension_id, "version": version, "semanticSha256": spec_digest},
        "operations": mapping_operations,
        "resources": resources,
    }
    return extension, service_mapping


def review_markdown(extension: dict[str, Any], mapping: dict[str, Any]) -> str:
    operations = mapping["operations"]
    resources = mapping["resources"]
    forms = Counter("non_resource" if "path" in item["conditions"][0]["operation"] else "resource" for item in operations)
    verbs = Counter(item["conditions"][0]["operation"].get("verb") for item in operations if "verb" in item["conditions"][0]["operation"])
    connect_methods = Counter(item["conditions"][0]["operation"].get("method") for item in operations if item["conditions"][0]["operation"].get("verb") == "connect")
    unique_conditions = {semantic_sha256(item["conditions"]) for item in operations}
    lines = [
        "# Kubernetes API extension release review",
        "",
        "**Classification: `accepted`**",
        "",
        "The approved Kubernetes operation forms compile into an immutable extension release and every authoritative Kubernetes v1.36.2 operation validates against that release.",
        "",
        "## Release",
        "",
        f"- Extension: `{extension['metadata']['id']}`",
        f"- Version: `{extension['metadata']['version']}`",
        f"- Extension semantic SHA-256: `{extension['metadata']['semanticSha256']}`",
        f"- Service-mapping semantic SHA-256: `{mapping['metadata']['semanticSha256']}`",
        f"- Authoritative operations: {len(operations)}",
        f"- Resource operations: {forms['resource']}",
        f"- Non-resource operations: {forms['non_resource']}",
        f"- Distinct condition operations: {len(unique_conditions)}",
        f"- Discoverable built-in resource selectors: {len(resources)}",
        "",
        "## Preserved semantics",
        "",
        f"- Resource verbs: {', '.join(f'`{name}` {count}' for name, count in sorted(verbs.items()))}",
        f"- Connect HTTP methods: {', '.join(f'`{name}` {count}' for name, count in sorted(connect_methods.items()))}",
        "- Resource operations retain API group, API version, plural resource, access scope, and optional subresource.",
        "- Connect operations additionally retain HTTP method rather than collapsing distinct connect endpoints.",
        "- Non-resource operations retain canonical path and HTTP method.",
        "- The resource-coordinate schema remains open to valid CRD group, version, resource, and subresource values; the built-in inventory is not a closed vocabulary enum.",
        "- The service mapping includes a generated, language-neutral GVK-to-resource discovery catalog for built-in resources. It does not claim that unmodeled CRDs can be resolved without live discovery evidence.",
        "",
        "## Maintainer review surface",
        "",
        "Maintainers review the compact `model/runtimeconditions.yaml` semantic contract and this summary. The extension release and complete service mapping are deterministic machine outputs and are not line-by-line review surfaces.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--semantics", type=Path, required=True)
    parser.add_argument("--extension-output", type=Path, required=True)
    parser.add_argument("--service-mapping-output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
    args = parser.parse_args()
    inventory = read_document(args.inventory)
    semantics = read_document(args.semantics)
    extension, mapping = build_outputs(inventory, semantics)
    write_yaml(args.extension_output, extension)
    write_yaml(args.service_mapping_output, mapping)
    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.write_text(review_markdown(extension, mapping), encoding="utf-8")
    print("classification: accepted")
    print(f"extension: {extension['metadata']['id']}")
    print(f"operations: {mapping['metadata']['operationCount']}")
    print(f"extension semantic sha256: {extension['metadata']['semanticSha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

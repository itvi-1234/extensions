#!/usr/bin/env python3
"""Project a Kubernetes OpenAPI v2 document into a deterministic language-neutral operation inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from serialization import read_document, write_yaml


INVENTORY_API_VERSION = "runtimeconditions.io/kubernetes-openapi-inventory/v1alpha1"
INVENTORY_KIND = "RuntimeConditionsKubernetesOpenAPIOperationInventory"
HTTP_METHODS = ("delete", "get", "head", "options", "patch", "post", "put", "trace")
NORMALIZED_VERBS = {
    "delete": "delete",
    "deletecollection": "deletecollection",
    "get": "get",
    "list": "list",
    "patch": "patch",
    "post": "create",
    "put": "update",
    "watch": "watch",
    "watchlist": "watch",
    "connect": "connect",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def semantic_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def fingerprint(values: Iterable[str]) -> str:
    return sha256_bytes(("\n".join(values) + "\n").encode("utf-8"))


def require_string(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{description} must be a non-empty string")
    return value


def extract_operations(model: dict[str, Any]) -> list[dict[str, Any]]:
    if model.get("swagger") != "2.0":
        raise ValueError("Kubernetes projection requires a Swagger 2.0 document")
    paths = model.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ValueError("OpenAPI document must contain paths")
    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path_item, dict):
            raise ValueError(f"path item {path!r} must be an object")
        for method in HTTP_METHODS:
            if method not in path_item:
                continue
            operation = path_item[method]
            if not isinstance(operation, dict):
                raise ValueError(f"{method.upper()} {path}: operation must be an object")
            operation_id = require_string(operation.get("operationId"), f"{method.upper()} {path} operationId")
            if operation_id in seen:
                raise ValueError(f"duplicate operationId {operation_id!r}")
            seen.add(operation_id)
            tags = operation.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag for tag in tags):
                raise ValueError(f"{operation_id}: tags must be a list of non-empty strings")
            action = operation.get("x-kubernetes-action")
            gvk = operation.get("x-kubernetes-group-version-kind")
            if (action is None) != (gvk is None):
                raise ValueError(f"{operation_id}: x-kubernetes-action and x-kubernetes-group-version-kind must be present together")
            if action is not None:
                require_string(action, f"{operation_id} x-kubernetes-action")
                if action not in NORMALIZED_VERBS:
                    raise ValueError(f"{operation_id}: unsupported Kubernetes action {action!r}")
                if not isinstance(gvk, dict):
                    raise ValueError(f"{operation_id}: x-kubernetes-group-version-kind must be an object")
                for field in ("group", "kind", "version"):
                    if not isinstance(gvk.get(field), str) or (field != "group" and not gvk[field]):
                        raise ValueError(f"{operation_id}: invalid GVK {field}")
            operations.append(
                {
                    "operationId": operation_id,
                    "path": path,
                    "method": method,
                    "tags": tags,
                    "action": action,
                    "gvk": gvk,
                }
            )
    if not operations:
        raise ValueError("OpenAPI document contains no operations")
    return sorted(operations, key=lambda item: item["operationId"])


def parse_resource_path(path: str) -> dict[str, Any]:
    segments = path.strip("/").split("/")
    if len(segments) >= 2 and segments[0] == "api":
        api_group = ""
        api_version = segments[1]
        remaining = segments[2:]
    elif len(segments) >= 3 and segments[0] == "apis":
        api_group = segments[1]
        api_version = segments[2]
        remaining = segments[3:]
    else:
        raise ValueError(f"resource operation path is outside /api or /apis: {path}")
    watch_path = bool(remaining and remaining[0] == "watch")
    if watch_path:
        remaining = remaining[1:]
    route_scope = "cluster"
    if len(remaining) >= 3 and remaining[0] == "namespaces" and remaining[1] == "{namespace}":
        route_scope = "namespaced"
        remaining = remaining[2:]
    if not remaining:
        raise ValueError(f"resource operation path does not identify a resource: {path}")
    resource = remaining[0]
    tail = remaining[1:]
    name_parameter = None
    if tail and tail[0].startswith("{") and tail[0].endswith("}"):
        name_parameter = tail[0][1:-1]
        tail = tail[1:]
    static_tail = [segment for segment in tail if not (segment.startswith("{") and segment.endswith("}"))]
    if len(static_tail) > 1:
        raise ValueError(f"resource operation path contains unsupported nested subresources: {path}")
    result: dict[str, Any] = {
        "apiGroup": api_group,
        "apiVersion": api_version,
        "resource": resource,
        "routeScope": route_scope,
    }
    if name_parameter:
        result["nameParameter"] = name_parameter
    if static_tail:
        result["subresource"] = static_tail[0]
    if watch_path:
        result["watchPath"] = True
    return result


def build_inventory(
    model_path: Path,
    model: dict[str, Any],
    source_repository: str,
    source_revision: str,
    source_ref: str,
    source_path: str,
) -> dict[str, Any]:
    raw_operations = extract_operations(model)
    parsed_resources: dict[str, dict[str, Any]] = {}
    family_namespaced: dict[tuple[str, str, str], bool] = defaultdict(bool)
    for operation in raw_operations:
        if operation["action"] is None:
            continue
        parsed = parse_resource_path(operation["path"])
        parsed_resources[operation["operationId"]] = parsed
        family = (parsed["apiGroup"], parsed["apiVersion"], parsed["resource"])
        family_namespaced[family] = family_namespaced[family] or parsed["routeScope"] == "namespaced"

    operations: list[dict[str, Any]] = []
    for operation in raw_operations:
        projected: dict[str, Any] = {
            "operationId": operation["operationId"],
            "path": operation["path"],
            "method": operation["method"],
        }
        if operation["tags"]:
            projected["tags"] = operation["tags"]
        if operation["action"] is None:
            projected["classification"] = "non_resource"
            projected["projection"] = {
                "form": "non_resource",
                "path": operation["path"],
                "method": operation["method"],
            }
            operations.append(projected)
            continue
        parsed = parsed_resources[operation["operationId"]]
        family = (parsed["apiGroup"], parsed["apiVersion"], parsed["resource"])
        if parsed["routeScope"] == "namespaced":
            access_scope = "namespaced"
        elif family_namespaced[family]:
            access_scope = "all_namespaces"
        else:
            access_scope = "cluster"
        endpoint_gv = (parsed["apiGroup"], parsed["apiVersion"])
        gvk = operation["gvk"]
        projection: dict[str, Any] = {
            "form": "resource",
            "verb": NORMALIZED_VERBS[operation["action"]],
            "apiGroup": parsed["apiGroup"],
            "apiVersion": parsed["apiVersion"],
            "resource": parsed["resource"],
            "scope": access_scope,
        }
        if parsed.get("subresource"):
            projection["subresource"] = parsed["subresource"]
        projected["classification"] = "resource"
        projected["source"] = {
            "action": operation["action"],
            "groupVersionKind": {
                "group": gvk["group"],
                "version": gvk["version"],
                "kind": gvk["kind"],
            },
        }
        if endpoint_gv != (gvk["group"], gvk["version"]):
            projected["source"]["groupVersionKindDiffersFromEndpoint"] = True
        if parsed.get("watchPath"):
            projected["source"]["watchPath"] = True
        projected["projection"] = projection
        operations.append(projected)

    operation_ids = [operation["operationId"] for operation in operations]
    classification_counts = Counter(operation["classification"] for operation in operations)
    action_counts = Counter(operation.get("source", {}).get("action") for operation in operations if operation["classification"] == "resource")
    verb_counts = Counter(operation["projection"]["verb"] for operation in operations if operation["classification"] == "resource")
    scope_counts = Counter(operation["projection"]["scope"] for operation in operations if operation["classification"] == "resource")
    subresource_counts = Counter(operation["projection"].get("subresource") for operation in operations if operation["classification"] == "resource" and operation["projection"].get("subresource"))
    mismatches = sum(bool(operation.get("source", {}).get("groupVersionKindDiffersFromEndpoint")) for operation in operations)
    model_semantic_digest = semantic_sha256(model)
    return {
        "apiVersion": INVENTORY_API_VERSION,
        "kind": INVENTORY_KIND,
        "metadata": {
            "name": "kubernetes-api",
            "operationCount": len(operations),
            "operationIdsSha256": fingerprint(operation_ids),
            "semanticSha256": semantic_sha256(operations),
            "source": {
                "repository": source_repository,
                "revision": source_revision,
                "ref": source_ref,
                "path": source_path,
                "sha256": sha256_file(model_path),
                "semanticSha256": model_semantic_digest,
                "swaggerVersion": model.get("swagger"),
            },
            "summary": {
                "classifications": dict(sorted(classification_counts.items())),
                "actions": dict(sorted(action_counts.items())),
                "verbs": dict(sorted(verb_counts.items())),
                "accessScopes": dict(sorted(scope_counts.items())),
                "subresources": dict(sorted(subresource_counts.items())),
                "resourceFamilies": len(family_namespaced),
                "namespacedResourceFamilies": sum(family_namespaced.values()),
                "clusterResourceFamilies": len(family_namespaced) - sum(family_namespaced.values()),
                "groupVersionKindEndpointMismatches": mismatches,
                "connectOperations": verb_counts.get("connect", 0),
            },
        },
        "operations": operations,
    }


def baseline_operation_ids(path: Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    return {operation["operationId"] for operation in read_document(path).get("operations", [])}


def review_markdown(inventory: dict[str, Any], baseline: set[str]) -> str:
    metadata = inventory["metadata"]
    summary = metadata["summary"]
    source = metadata["source"]
    current = {operation["operationId"] for operation in inventory["operations"]}
    added = sorted(current - baseline) if baseline else []
    removed = sorted(baseline - current) if baseline else []
    representative = next(operation for operation in inventory["operations"] if operation["operationId"] == "readCoreV1NamespacedConfigMap")
    lines = [
        "# Kubernetes OpenAPI semantic review",
        "",
        "**Classification: `investigation`**",
        "",
        "The authoritative Kubernetes operation inventory projected deterministically. The extension vocabulary remains unreleased while the structured resource, non-resource, connect, watch, and dynamic-resource semantics are reviewed.",
        "",
        "## Authoritative input",
        "",
        f"- Repository: `{source['repository']}`",
        f"- Revision: `{source['revision']}`",
        f"- Release ref: `{source['ref']}`",
        f"- Path: `{source['path']}`",
        f"- Source SHA-256: `{source['sha256']}`",
        f"- Source semantic SHA-256: `{source['semanticSha256']}`",
        f"- Operation IDs: {metadata['operationCount']}",
        f"- Operation-ID SHA-256: `{metadata['operationIdsSha256']}`",
        f"- Inventory semantic SHA-256: `{metadata['semanticSha256']}`",
        "",
        "## Inventory",
        "",
        f"- Resource operations: {summary['classifications'].get('resource', 0)}",
        f"- Non-resource operations: {summary['classifications'].get('non_resource', 0)}",
        f"- Resource families: {summary['resourceFamilies']} ({summary['namespacedResourceFamilies']} namespaced, {summary['clusterResourceFamilies']} cluster-scoped)",
        f"- Access scopes: {', '.join(f'`{name}` {count}' for name, count in summary['accessScopes'].items())}",
        f"- Connect operations requiring a vocabulary decision: {summary['connectOperations']}",
        f"- Endpoint/GVK group-version differences requiring the endpoint coordinates to remain authoritative: {summary['groupVersionKindEndpointMismatches']}",
        "",
        "| Normalized verb | Operations |",
        "| --- | ---: |",
    ]
    for verb, count in summary["verbs"].items():
        lines.append(f"| `{verb}` | {count} |")
    lines.extend(
        [
            "",
            "## Representative operation",
            "",
            f"`{representative['operationId']}` projects to `{representative['projection']['verb']}` on `{representative['projection']['apiGroup'] or 'core'}/{representative['projection']['apiVersion']}` resource `{representative['projection']['resource']}` with `{representative['projection']['scope']}` access.",
            "",
            "## Findings that affect extension design",
            "",
            "- A namespaced resource can be accessed within one namespace or across all namespaces. The operation needs `namespaced`, `all_namespaces`, and `cluster` access scopes rather than a single resource-scope flag.",
            "- The endpoint group and version identify the accessed API resource. GVK identifies the request or response representation and differs for eviction, scale, and token subresources, so it cannot replace endpoint coordinates.",
            "- Dedicated watch and watch-list endpoints normalize to the same logical `watch` verb in the language-neutral inventory, but an SDK generator may transform or remove those endpoints and must own the resulting language behavior.",
            "- Non-resource endpoints need a separately validated operation form instead of being forced into resource coordinates.",
            "- Connect operations preserve the authoritative Kubernetes action and HTTP method until maintainers approve adopter-facing semantics for attach, exec, port-forward, and proxy access.",
        ]
    )
    if baseline:
        lines.extend(
            [
                "",
                "## Operation-set change",
                "",
                f"- Added: {', '.join(f'`{item}`' for item in added) if added else 'none'}",
                f"- Removed: {', '.join(f'`{item}`' for item in removed) if removed else 'none'}",
            ]
        )
    lines.extend(
        [
            "",
            "## Human review surface",
            "",
            "Review the structured operation forms, access-scope distinctions, connect semantics, non-resource representation, CRD compatibility, and representative adapter impact. The complete generated YAML inventory is machine output and is not a line-by-line review surface.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--inventory-output", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    model = read_document(args.model)
    inventory = build_inventory(
        args.model,
        model,
        args.source_repository,
        args.source_revision,
        args.source_ref,
        args.source_path,
    )
    baseline = baseline_operation_ids(args.baseline)
    write_yaml(args.inventory_output, inventory)
    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.write_text(review_markdown(inventory, baseline), encoding="utf-8")
    print("classification: investigation")
    print(f"operations: {inventory['metadata']['operationCount']}")
    print(f"resource operations: {inventory['metadata']['summary']['classifications'].get('resource', 0)}")
    print(f"non-resource operations: {inventory['metadata']['summary']['classifications'].get('non_resource', 0)}")
    print(f"inventory semantic sha256: {inventory['metadata']['semanticSha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

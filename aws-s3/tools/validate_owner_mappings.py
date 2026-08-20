#!/usr/bin/env python3
"""Validate recursively composable SDK mapping artifacts as static data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def key(value: dict[str, Any]) -> tuple[str, str]:
    metadata = value.get("metadata", {})
    distribution = metadata.get("distribution")
    name = metadata.get("name")
    if not isinstance(distribution, str) or not isinstance(name, str):
        raise ValueError("mapping metadata must identify distribution and name")
    return distribution, name


def target_key(reference: dict[str, Any]) -> tuple[str, str]:
    distribution = reference.get("distribution")
    mapping = reference.get("mapping")
    if not isinstance(distribution, str) or not isinstance(mapping, str):
        raise ValueError(f"invalid SDK mapping reference: {reference!r}")
    return distribution, mapping


def operations(mapping: dict[str, Any]) -> set[str]:
    return {
        item["name"]
        for item in mapping.get("operations", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def waiters(mapping: dict[str, Any]) -> set[str]:
    return {
        item["name"]
        for item in mapping.get("python", {})
        .get("client", {})
        .get("waiterFactory", {})
        .get("items", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def calls(mapping: dict[str, Any]) -> set[str]:
    return {
        item["name"]
        for item in mapping.get("python", {}).get("calls", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def validate_mapping(
    mapping: dict[str, Any], registry: dict[tuple[str, str], dict[str, Any]]
) -> None:
    mapping_key = key(mapping)
    declared_dependencies = {
        (dependency["distribution"], dependency["mapping"])
        for dependency in mapping.get("dependencies", [])
        if dependency.get("kind") == "sdkMapping"
    }
    for dependency in declared_dependencies:
        if dependency not in registry:
            raise ValueError(f"{mapping_key}: missing SDK mapping dependency {dependency}")

    used_dependencies: set[tuple[str, str]] = set()
    for item in walk(mapping):
        if "operationRef" in item:
            reference = item["operationRef"]
            target = target_key(reference)
            target_mapping = registry.get(target)
            if target_mapping is None:
                raise ValueError(f"{mapping_key}: operation target is missing: {target}")
            operation = reference.get("operation")
            if operation not in operations(target_mapping):
                raise ValueError(f"{mapping_key}: unknown operation {target}.{operation}")
            if target != mapping_key:
                used_dependencies.add(target)
        if "waiterRef" in item:
            reference = item["waiterRef"]
            target = target_key(reference)
            target_mapping = registry.get(target)
            if target_mapping is None:
                raise ValueError(f"{mapping_key}: waiter target is missing: {target}")
            waiter = reference.get("waiter")
            if waiter not in waiters(target_mapping):
                raise ValueError(f"{mapping_key}: unknown waiter {target}.{waiter}")
            if target != mapping_key:
                used_dependencies.add(target)
        if "callRef" in item:
            reference = item["callRef"]
            target = target_key(reference)
            target_mapping = registry.get(target)
            if target_mapping is None:
                raise ValueError(f"{mapping_key}: call target is missing: {target}")
            call = reference.get("call")
            if call not in calls(target_mapping):
                raise ValueError(f"{mapping_key}: unknown call {target}.{call}")
            if target != mapping_key:
                used_dependencies.add(target)

    undeclared = sorted(used_dependencies - declared_dependencies)
    if undeclared:
        raise ValueError(f"{mapping_key}: references undeclared dependencies: {undeclared}")

    operation_names = operations(mapping)
    if operation_names:
        methods = mapping.get("python", {}).get("client", {}).get("methods", [])
        method_operations = {item.get("operation") for item in methods}
        if method_operations != operation_names:
            raise ValueError(f"{mapping_key}: client methods do not match canonical operations")
        for waiter in mapping.get("python", {}).get("client", {}).get("waiterFactory", {}).get("items", []):
            if waiter.get("operation") not in operation_names:
                raise ValueError(f"{mapping_key}: waiter has an unknown canonical operation")
        for paginator in mapping.get("python", {}).get("client", {}).get("paginatorFactory", {}).get("items", []):
            if paginator.get("operation") not in operation_names:
                raise ValueError(f"{mapping_key}: paginator has an unknown canonical operation")
        for operation in mapping.get("operations", []):
            for condition in operation.get("conditions", []):
                if condition.get("operation", {}).get("name") != operation.get("name"):
                    raise ValueError(f"{mapping_key}: Condition template operation mismatch")


def dependency_order(
    root: tuple[str, str], registry: dict[tuple[str, str], dict[str, Any]]
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    visiting: set[tuple[str, str]] = set()
    visited: set[tuple[str, str]] = set()

    def visit(current: tuple[str, str]) -> None:
        if current in visiting:
            raise ValueError(f"SDK mapping dependency cycle at {current}")
        if current in visited:
            return
        mapping = registry.get(current)
        if mapping is None:
            raise ValueError(f"missing SDK mapping: {current}")
        visiting.add(current)
        for dependency in mapping.get("dependencies", []):
            if dependency.get("kind") == "sdkMapping":
                visit((dependency["distribution"], dependency["mapping"]))
        visiting.remove(current)
        visited.add(current)
        result.append(current)

    visit(root)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", type=Path, action="append", required=True)
    parser.add_argument("--root-distribution", required=True)
    parser.add_argument("--root-mapping", required=True)
    args = parser.parse_args()

    registry: dict[tuple[str, str], dict[str, Any]] = {}
    for path in args.mapping:
        mapping = read_json(path)
        mapping_key = key(mapping)
        if mapping_key in registry:
            raise ValueError(f"duplicate mapping identity: {mapping_key}")
        registry[mapping_key] = mapping

    for mapping in registry.values():
        validate_mapping(mapping, registry)

    root = (args.root_distribution, args.root_mapping)
    order = dependency_order(root, registry)
    print("recursive SDK mapping validation passed")
    print("dependency order:")
    for distribution, mapping in order:
        print(f"  {distribution}: {mapping}")


if __name__ == "__main__":
    main()

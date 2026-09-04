#!/usr/bin/env python3
"""Compile the reviewed NATS semantic model into an immutable extension release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from serialization import read_document, write_yaml


SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
SUBJECT = {"type": "string", "minLength": 1, "pattern": r"^[^\s]+$"}
RESOURCE_NAME = {"type": "string", "minLength": 1, "pattern": r"^[^\s.*>]+$"}


def semantic_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_string(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{description} must be a non-empty string")
    return value


def actions(model: dict[str, Any], resource: str) -> list[str]:
    value = model.get("operationForms", {}).get(resource, {}).get("actions")
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"operationForms.{resource}.actions must be a non-empty string list")
    if len(value) != len(set(value)):
        raise ValueError(f"operationForms.{resource}.actions contains duplicates")
    return value


def object_form(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "required": required, "properties": properties, "additionalProperties": False}


def operation_schema(model: dict[str, Any]) -> dict[str, Any]:
    connection = object_form(["resource", "action"], {"resource": {"const": "connection"}, "action": {"enum": actions(model, "connection")}})
    subject = object_form(["resource", "action", "subject"], {"resource": {"const": "subject"}, "action": {"enum": actions(model, "subject")}, "subject": SUBJECT})
    stream_management = object_form(["resource", "action", "name"], {"resource": {"const": "stream"}, "action": {"enum": [item for item in actions(model, "stream") if item != "publish"]}, "name": RESOURCE_NAME, "subjects": {"type": "array", "minItems": 1, "uniqueItems": True, "items": SUBJECT}})
    stream_publish = object_form(["resource", "action", "subject"], {"resource": {"const": "stream"}, "action": {"const": "publish"}, "subject": SUBJECT})
    consumer = object_form(["resource", "action", "stream"], {"resource": {"const": "consumer"}, "action": {"enum": actions(model, "consumer")}, "stream": RESOURCE_NAME, "name": RESOURCE_NAME})
    key_value = object_form(["resource", "action", "bucket"], {"resource": {"const": "key_value"}, "action": {"enum": actions(model, "key_value")}, "bucket": RESOURCE_NAME})
    object_store = object_form(["resource", "action", "bucket"], {"resource": {"const": "object_store"}, "action": {"enum": actions(model, "object_store")}, "bucket": RESOURCE_NAME})
    return {"oneOf": [connection, subject, stream_management, stream_publish, consumer, key_value, object_store]}


def build(model: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    config = model.get("extension", {})
    extension_id = require_string(config.get("id"), "extension.id")
    version = require_string(config.get("version"), "extension.version")
    kind = require_string(config.get("conditionKind"), "extension.conditionKind")
    interface_type = require_string(config.get("interfaceType"), "extension.interfaceType")
    if not SEMVER.fullmatch(version) or f"/{version}/" not in extension_id:
        raise ValueError("extension id and version must identify the same semantic release")
    resources = list(model.get("operationForms", {}))
    all_actions = sorted({action for resource in resources for action in actions(model, resource)})
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["kind", "interface"],
        "properties": {
            "kind": {"const": kind},
            "interface": {
                "type": "object",
                "required": ["type", "operations"],
                "properties": {"type": {"const": interface_type}, "operations": {"type": "array", "minItems": 1, "uniqueItems": True, "items": operation_schema(model)}},
                "additionalProperties": False,
            },
        },
        "additionalProperties": True,
    }
    Draft202012Validator.check_schema(schema)
    spec = {
        "kinds": [{"name": kind}],
        "interfaceTypes": [{"name": interface_type, "targetKind": kind}],
        "interfaceFields": [{"name": "operations", "targetKind": kind, "targetType": interface_type}],
        "fieldValues": [
            {"field": "interface.operations[].resource", "targetKind": kind, "targetType": interface_type, "values": resources},
            {"field": "interface.operations[].action", "targetKind": kind, "targetType": interface_type, "values": all_actions},
        ],
        "schemas": [{"id": "nats-service-interface", "appliesToKind": kind, "appliesToInterfaceType": interface_type, "description": "Validates adapter-actionable NATS connection, subject authorization, and JetStream resource requirements.", "schema": schema}],
    }
    digest = semantic_sha256(spec)
    extension = {"apiVersion": "runtimeconditions.io/v1alpha1", "kind": "RuntimeConditionsExtensionDefinition", "metadata": {"id": extension_id, "version": version, "semanticSha256": digest}, "spec": spec}
    vocabulary = {"apiVersion": "runtimeconditions.io/service-mapping/v1alpha1", "kind": "RuntimeConditionsServiceVocabulary", "metadata": {"name": "nats.service", "service": "nats", "semanticSha256": semantic_sha256(model["operationForms"])}, "extension": {"id": extension_id, "version": version, "semanticSha256": digest}, "operationForms": model["operationForms"]}
    return extension, vocabulary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--extension-output", type=Path, required=True)
    parser.add_argument("--vocabulary-output", type=Path, required=True)
    args = parser.parse_args()
    extension, vocabulary = build(read_document(args.model))
    write_yaml(args.extension_output, extension)
    write_yaml(args.vocabulary_output, vocabulary)
    print(f"extension: {extension['metadata']['id']}")
    print(f"extension semantic sha256: {extension['metadata']['semanticSha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

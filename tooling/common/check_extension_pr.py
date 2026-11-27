"""Check documentation requirements in catalog extension folders changed by a PR."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

import yaml
from downstream_releases import version_key
from markdown_it import MarkdownIt
from serialization import RuntimeConditionsLoader

REPO_ROOT = Path(__file__).resolve().parents[2]


def require_description(value: object, path: str) -> list[str]:
    if not isinstance(value, str) or len(value.strip()) < 5:
        return [
            f"{path}: description must contain at least 5 characters after trimming whitespace"
        ]
    return []


def schema_problems(schema: object, path: str, seen: set[int]) -> list[str]:
    if not isinstance(schema, dict) or id(schema) in seen:
        return []
    seen.add(id(schema))
    problems = []
    for keyword in (
        "properties",
        "patternProperties",
        "$defs",
        "definitions",
        "dependentSchemas",
    ):
        entries = schema.get(keyword, {})
        if not isinstance(entries, dict):
            problems.append(f"{path}/{keyword}: expected an object")
            continue
        for name, child in entries.items():
            escaped = str(name).replace("~", "~0").replace("/", "~1")
            child_path = f"{path}/{keyword}/{escaped}"
            if keyword in ("properties", "patternProperties"):
                description = (
                    child.get("description") if isinstance(child, dict) else None
                )
                problems.extend(
                    require_description(description, f"{child_path}/description")
                )
            problems.extend(schema_problems(child, child_path, seen))
    for keyword in (
        "allOf",
        "anyOf",
        "oneOf",
        "prefixItems",
        "items",
        "contains",
        "additionalProperties",
        "unevaluatedProperties",
        "unevaluatedItems",
        "propertyNames",
        "if",
        "then",
        "else",
        "not",
        "dependencies",
    ):
        child = schema.get(keyword)
        if isinstance(child, list):
            for index, item in enumerate(child):
                problems.extend(
                    schema_problems(item, f"{path}/{keyword}/{index}", seen)
                )
        elif keyword == "dependencies" and isinstance(child, dict):
            for name, item in child.items():
                problems.extend(schema_problems(item, f"{path}/{keyword}/{name}", seen))
        else:
            problems.extend(schema_problems(child, f"{path}/{keyword}", seen))
    return problems


def definition_problems(document: dict) -> list[str]:
    spec = document.get("spec")
    if not isinstance(spec, dict):
        return ["/spec: expected an object"]
    problems = []
    for group in ("conditionFields", "interfaceFields", "schemas"):
        entries = spec.get(group, [])
        if not isinstance(entries, list):
            problems.append(f"/spec/{group}: expected an array")
            continue
        for index, entry in enumerate(entries):
            path = f"/spec/{group}/{index}"
            if not isinstance(entry, dict):
                problems.append(f"{path}: expected an object")
            elif group == "schemas":
                problems.extend(
                    schema_problems(entry.get("schema"), f"{path}/schema", set())
                )
            else:
                problems.extend(
                    require_description(entry.get("description"), f"{path}/description")
                )
    return problems


def readme_problems(readme: Path) -> list[str]:
    text = readme.read_text(encoding="utf-8")
    count = sum(
        token.type in ("fence", "code_block") for token in MarkdownIt().parse(text)
    )
    if count < 2 or count % 2:
        return [
            f"{readme}: expected at least 2 code blocks in usage/output pairs; found {count}"
        ]
    return []


def check_extension(folder: Path, changed: set[Path] | None = None) -> list[str]:
    problems = []
    candidates = sorted(
        set(folder.glob("*.yaml"))
        | set(folder.glob("*.yml"))
        | set(folder.glob("releases/*/runtimeconditions.extension.yaml"))
    )
    definitions = []
    for path in candidates:
        try:
            document = yaml.load(
                path.read_text(encoding="utf-8"), Loader=RuntimeConditionsLoader
            )
            if (
                not isinstance(document, dict)
                or document.get("kind") != "RuntimeConditionsExtensionDefinition"
            ):
                if path.name == "runtimeconditions.extension.yaml":
                    problems.append(
                        f"{path}: expected a RuntimeConditionsExtensionDefinition"
                    )
                continue
            metadata = document.get("metadata")
            if not isinstance(metadata, dict):
                problems.append(f"{path}:/metadata: expected an object with a version")
                continue
            version = version_key(str(metadata.get("version", "")))
            definitions.append((version, path, document))
        except (OSError, ValueError, yaml.YAMLError) as error:
            problems.append(f"{path}: {error}")
    if not definitions:
        problems.append(f"{folder}: no extension definitions found")
    else:
        newest = max(version for version, _, _ in definitions)
        for version, path, document in definitions:
            if version == newest or path in (changed or set()):
                problems.extend(
                    f"{path}:{problem}" for problem in definition_problems(document)
                )
    readme = folder / "README.md"
    try:
        problems.extend(readme_problems(readme))
    except (OSError, ValueError) as error:
        problems.append(f"{readme}: {error}")
    return problems


def changed_paths(root: Path, base: str, head: str) -> set[Path]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            f"{base}...{head}",
            "--",
            "catalog/",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return {root / os.fsdecode(name) for name in result.stdout.split(b"\0") if name}


def changed_extensions(root: Path, paths: set[Path]) -> list[Path]:
    folders = set()
    for path in paths:
        parts = PurePosixPath(path.relative_to(root)).parts
        if len(parts) >= 4 and parts[0] == "catalog":
            folder = root.joinpath(*parts[:3])
            if folder.is_dir():
                folders.add(folder)
    return sorted(folders)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--base", required=True, help="PR target commit or branch")
    parser.add_argument("--head", default="HEAD", help="PR head commit (default: HEAD)")
    args = parser.parse_args(argv)
    try:
        changed = changed_paths(args.repo_root, args.base, args.head)
        folders = changed_extensions(args.repo_root, changed)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Cannot determine changed extensions with git: {error}", file=sys.stderr)
        return 1
    problems = []
    for folder in folders:
        print(f"Checking {folder.relative_to(args.repo_root)}")
        problems.extend(check_extension(folder, changed))
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(
            f"Extension PR checklist failed: {len(problems)} problem(s).",
            file=sys.stderr,
        )
        return 1
    print(
        f"Extension PR checklist passed for {len(folders)} changed extension folder(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

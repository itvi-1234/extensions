"""Enforce that catalog extension kinds are namespaced under their
provider folder (catalog/<provider>/...). Doesn't check interfaceType yet -
see runtimeconditions/extensions#3.
"""

from __future__ import annotations

import sys
from pathlib import Path

from serialization import read_document

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = REPO_ROOT / "catalog"


def provider_for(extension_path: Path) -> str:
    return extension_path.relative_to(CATALOG_ROOT).parts[0]


def check_extension(extension_path: Path) -> list[str]:
    provider = provider_for(extension_path)
    prefix = f"{provider}."
    doc = read_document(extension_path)
    spec = doc.get("spec", {})

    problems = []
    for kind in spec.get("kinds", []):
        name = kind.get("name", "")
        if not name.startswith(prefix):
            problems.append(f"kind {name!r} is not namespaced under {prefix!r}")
    return problems


def main() -> int:
    failures: dict[Path, list[str]] = {}
    for extension_path in sorted(CATALOG_ROOT.glob("*/*/releases/*/runtimeconditions.extension.yaml")):
        problems = check_extension(extension_path)
        if problems:
            failures[extension_path] = problems

    if not failures:
        print("All catalog extensions are namespaced correctly.")
        return 0

    for extension_path, problems in failures.items():
        relative = extension_path.relative_to(REPO_ROOT)
        for problem in problems:
            print(f"{relative}: {problem}", file=sys.stderr)
    print(
        f"\n{sum(len(p) for p in failures.values())} namespacing violation(s) in "
        f"{len(failures)} extension(s). See the spec's namespacing rule: kind "
        "names must start with '<provider>.', where <provider> is the "
        "extension's top-level folder under catalog/.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

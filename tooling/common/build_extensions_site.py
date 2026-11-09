"""Publish canonical extension definitions, their lookup index, and Go discovery.

Only complete <location>:<version> extension references are supported. Definition
bytes are published unchanged beneath release paths; extensions/index.yaml maps
their exact identities to retrieval URLs and source checksums.
"""

from __future__ import annotations

import argparse
import re
import sys
from hashlib import sha256
from pathlib import Path
from html import escape
from urllib.parse import quote

import yaml

from go_bindings import GoBinding, load_bindings, validate_source
from serialization import read_document

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_HOST = "runtimeconditions.io"
CANONICAL_REFERENCE = re.compile(
    rf"https://{re.escape(EXPECTED_HOST)}/extensions/"
    r"([A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?):([^/?#\s]+)"
)


def canonical_parts(reference: str) -> tuple[str, str]:
    match = CANONICAL_REFERENCE.fullmatch(reference) if isinstance(reference, str) else None
    if match is None:
        raise ValueError(f"expected canonical extension reference <location>:<version>, got {reference!r}")
    location, version = match.groups()
    if location.startswith("rc/"):
        raise ValueError("canonical providerless references must omit the internal rc namespace")
    if version in {".", ".."} or "\\" in version or any(ord(char) < 32 or ord(char) == 127 for char in version):
        raise ValueError(f"invalid canonical extension version in {reference!r}")
    return location, version


def build_go_pages(output_dir: Path, root: Path) -> None:
    """Only generated modules get discovery pages; dormant catalog targets wait."""
    bindings = load_bindings(root)
    generated = []
    for binding in bindings.values():
        if not (root / binding.directory / "go.mod").is_file():
            continue
        validate_source(root, binding)
        generated.append(binding)
    for binding in generated:
        for module in sorted({binding.prefix, binding.module}):
            destination = output_dir / module.split("/", 1)[1] / "index.html"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(go_page(binding), encoding="utf-8")
            print(f"{binding.directory} -> /{module.split('/', 1)[1]}/")
    if generated:
        destination = output_dir / "x/index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        links = "\n".join(
            f'<li><a href="/{escape(binding.module.split("/", 1)[1])}/">{escape(binding.module)}</a></li>'
            for binding in sorted(generated, key=lambda item: item.module)
        )
        destination.write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<title>Runtime Conditions Go bindings</title></head><body>'
            '<h1>Runtime Conditions Go bindings</h1><ul>' + links + '</ul>'
            '<p>Requires Go 1.25 or later.</p></body></html>\n', encoding="utf-8"
        )


def go_page(binding: GoBinding) -> str:
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="go-import" content="{escape(binding.go_import, quote=True)}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(binding.module)} — Go bindings</title>
</head>
<body>
  <h1>{escape(binding.module)}</h1>
  <p>Runtime Conditions extension bindings for Go. Requires Go {escape(binding.go_version)} or later.</p>
  <h2>Install a released version</h2>
  <pre><code>go get {escape(binding.module)}@v{escape(binding.version)}</code></pre>
  <h2>Import</h2>
  <pre><code>import "{escape(binding.module)}"</code></pre>
  <p>The package name is <code>{escape(binding.name)}</code>; an import alias is optional.</p>
  <p>Versions are published with repository tags. The catalog version's tag is
     <code>{escape(binding.tag)}</code>.</p>
  <p><a href="{escape(binding.repository)}/tree/main/{escape(binding.directory)}">Generated source</a>
     · <a href="https://pkg.go.dev/{escape(binding.module)}">Go documentation</a>
     · <a href="/x/">All Go bindings</a></p>
</body>
</html>
'''


def build(output_dir: Path, root: Path = REPO_ROOT) -> int:
    catalog_root = root / "catalog"
    extension_paths = sorted(catalog_root.glob("*/*/releases/*/runtimeconditions.extension.yaml"))
    extension_paths += sorted(
        path
        for path in catalog_root.glob("*/*/*.yaml")
        if read_document(path).get("kind") == "RuntimeConditionsExtensionDefinition"
    )
    if not extension_paths:
        print("No extensions found under catalog/.", file=sys.stderr)
        return 1

    errors = []
    entries = {}
    outputs = {}
    for extension_path in extension_paths:
        relative = extension_path.relative_to(root)
        try:
            doc = read_document(extension_path)
            metadata = doc.get("metadata")
            if doc.get("kind") != "RuntimeConditionsExtensionDefinition" or not isinstance(metadata, dict):
                raise ValueError("expected extension definition with metadata object")
            extension_id = metadata.get("id")
            location, version = canonical_parts(extension_id)
            if "version" in metadata and metadata["version"] != version:
                raise ValueError("metadata.version must exactly match the canonical reference version")
            spec = doc.get("spec", {})
            if not isinstance(spec, dict) or not isinstance(spec.get("dependencies", []), list):
                raise ValueError("expected spec object with a dependencies array when present")
            for dependency in spec.get("dependencies", []):
                canonical_parts(dependency)
            destination = Path("extensions", *location.split("/"), "releases", version, "runtimeconditions.extension.yaml")
            if extension_id in entries:
                raise ValueError(f"duplicate extension id {extension_id!r}")
            if destination in outputs:
                raise ValueError(f"conflicting output path {destination}")
            source = extension_path.read_bytes()
            outputs[destination] = source
            entries[extension_id] = {
                "id": extension_id,
                "url": f"https://{EXPECTED_HOST}/" + quote(destination.as_posix(), safe="/"),
                "sourceSha256": sha256(source).hexdigest(),
            }
        except (ValueError, OSError) as error:
            errors.append(f"{relative}: {error}")

    index = {
        "apiVersion": "runtimeconditions.io/extension-index/v1alpha1",
        "kind": "RuntimeConditionsExtensionIndex",
        "extensions": [entries[identifier] for identifier in sorted(entries)],
    }
    outputs[Path("extensions/index.yaml")] = yaml.safe_dump(
        index, sort_keys=False, allow_unicode=True, width=4096
    ).encode("utf-8")
    for relative, source in outputs.items():
        destination = output_dir / relative
        if (not destination.resolve().is_relative_to(output_dir.resolve())
                or any(parent.exists() and not parent.is_dir() for parent in destination.parents)
                or destination.exists() and (not destination.is_file() or destination.read_bytes() != source)):
            errors.append(f"conflicting output path {relative}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"\nExtension publication failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    try:
        build_go_pages(output_dir, root)
        for relative, source in outputs.items():
            destination = output_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source)
            print(f"extension publication -> /{relative.as_posix()}")
    except (ValueError, KeyError, OSError) as error:
        print(f"Site assembly failed: {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return build(args.output)


if __name__ == "__main__":
    sys.exit(main())

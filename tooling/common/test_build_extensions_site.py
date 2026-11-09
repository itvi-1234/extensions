"""Exercise static discovery alongside extension-definition publication."""

from __future__ import annotations

from contextlib import redirect_stderr
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import yaml

from build_extensions_site import build
from go_bindings import load_bindings


class MetaTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.imports = []

    def handle_starttag(self, tag, attrs) -> None:
        values = dict(attrs)
        if tag == "meta" and values.get("name") == "go-import":
            self.imports.append(values.get("content"))


class SiteTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="binding-site-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "extensions"
        self.output = Path(temporary.name) / "site"
        self.config = {
            "coordinate": "runtimeconditions.io/x/vendor/service", "name": "service",
            "version": "0.1.0", "sourceDirectory": "bindings/service/go",
            "languageVersion": "1.25.0", "publicationMode": "github-tag",
        }
        self.catalog = {"repositoryUrl": "https://github.com/example/extensions", "packages": {
            "service": {"languages": {"go": self.config}},
            "pending": {"languages": {"go": {**self.config, "coordinate": "runtimeconditions.io/x/vendor/pending",
                "name": "pending", "sourceDirectory": "bindings/pending/go"}}},
        }}
        self.write_catalog()
        self.definition = self.root / "catalog/vendor/service/releases/0.1.0/runtimeconditions.extension.yaml"
        self.definition.parent.mkdir(parents=True)
        self.document = {"kind": "RuntimeConditionsExtensionDefinition", "metadata": {
            "id": "https://runtimeconditions.io/extensions/vendor/service:0.1.0", "version": "0.1.0"}}
        self.write_definition()
        self.write_source()

    def write_definition(self) -> None:
        self.definition.write_text(yaml.safe_dump(self.document), encoding="utf-8")

    def assert_rejected(self, message: str) -> None:
        errors = StringIO()
        with redirect_stderr(errors):
            self.assertEqual(build(self.output, self.root), 1)
        self.assertIn(message, errors.getvalue())

    def write_catalog(self) -> None:
        path = self.root / "tooling/extension-bindings/packages.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.catalog), encoding="utf-8")

    def write_source(self) -> None:
        source = self.root / self.config["sourceDirectory"]
        source.mkdir(parents=True, exist_ok=True)
        (source / "go.mod").write_text(f'module {self.config["coordinate"]}\n\ngo 1.25\n')
        (source / "bindings.go").write_text(f'package {self.config["name"]}\n')

    def test_site_contains_discovery_install_and_unaliased_import(self) -> None:
        self.assertEqual(build(self.output, self.root), 0)
        page = (self.output / "x/vendor/service/index.html").read_text()
        tags = MetaTags()
        tags.feed(page)
        self.assertEqual(tags.imports, [
            "runtimeconditions.io/x/vendor/service git https://github.com/example/extensions bindings/service/go"])
        self.assertIn('import "runtimeconditions.io/x/vendor/service"', page)
        self.assertIn("go get runtimeconditions.io/x/vendor/service@v0.1.0", page)
        self.assertFalse((self.output / "x/vendor/pending").exists())
        self.assertIn("runtimeconditions.io/x/vendor/service", (self.output / "x/index.html").read_text())
        published = self.output / "extensions/vendor/service/releases/0.1.0/runtimeconditions.extension.yaml"
        self.assertEqual(published.read_bytes(), self.definition.read_bytes())
        index = yaml.safe_load((self.output / "extensions/index.yaml").read_text())
        self.assertEqual(index, {
            "apiVersion": "runtimeconditions.io/extension-index/v1alpha1",
            "kind": "RuntimeConditionsExtensionIndex",
            "extensions": [{
                "id": self.document["metadata"]["id"],
                "url": "https://runtimeconditions.io/extensions/vendor/service/releases/0.1.0/runtimeconditions.extension.yaml",
                "sourceSha256": sha256(published.read_bytes()).hexdigest(),
            }],
        })
        self.assertFalse((self.output / "extensions/vendor/service:0.1.0").exists())
        self.assertFalse((self.output / "extensions/vendor/service/0.1.0").exists())

    def test_providerless_and_digest_versions_publish_exact_ids(self) -> None:
        for version in ("v1alpha1", "sha256:abc123"):
            with self.subTest(version=version):
                reference = f"https://runtimeconditions.io/extensions/common-integrations:{version}"
                self.document["metadata"] = {"id": reference}
                self.write_definition()
                output = self.output / version
                self.assertEqual(build(output, self.root), 0)
                artifact = output / f"extensions/common-integrations/releases/{version}/runtimeconditions.extension.yaml"
                self.assertEqual(artifact.read_bytes(), self.definition.read_bytes())
                entry = yaml.safe_load((output / "extensions/index.yaml").read_text())["extensions"][0]
                self.assertEqual(entry["id"], reference)
                encoded = version.replace(":", "%3A")
                self.assertEqual(entry["url"], f"https://runtimeconditions.io/extensions/common-integrations/releases/{encoded}/runtimeconditions.extension.yaml")

    def test_legacy_and_invalid_references_are_rejected_before_writing(self) -> None:
        for reference in (
            "https://runtimeconditions.io/extensions/vendor/service/0.1.0/runtimeconditions.extension.yaml",
            "https://runtimeconditions.io/extensions/vendor/service",
            "https://runtimeconditions.io/extensions/vendor/service:",
            "https://runtimeconditions.io/extensions/rc/service:0.1.0",
            "https://runtimeconditions.io/extensions/vendor/service:..",
            "https://runtimeconditions.io/extensions/vendor/../escape:1",
            "https://runtimeconditions.io/extensions/vendor/service:1?query=value",
            "https://runtimeconditions.io/extensions/vendor/service:1#fragment",
            "https://runtimeconditions.io/extensions/vendor/service:1\x00",
            "http://runtimeconditions.io/extensions/vendor/service:1",
            "https://other.example/extensions/vendor/service:1",
            None,
        ):
            with self.subTest(reference=reference):
                self.document["metadata"]["id"] = reference
                self.write_definition()
                self.assert_rejected("canonical")
                self.assertFalse(self.output.exists())

    def test_version_annotation_must_match_canonical_id(self) -> None:
        for version in ("0.2.0", "", None, 1):
            with self.subTest(version=version):
                self.document["metadata"]["version"] = version
                self.write_definition()
                self.assert_rejected("metadata.version")
                self.assertFalse(self.output.exists())

    def test_legacy_dependency_reference_is_rejected(self) -> None:
        self.document["spec"] = {"dependencies": [
            "https://runtimeconditions.io/extensions/common-integrations/v1alpha1/runtimeconditions.extension.yaml"]}
        self.write_definition()
        self.assert_rejected("canonical")
        self.assertFalse(self.output.exists())

    def test_duplicate_id_is_rejected_before_writing(self) -> None:
        duplicate = self.root / "catalog/vendor/duplicate/releases/0.1.0/runtimeconditions.extension.yaml"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_bytes(self.definition.read_bytes())
        self.assert_rejected("duplicate extension id")
        self.assertFalse(self.output.exists())

    def test_conflicting_artifact_path_is_rejected_before_writing(self) -> None:
        artifact = self.output / "extensions/vendor/service/releases/0.1.0/runtimeconditions.extension.yaml"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"unrelated content\n")
        self.assert_rejected("conflicting output path")
        self.assertEqual(artifact.read_bytes(), b"unrelated content\n")
        self.assertFalse((self.output / "extensions/index.yaml").exists())
        self.assertFalse((self.output / "x").exists())

    def test_lookup_entries_are_sorted_and_reproducible(self) -> None:
        additional = self.root / "catalog/rc/common-integrations/common-v1alpha1.yaml"
        additional.parent.mkdir(parents=True)
        reference = "https://runtimeconditions.io/extensions/common-integrations:v1alpha1"
        additional.write_text(yaml.safe_dump({"kind": "RuntimeConditionsExtensionDefinition", "metadata": {"id": reference}}))
        self.assertEqual(build(self.output, self.root), 0)
        index = (self.output / "extensions/index.yaml").read_bytes()
        entries = yaml.safe_load(index)["extensions"]
        self.assertEqual([entry["id"] for entry in entries], [reference, self.document["metadata"]["id"]])
        self.assertEqual(entries[0]["sourceSha256"], sha256(additional.read_bytes()).hexdigest())
        other_output = self.output.parent / "second-site"
        self.assertEqual(build(other_output, self.root), 0)
        self.assertEqual((other_output / "extensions/index.yaml").read_bytes(), index)

    def test_mismatched_generated_module_fails_site_build(self) -> None:
        (self.root / "bindings/service/go/go.mod").write_text("module github.com/old/module\n")
        self.assertEqual(build(self.output, self.root), 1)
        self.assertFalse((self.output / "x/vendor/service").exists())

    def test_mismatched_generated_package_fails_site_build(self) -> None:
        (self.root / "bindings/service/go/bindings.go").write_text("package vendorservice\n")
        self.assertEqual(build(self.output, self.root), 1)

    def test_major_versions_publish_prefix_and_versioned_discovery(self) -> None:
        self.config.update(coordinate="runtimeconditions.io/x/vendor/service/v10", version="10.1.0")
        self.write_catalog()
        self.write_source()
        self.assertEqual(build(self.output, self.root), 0)
        base = (self.output / "x/vendor/service/index.html").read_text()
        versioned = (self.output / "x/vendor/service/v10/index.html").read_text()
        self.assertEqual(base, versioned)
        self.assertIn('content="runtimeconditions.io/x/vendor/service git', base)

    def test_invalid_publication_coordinates_are_rejected(self) -> None:
        for changes in ({"coordinate": "runtimeconditions.io/x/vendor/../escape"},
                        {"coordinate": "other.example/x/vendor/service"},
                        {"sourceDirectory": "../outside"},
                        {"name": "renamed"}, {"languageVersion": "1.24.0"},
                        {"version": "2.0.0"}, {"version": "0.1.0-beta.01"}):
            original = self.config.copy()
            self.config.update(changes)
            self.write_catalog()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                load_bindings(self.root)
            self.config.clear()
            self.config.update(original)

    def test_duplicate_discovery_prefix_is_rejected(self) -> None:
        self.catalog["packages"]["pending"]["languages"]["go"].update(
            coordinate=self.config["coordinate"], name=self.config["name"])
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "duplicate public"):
            load_bindings(self.root)


if __name__ == "__main__":
    unittest.main()

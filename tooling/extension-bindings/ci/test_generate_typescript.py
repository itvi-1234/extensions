"""Exercise the TypeScript generation script."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from generation import select_targets
from testsupport import RepoTestCase, load_script, run_script

script = load_script("generate-typescript.py")

ROOT_EXTENSION = "https://example.test/owner/v1/extension.yaml"
ADDON_EXTENSION = "https://example.test/addon/v1/extension.yaml"


def typescript(name: str, directory: str, version: str = "0.1.0") -> dict:
    return {
        "coordinate": name,
        "name": name,
        "version": version,
        "sourceDirectory": directory,
        "languageVersion": "20.19.6",
        "publicationMode": "registry",
        "registryId": "npm",
    }


class TypeScriptGenerationTests(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.packages["owner"]["languages"]["typescript"] = typescript(
            "@example/owner", "bindings/owner/typescript"
        )
        self.packages["owner"]["rootExtension"] = ROOT_EXTENSION
        self.packages["addon"]["languages"]["typescript"] = typescript(
            "@example/addon", "bindings/addon/typescript"
        )
        self.packages["addon"]["rootExtension"] = ADDON_EXTENSION
        self.write_catalog()
        self.catalog_document = {
            "repositoryUrl": "https://github.com/example/extensions",
            "packages": self.packages,
        }

    def test_configure_reports_the_node_version_and_whether_typescript_is_selected(self) -> None:
        output = self.root.parent / "github-output"
        for targets, version, has_typescript in [
            ("owner:typescript", "20.19.6", "true"),
            ("owner:go", "", "false"),
            ("owner:go,owner:typescript", "20.19.6", "true"),
        ]:
            with self.subTest(targets=targets):
                values = run_script(
                    "generate-typescript.py",
                    self.root,
                    output,
                    "configure",
                    "--targets",
                    targets,
                )
                self.assertEqual(
                    values,
                    {"typescript-version": version, "has-typescript": has_typescript},
                )

    def test_the_emitter_digest_follows_its_sources_and_not_its_build(self) -> None:
        emitter = self.root / "emitter"
        for name, data in {
            "package.json": "{}",
            "package-lock.json": "{}",
            "package-target.schema.yaml": "type: object\n",
            "src/plan.ts": "export {};\n",
            "templates/package.json.tmpl": "{}",
        }.items():
            path = emitter / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding="utf-8")
        first = script.emitter_digest(emitter)
        (emitter / "dist").mkdir()
        (emitter / "dist/plan.js").write_text("built\n", encoding="utf-8")
        self.assertEqual(script.emitter_digest(emitter), first)
        (emitter / "src/plan.ts").write_text("export const x = 1;\n", encoding="utf-8")
        self.assertNotEqual(script.emitter_digest(emitter), first)

    def test_the_file_manifest_lists_every_file_but_itself_in_the_go_format(self) -> None:
        package = self.root / "package"
        (package / "src").mkdir(parents=True)
        (package / "src/b.ts").write_text("b\n", encoding="utf-8")
        (package / "a.json").write_text("a\n", encoding="utf-8")
        (package / script.FILE_MANIFEST).write_text("stale\n", encoding="utf-8")
        digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
        self.assertEqual(
            script.file_manifest(package),
            "apiVersion: runtimeconditions.io/file-manifest/v1alpha1\n"
            "kind: RuntimeConditionsFileManifest\n"
            "files:\n"
            f"    a.json: {digest('a' + chr(10))}\n"
            f"    src/b.ts: {digest('b' + chr(10))}\n",
        )

    def test_the_package_target_comes_from_the_catalog_and_the_model(self) -> None:
        model = {"dependencyEdges": [{"from": ROOT_EXTENSION, "to": ADDON_EXTENSION}]}
        target = script.package_target(self.catalog_document, "owner", model, "f" * 64)
        self.assertEqual(target["packageName"], "@example/owner")
        self.assertEqual(target["sourceDirectory"], "bindings/owner/typescript")
        self.assertEqual(target["minimumNodeVersion"], "20.19")
        self.assertEqual(target["registryId"], "npm")
        self.assertEqual(target["repositoryUrl"], "https://github.com/example/extensions")
        self.assertEqual(target["emitterSha256"], "f" * 64)
        self.assertEqual(
            target["dependencies"],
            [{"extension": ADDON_EXTENSION, "packageName": "@example/addon", "version": "0.1.0"}],
        )

    def test_a_package_without_dependency_edges_has_no_dependencies(self) -> None:
        target = script.package_target(self.catalog_document, "addon", {}, "f" * 64)
        self.assertEqual(target["dependencies"], [])

    def test_a_dependency_needs_exactly_one_typescript_provider(self) -> None:
        del self.packages["addon"]["languages"]["typescript"]
        model = {"dependencyEdges": [{"from": ROOT_EXTENSION, "to": ADDON_EXTENSION}]}
        with self.assertRaisesRegex(ValueError, "found 0"):
            script.package_target(self.catalog_document, "owner", model, "f" * 64)

    def test_the_root_extension_is_read_from_the_catalog_and_checked_against_the_lock(self) -> None:
        source = b"extension: definition\n"
        self.write("catalog/owner/owner-v1.yaml", source.decode())
        lock = {
            "extensions": [
                {
                    "id": ROOT_EXTENSION,
                    "sourceBackend": "catalog",
                    "sourceLocator": "catalog:owner/owner-v1.yaml",
                    "sourceSha256": hashlib.sha256(source).hexdigest(),
                }
            ]
        }
        self.assertEqual(script.root_extension_source(self.root, lock, ROOT_EXTENSION), source)
        lock["extensions"][0]["sourceSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "differs from the dependency lock"):
            script.root_extension_source(self.root, lock, ROOT_EXTENSION)
        lock["extensions"][0]["sourceLocator"] = "https:example.test/owner.yaml"
        with self.assertRaisesRegex(ValueError, "only catalog extension sources"):
            script.root_extension_source(self.root, lock, ROOT_EXTENSION)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            script.root_extension_source(self.root, lock, ADDON_EXTENSION)

    def test_generation_needs_the_built_emitter(self) -> None:
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(
            ValueError, "build the TypeScript emitter first"
        ):
            script.tools(self.root)
        built = self.root / "main.js"
        built.write_text("", encoding="utf-8")
        with patch.dict("os.environ", {"RC_TYPESCRIPT_EMITTER": str(built)}, clear=True):
            self.assertEqual(script.tools(self.root), ("node", built))

    def generated(self, files: dict[str, str]):
        def generate(root, catalog, key, rc, core, work):
            package = work / key
            for name, data in files.items():
                path = package / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(data, encoding="utf-8")
            return package

        return generate

    def test_update_replaces_the_committed_tree_and_check_compares_it(self) -> None:
        self.write("tooling/extension-bindings/packages.yaml", self.catalog.read_text(encoding="utf-8"))
        self.write("bindings/owner/typescript/stale.ts", "old generated source\n")
        targets = select_targets(self.catalog, "owner:typescript")
        files = {"package.json": "{}\n", "src/bindings.ts": "new\n"}
        with patch.object(script, "generate", self.generated(files)):
            with self.assertRaisesRegex(ValueError, "stale.ts"):
                script.run(self.root, targets, Path("rc"), Path("core.yaml"), False)
            script.run(self.root, targets, Path("rc"), Path("core.yaml"), True)
            script.run(self.root, targets, Path("rc"), Path("core.yaml"), False)
        committed = self.root / "bindings/owner/typescript"
        self.assertFalse((committed / "stale.ts").exists())
        self.assertEqual((committed / "src/bindings.ts").read_text(encoding="utf-8"), "new\n")

    def test_update_leaves_other_languages_alone(self) -> None:
        targets = select_targets(self.catalog, "owner:go")
        with patch.object(script, "generate") as generate:
            script.run(self.root, targets, Path("rc"), Path("core.yaml"), True)
        generate.assert_not_called()
        self.assertTrue((self.root / "bindings/owner/go/stale.go").exists())

    def test_typescript_targets_carry_their_directory_and_exact_node_version(self) -> None:
        self.assertIn(
            ("owner:typescript", "bindings/owner/typescript", "20.19.6"),
            select_targets(self.catalog, ""),
        )


if __name__ == "__main__":
    import unittest

    unittest.main()

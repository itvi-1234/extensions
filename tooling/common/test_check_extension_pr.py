"""Exercise extension documentation checks and PR-scoped Git selection."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import check_extension_pr as checklist
import yaml


class ExtensionFixture(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="extension-checklist-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.extension = self.root / "catalog/vendor/service"
        self.definition = (
            self.extension / "releases/0.1.0/runtimeconditions.extension.yaml"
        )
        self.document = {
            "kind": "RuntimeConditionsExtensionDefinition",
            "metadata": {"version": "0.1.0"},
            "spec": {
                "conditionFields": [
                    {"name": "configuration", "description": "Configuration"}
                ],
                "interfaceFields": [
                    {"name": "operations", "description": "Operations"}
                ],
                "schemas": [
                    {
                        "schema": {
                            "properties": {
                                "interface": {
                                    "description": "Interface",
                                    "properties": {
                                        "operations": {
                                            "description": "Operations",
                                            "type": "array",
                                            "items": {
                                                "properties": {
                                                    "name": {
                                                        "description": "Operation name"
                                                    }
                                                }
                                            },
                                        }
                                    },
                                }
                            }
                        }
                    }
                ],
            },
        }
        self.write_definition()
        self.readme = self.extension / "README.md"
        self.readme.write_text(
            "# Example\n```go\nUse()\n```\n```yaml\nkind: vendor.service\n```\n"
        )

    def write_definition(self) -> None:
        self.definition.parent.mkdir(parents=True, exist_ok=True)
        self.definition.write_text(yaml.safe_dump(self.document), encoding="utf-8")


class ChecklistTests(ExtensionFixture):
    def test_valid_extension_passes(self) -> None:
        self.assertEqual(checklist.check_extension(self.extension), [])

    def test_declared_fields_require_five_characters_after_trimming(self) -> None:
        for group in ("conditionFields", "interfaceFields"):
            for value in (None, "", "    ", "abcd", " abcd ", 12345):
                with self.subTest(group=group, description=value):
                    self.document["spec"][group][0]["description"] = value
                    self.write_definition()
                    problems = checklist.check_extension(self.extension)
                    self.assertTrue(
                        any(f"/spec/{group}/0/description" in p for p in problems)
                    )
            self.document["spec"][group][0]["description"] = "abcde"
        self.write_definition()
        self.assertEqual(checklist.check_extension(self.extension), [])

    def test_missing_description_is_reported_with_its_schema_path(self) -> None:
        del self.document["spec"]["schemas"][0]["schema"]["properties"]["interface"][
            "description"
        ]
        self.write_definition()
        problems = checklist.check_extension(self.extension)
        self.assertTrue(
            any(
                "/spec/schemas/0/schema/properties/interface/description" in p
                for p in problems
            )
        )

    def test_nested_fields_are_checked_through_schema_keywords(self) -> None:
        nested = {"properties": {"missing": {"type": "string"}}}
        wrappers = [
            {"items": nested},
            {"items": [nested]},
            {"prefixItems": [nested]},
            {"allOf": [nested]},
            {"anyOf": [nested]},
            {"oneOf": [nested]},
            {"$defs": {"record": nested}},
            {"definitions": {"record": nested}},
            {"if": nested},
            {"then": nested},
            {"else": nested},
            {"not": nested},
            {"additionalProperties": nested},
            {"contains": nested},
            {"patternProperties": {"^x": {"description": "Pattern", **nested}}},
            {"dependentSchemas": {"flag": nested}},
        ]
        for schema in wrappers:
            with self.subTest(schema=schema):
                self.document["spec"]["schemas"][0]["schema"] = schema
                self.write_definition()
                self.assertTrue(
                    any(
                        "/properties/missing/description" in p
                        for p in checklist.check_extension(self.extension)
                    )
                )

    def test_schema_examples_and_defaults_are_not_treated_as_field_definitions(
        self,
    ) -> None:
        schema = self.document["spec"]["schemas"][0]["schema"]
        schema.update(
            examples=[{"properties": {"example": {}}}],
            default={"properties": {"default": {}}},
            enum=[{"properties": {}}],
        )
        self.write_definition()
        self.assertEqual(checklist.check_extension(self.extension), [])

    def test_local_references_are_checked_in_definitions(self) -> None:
        self.document["spec"]["schemas"][0]["schema"] = {
            "$defs": {"operation": {"properties": {"name": {"type": "string"}}}},
            "properties": {
                "operation": {"$ref": "#/$defs/operation", "description": "Operation"}
            },
        }
        self.write_definition()
        self.assertTrue(
            any(
                "/$defs/operation/properties/name/description" in p
                for p in checklist.check_extension(self.extension)
            )
        )

    def test_readme_must_exist(self) -> None:
        self.readme.unlink()
        self.assertTrue(
            any("README.md" in p for p in checklist.check_extension(self.extension))
        )

    def test_readme_requires_complete_pairs_of_blocks(self) -> None:
        for text in (
            "No examples",
            "```go\nUse()\n```\n",
            "```\na\n```\n" * 3,
        ):
            with self.subTest(text=text):
                self.readme.write_text(text)
                self.assertTrue(
                    any(
                        "README.md" in p
                        for p in checklist.check_extension(self.extension)
                    )
                )

    def test_fences_support_tildes_longer_markers_and_indentation(self) -> None:
        self.readme.write_text("  ~~~go\nUse()\n  ~~~~\n````yaml\n```\ntext\n`````\n")
        self.assertEqual(checklist.check_extension(self.extension), [])

    def test_fence_markers_inside_a_block_do_not_count_as_extra_examples(self) -> None:
        self.readme.write_text("````markdown\n```go\nUse()\n```\n````\n")
        self.assertTrue(
            any("README.md" in p for p in checklist.check_extension(self.extension))
        )

    def test_newest_legacy_definition_is_checked(self) -> None:
        self.document["spec"]["interfaceFields"][0].pop("description")
        self.document["metadata"]["version"] = "v1alpha1"
        legacy = self.extension / "service-v1alpha1.yaml"
        legacy.write_text(yaml.safe_dump(self.document))
        self.assertTrue(
            any(
                "service-v1alpha1.yaml" in p
                for p in checklist.check_extension(self.extension)
            )
        )

    def test_unchanged_historical_release_does_not_block_a_documented_new_release(
        self,
    ) -> None:
        self.document["spec"]["interfaceFields"][0].pop("description")
        older = self.definition.with_name("runtimeconditions.extension.yaml")
        newer = self.extension / "releases/0.2.0/runtimeconditions.extension.yaml"
        newer.parent.mkdir(parents=True)
        newer.write_text(
            self.definition.read_text().replace("version: 0.1.0", "version: 0.2.0")
        )
        older.write_text(yaml.safe_dump(self.document))
        self.assertEqual(checklist.check_extension(self.extension), [])
        self.assertTrue(
            any(
                "0.1.0" in p for p in checklist.check_extension(self.extension, {older})
            )
        )

    def test_auxiliary_yaml_sequence_is_not_an_extension_definition(self) -> None:
        (self.extension / "example-values.yaml").write_text("- first\n- second\n")
        self.assertEqual(checklist.check_extension(self.extension), [])

    def test_code_blocks_nested_in_lists_and_blockquotes_are_counted(self) -> None:
        for prefix in ("1. Usage\n\n", "> Usage\n>\n"):
            indent = "    " if prefix.startswith("1.") else "> "
            with self.subTest(prefix=prefix):
                self.readme.write_text(
                    prefix
                    + "".join(
                        indent + line + "\n"
                        for line in (
                            "```go",
                            "Use()",
                            "```",
                            "",
                            "```yaml",
                            "kind: test",
                            "```",
                        )
                    )
                )
                self.assertEqual(checklist.check_extension(self.extension), [])

    def test_fences_inside_html_comments_are_not_counted(self) -> None:
        self.readme.write_text(
            "<!--\n```go\nUse()\n```\n```yaml\nkind: test\n```\n-->\n"
        )
        self.assertTrue(checklist.check_extension(self.extension))

    def test_invalid_yaml_and_missing_definitions_fail_without_a_traceback(
        self,
    ) -> None:
        for text in ("spec: [", "- not an object", "kind: Profile\n"):
            with self.subTest(text=text):
                self.definition.write_text(text)
                self.assertTrue(checklist.check_extension(self.extension))
        self.definition.unlink()
        self.assertTrue(checklist.check_extension(self.extension))


class GitSelectionTests(ExtensionFixture):
    def setUp(self) -> None:
        super().setUp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Checklist test")
        self.git("config", "user.email", "checklist@example.invalid")
        self.commit()
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], text=True
        ).strip()

    def commit(self) -> None:
        self.git("add", ".")
        self.git("commit", "-qm", "Test fixture")

    def test_readme_and_example_only_changes_select_the_extension_once(self) -> None:
        self.readme.write_text("Missing code blocks")
        (self.extension / "example.yaml").write_text("kind: Profile\n")
        self.commit()
        self.assertEqual(
            checklist.changed_extensions(
                self.root, checklist.changed_paths(self.root, self.base, "HEAD")
            ),
            [self.extension],
        )
        with redirect_stderr(StringIO()) as errors, redirect_stdout(StringIO()):
            result = checklist.main(
                ["--repo-root", str(self.root), "--base", self.base]
            )
        self.assertEqual(result, 1)
        self.assertIn("README.md", errors.getvalue())

    def test_unrelated_changes_do_not_check_existing_invalid_extensions(self) -> None:
        self.readme.write_text("Invalid but unchanged in the PR")
        self.commit()
        base = self.git("rev-parse", "HEAD")
        (self.root / "README.md").write_text("Unrelated")
        self.commit()
        self.assertEqual(
            checklist.changed_extensions(
                self.root, checklist.changed_paths(self.root, base, "HEAD")
            ),
            [],
        )
        with redirect_stdout(StringIO()):
            self.assertEqual(
                checklist.main(["--repo-root", str(self.root), "--base", base]), 0
            )

    def test_merge_base_excludes_changes_only_on_the_target_branch(self) -> None:
        self.git("switch", "-qc", "feature")
        (self.root / "feature.txt").write_text("Feature change")
        self.commit()
        self.git("switch", "-q", "main")
        self.readme.write_text("Changed only on main")
        self.commit()
        self.git("switch", "-q", "feature")
        self.assertEqual(
            checklist.changed_extensions(
                self.root, checklist.changed_paths(self.root, "main", "HEAD")
            ),
            [],
        )

    def test_rename_checks_both_surviving_extension_folders(self) -> None:
        destination = self.root / "catalog/vendor/other"
        shutil.copytree(self.extension, destination)
        self.commit()
        base = self.git("rev-parse", "HEAD")
        (self.extension / "README.md").rename(destination / "moved.md")
        self.commit()
        self.assertEqual(
            checklist.changed_extensions(
                self.root, checklist.changed_paths(self.root, base, "HEAD")
            ),
            [destination, self.extension],
        )

    def test_fully_deleted_extension_is_skipped(self) -> None:
        shutil.rmtree(self.extension)
        self.commit()
        self.assertEqual(
            checklist.changed_extensions(
                self.root, checklist.changed_paths(self.root, self.base, "HEAD")
            ),
            [],
        )

    def test_changed_historical_definition_is_checked_but_unchanged_one_is_preserved(
        self,
    ) -> None:
        newer = self.extension / "releases/0.2.0/runtimeconditions.extension.yaml"
        newer.parent.mkdir(parents=True)
        newer.write_text(
            self.definition.read_text().replace("version: 0.1.0", "version: 0.2.0")
        )
        self.document["spec"]["interfaceFields"][0].pop("description")
        self.write_definition()
        self.commit()
        base = self.git("rev-parse", "HEAD")
        with self.readme.open("a") as stream:
            stream.write("\nUpdated examples.\n")
        self.commit()
        with redirect_stdout(StringIO()):
            self.assertEqual(
                checklist.main(["--repo-root", str(self.root), "--base", base]), 0
            )
        self.document["spec"]["interfaceFields"][0]["description"] = "bad"
        self.write_definition()
        self.commit()
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as errors:
            self.assertEqual(
                checklist.main(["--repo-root", str(self.root), "--base", base]), 1
            )
        self.assertIn("releases/0.1.0/", errors.getvalue())

    def test_invalid_git_range_fails_instead_of_succeeding_with_no_changes(
        self,
    ) -> None:
        with redirect_stderr(StringIO()) as errors:
            result = checklist.main(
                ["--repo-root", str(self.root), "--base", "not-a-ref"]
            )
        self.assertEqual(result, 1)
        self.assertIn("git", errors.getvalue().lower())

    def test_cli_passes_valid_changes_and_fails_invalid_changes(self) -> None:
        with self.readme.open("a") as stream:
            stream.write("\nA documentation update.\n")
        self.commit()
        command = [
            sys.executable,
            str(Path(checklist.__file__)),
            "--repo-root",
            str(self.root),
            "--base",
            self.base,
            "--head",
            "HEAD",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 changed extension folder", result.stdout)
        self.readme.unlink()
        self.commit()
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.md", result.stderr)

    def test_valid_changed_extension_does_not_validate_untouched_invalid_folder(
        self,
    ) -> None:
        other = self.root / "catalog/vendor/untouched"
        other.mkdir()
        (other / "README.md").write_text("Invalid unchanged extension")
        self.commit()
        base = self.git("rev-parse", "HEAD")
        (self.extension / "notes with spaces.md").write_text("Review notes")
        self.commit()
        with redirect_stdout(StringIO()):
            self.assertEqual(
                checklist.main(["--repo-root", str(self.root), "--base", base]), 0
            )


if __name__ == "__main__":
    unittest.main()

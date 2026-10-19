"""Exercise shared target selection and direct-main commits against local Git remotes."""

from __future__ import annotations

from generation import commit, describe, git, of_language, select_targets
from testsupport import RepoTestCase, run_script


class SelectionTests(RepoTestCase):
    def test_defaults_select_every_enabled_language_and_sort_targets(self) -> None:
        self.assertEqual(
            [target[0] for target in select_targets(self.catalog, "")],
            ["addon:go", "owner:go", "owner:python"],
        )
        self.assertEqual(
            select_targets(self.catalog, "all"), select_targets(self.catalog, "")
        )

    def test_python_targets_carry_their_directory_and_exact_version(self) -> None:
        self.assertEqual(
            select_targets(self.catalog, "owner:python"),
            [("owner:python", "bindings/owner/python", "3.12.10")],
        )

    def test_a_language_filter_restricts_defaults_and_rejects_other_languages(
        self,
    ) -> None:
        self.assertEqual(
            [target[0] for target in select_targets(self.catalog, "", ("go",))],
            ["addon:go", "owner:go"],
        )
        with self.assertRaisesRegex(ValueError, "enables Go only"):
            select_targets(self.catalog, "owner:python", ("go",))

    def test_manual_selection_rejects_disabled_unknown_empty_and_duplicate_targets(
        self,
    ) -> None:
        for value in [
            "owner:ruby",
            "addon:python",
            "missing:go",
            "owner:go,",
            "owner:go,owner:go",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_targets(self.catalog, value)

    def test_selection_rejects_unexpected_directory_and_mixed_compilers(self) -> None:
        self.packages["owner"]["languages"]["go"]["sourceDirectory"] = "catalog"
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "source directory"):
            select_targets(self.catalog, "owner:go")
        self.packages["owner"]["languages"]["go"]["sourceDirectory"] = (
            "bindings/owner/go"
        )
        self.packages["owner"]["languages"]["go"]["languageVersion"] = "1.26.0"
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "one exact Go version"):
            select_targets(self.catalog, "")

    def test_selection_rejects_mixed_python_interpreters(self) -> None:
        self.packages["addon"]["languages"]["python"] = {
            "sourceDirectory": "bindings/addon/python",
            "languageVersion": "3.13.1",
        }
        self.write_catalog()
        select_targets(self.catalog, "addon:python")
        with self.assertRaisesRegex(ValueError, "one exact Python version"):
            select_targets(self.catalog, "addon:python,owner:python")

    def test_python_selection_rejects_unexpected_directory(self) -> None:
        self.packages["owner"]["languages"]["python"]["sourceDirectory"] = "catalog"
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "source directory"):
            select_targets(self.catalog, "owner:python")

    def test_describe_names_the_selected_languages(self) -> None:
        self.assertEqual(describe(select_targets(self.catalog, "owner:go")), "Go")
        self.assertEqual(
            describe(select_targets(self.catalog, "owner:python")), "Python"
        )
        self.assertEqual(describe(select_targets(self.catalog, "")), "Go and Python")

    def test_of_language_keeps_only_that_language(self) -> None:
        targets = select_targets(self.catalog, "")
        self.assertEqual(
            [target[0] for target in of_language(targets, "python")], ["owner:python"]
        )

    def test_configure_reports_the_selection_and_source_commit(self) -> None:
        values = run_script(
            "generation.py",
            self.root,
            self.root.parent / "github-output",
            "configure",
            "--targets",
            "owner:go,owner:python",
        )
        self.assertEqual(values["targets"], "owner:go,owner:python")
        self.assertEqual(values["source-commit"], self.source)


class CommitTests(RepoTestCase):
    def test_commit_adds_removes_and_pushes_only_selected_generated_source(
        self,
    ) -> None:
        (self.root / "bindings/owner/go/stale.go").unlink()
        self.write("bindings/owner/go/new.go", "new generated source\n")
        self.assertTrue(commit(self.root, self.targets, self.source))
        head = git(self.root, "rev-parse", "HEAD").strip()
        self.assertEqual(
            git(self.root, "ls-remote", "origin", "refs/heads/main").split()[0], head
        )
        self.assertEqual(git(self.root, "rev-parse", "HEAD^").strip(), self.source)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertEqual(
            git(self.root, "show", "HEAD:bindings/owner/python/source.py"),
            "unchanged Python source\n",
        )
        self.assertFalse(commit(self.root, self.targets, head))
        self.assertEqual(git(self.root, "rev-parse", "HEAD").strip(), head)

    def test_commit_rejects_input_or_unselected_output_changes(self) -> None:
        for path in [
            "catalog/input.yaml",
            "bindings/owner/python/new.py",
            "bindings/owner/go-other/file",
        ]:
            with self.subTest(path=path):
                self.write(path, "unexpected\n")
                with self.assertRaisesRegex(ValueError, "outside selected bindings"):
                    commit(self.root, self.targets, self.source)
                (self.root / path).unlink()
        self.assertEqual(git(self.root, "rev-parse", "HEAD").strip(), self.source)

    def test_commit_message_names_the_committed_languages(self) -> None:
        self.write("bindings/owner/go/new.go", "new Go source\n")
        self.write("bindings/owner/python/new.py", "new Python source\n")
        targets = select_targets(self.catalog, "owner:go,owner:python")
        self.assertTrue(commit(self.root, targets, self.source))
        self.assertEqual(
            git(self.root, "log", "-1", "--format=%s"),
            "chore(bindings): regenerate Go and Python bindings\n",
        )
        self.assertEqual(
            git(self.root, "show", "HEAD:bindings/owner/python/new.py"),
            "new Python source\n",
        )

    def test_python_commit_leaves_go_source_alone_and_rejects_its_changes(self) -> None:
        targets = select_targets(self.catalog, "owner:python")
        self.write("bindings/owner/python/new.py", "new Python source\n")
        self.write("bindings/owner/go/new.go", "unselected Go source\n")
        with self.assertRaisesRegex(ValueError, "outside selected bindings"):
            commit(self.root, targets, self.source)
        (self.root / "bindings/owner/go/new.go").unlink()
        self.assertTrue(commit(self.root, targets, self.source))
        self.assertEqual(
            git(self.root, "log", "-1", "--format=%s"),
            "chore(bindings): regenerate Python bindings\n",
        )
        self.assertEqual(
            git(self.root, "show", "HEAD:bindings/owner/go/stale.go"),
            "old generated source\n",
        )

    def test_commit_rejects_an_existing_index(self) -> None:
        self.write("bindings/owner/go/new.go", "generated\n")
        git(self.root, "add", "bindings/owner/go/new.go")
        with self.assertRaisesRegex(ValueError, "index must be empty"):
            commit(self.root, self.targets, self.source)

    def test_commit_rejects_moved_main_before_staging(self) -> None:
        other = self.root.parent / "other"
        git(self.root, "clone", "--branch", "main", str(self.remote), str(other))
        git(other, "config", "user.name", "Test")
        git(other, "config", "user.email", "test@example.invalid")
        (other / "new-input.yaml").write_text("new input\n", encoding="utf-8")
        git(other, "add", ".")
        git(other, "commit", "-m", "Concurrent input")
        git(other, "push", "origin", "HEAD:refs/heads/main")
        self.write("bindings/owner/go/new.go", "generated from older input\n")
        with self.assertRaisesRegex(ValueError, "main moved"):
            commit(self.root, self.targets, self.source)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")
        self.assertEqual(git(self.root, "rev-parse", "HEAD").strip(), self.source)


if __name__ == "__main__":
    import unittest

    unittest.main()

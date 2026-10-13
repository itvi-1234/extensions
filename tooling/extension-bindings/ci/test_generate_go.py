"""Exercise the Go generation script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from generation import select_targets
from testsupport import RepoTestCase, load_script, run_script

script = load_script("generate-go.py")


class GoGenerationTests(RepoTestCase):
    def test_configure_reports_the_exact_go_version(self) -> None:
        output = self.root.parent / "github-output"
        for targets in ["owner:go", "owner:go,owner:python", "owner:python"]:
            with self.subTest(targets=targets):
                values = run_script(
                    "generate-go.py", self.root, output, "configure", "--targets", targets
                )
                self.assertEqual(values, {"go-version": "1.25.0"})

    def test_a_python_only_run_still_provisions_the_generators_go_version(self) -> None:
        targets = select_targets(self.catalog, "owner:python")
        self.assertEqual(script.generator_version(self.catalog, targets), "1.25.0")
        self.packages["addon"]["languages"]["go"]["languageVersion"] = "1.26.0"
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "one exact Go version"):
            script.generator_version(self.catalog, targets)

    def test_update_passes_only_go_targets_to_the_generator(self) -> None:
        targets = select_targets(self.catalog, "")
        with patch.object(script.subprocess, "run") as run:
            script.update(self.root, targets, Path("rc"), Path("core.yaml"))
        arguments = run.call_args.args[0]
        self.assertEqual(
            [arguments[i + 1] for i, arg in enumerate(arguments) if arg == "--target"],
            ["addon:go", "owner:go"],
        )

    def test_update_does_nothing_without_go_targets(self) -> None:
        targets = select_targets(self.catalog, "owner:python")
        with patch.object(script.subprocess, "run") as run:
            script.update(self.root, targets, Path("rc"), Path("core.yaml"))
        run.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()

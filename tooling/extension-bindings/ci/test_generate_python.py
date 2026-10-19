"""Exercise the Python generation script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from generation import select_targets
from testsupport import RepoTestCase, load_script, run_script

script = load_script("generate-python.py")


class PythonGenerationTests(RepoTestCase):
    def test_configure_reports_the_version_and_whether_python_is_selected(self) -> None:
        output = self.root.parent / "github-output"
        for targets, version, has_python in [
            ("owner:python", "3.12.10", "true"),
            ("owner:go", "", "false"),
            ("owner:go,owner:python", "3.12.10", "true"),
        ]:
            with self.subTest(targets=targets):
                values = run_script(
                    "generate-python.py",
                    self.root,
                    output,
                    "configure",
                    "--targets",
                    targets,
                )
                self.assertEqual(
                    values, {"python-version": version, "has-python": has_python}
                )

    def test_update_refuses_python_targets_without_the_provisioned_tools(self) -> None:
        targets = select_targets(self.catalog, "owner:python")
        with patch.dict("os.environ", clear=True), self.assertRaisesRegex(
            ValueError, "RC_BINDINGS_PYTHON"
        ):
            script.update(self.root, targets, Path("rc"), Path("core.yaml"))
        wheel = Path(self.temp.name) / "profiler.whl"
        environment = {
            "RC_BINDINGS_PYTHON": "python",
            "RC_PYTHON_PROFILER_BIN": "profiler",
            "RC_PYTHON_PROFILER_ARTIFACT": str(wheel),
        }
        with patch.dict("os.environ", environment, clear=True), self.assertRaisesRegex(
            ValueError, "profiler wheel"
        ):
            script.update(self.root, targets, Path("rc"), Path("core.yaml"))

    def test_update_passes_only_python_targets_to_the_generator(self) -> None:
        wheel = Path(self.temp.name) / "profiler.whl"
        wheel.write_bytes(b"wheel")
        environment = {
            "RC_BINDINGS_PYTHON": "python",
            "RC_PYTHON_PROFILER_BIN": "profiler",
            "RC_PYTHON_PROFILER_ARTIFACT": str(wheel),
        }
        targets = select_targets(self.catalog, "")
        with patch.dict("os.environ", environment, clear=True), patch.object(
            script.subprocess, "run"
        ) as run:
            script.update(self.root, targets, Path("rc"), Path("core.yaml"))
        arguments = run.call_args.args[0]
        self.assertEqual(
            [arguments[i + 1] for i, arg in enumerate(arguments) if arg == "--target"],
            ["owner:python"],
        )

    def test_update_needs_no_tools_without_python_targets(self) -> None:
        targets = select_targets(self.catalog, "owner:go")
        with patch.dict("os.environ", clear=True), patch.object(
            script.subprocess, "run"
        ) as run:
            script.update(self.root, targets, Path("rc"), Path("core.yaml"))
        run.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()

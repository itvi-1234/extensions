"""Local Git fixture and script loader shared by the generation tests."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import yaml
from generation import git, select_targets

CI = Path(__file__).parent


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py").replace("-", "_"), CI / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(name: str, root: Path, output: Path, *args: str) -> dict[str, str]:
    output.write_text("", encoding="utf-8")
    subprocess.run(
        [sys.executable, str(CI / name), *args, "--root", str(root)],
        check=True,
        capture_output=True,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
    )
    return dict(
        line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()
    )


class RepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        summary = patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": ""})
        summary.start()
        self.addCleanup(summary.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="binding-generation-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout"
        self.root.mkdir()
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.invalid")
        self.catalog = self.root / "tooling/extension-bindings/packages.yaml"
        self.catalog.parent.mkdir(parents=True)
        self.packages = {
            "owner": {
                "languages": {
                    "go": {
                        "sourceDirectory": "bindings/owner/go",
                        "languageVersion": "1.25.0",
                    },
                    "python": {
                        "sourceDirectory": "bindings/owner/python",
                        "languageVersion": "3.12.10",
                    },
                }
            },
            "addon": {
                "languages": {
                    "go": {
                        "sourceDirectory": "bindings/addon/go",
                        "languageVersion": "1.25.0",
                    },
                }
            },
        }
        self.write_catalog()
        self.write("bindings/owner/go/stale.go", "old generated source\n")
        self.write("bindings/owner/python/source.py", "unchanged Python source\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "Initial inputs")
        self.remote = Path(self.temp.name) / "remote.git"
        git(self.root, "init", "--bare", str(self.remote))
        git(self.root, "remote", "add", "origin", str(self.remote))
        git(self.root, "push", "origin", "HEAD:refs/heads/main")
        self.source = git(self.root, "rev-parse", "HEAD").strip()
        self.targets = select_targets(self.catalog, "owner:go")

    def write(self, name: str, data: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")

    def write_catalog(self) -> None:
        self.catalog.write_text(
            yaml.safe_dump({"packages": self.packages}), encoding="utf-8"
        )

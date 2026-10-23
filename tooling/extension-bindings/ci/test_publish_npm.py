"""Exercise the npm publication script."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from generation import select_targets
from testsupport import RepoTestCase, load_script

script = load_script("publish-npm.py")


class NpmPublicationTests(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        for key, name in (("owner", "@example/owner"), ("addon", "@example/addon")):
            self.packages[key]["languages"]["typescript"] = {
                "coordinate": name,
                "name": name,
                "version": "0.1.0",
                "sourceDirectory": f"bindings/{key}/typescript",
                "languageVersion": "20.19.6",
                "publicationMode": "registry",
                "registryId": "npm",
            }
        self.write_catalog()
        self.package("addon", "@example/addon")
        self.package("owner", "@example/owner", {"@example/addon": "^0.1.0"})
        self.write("tooling/extension-bindings/emitters/typescript/node_modules/typescript/bin/tsc", "")
        self.targets = select_targets(self.catalog, "owner:typescript,addon:typescript")

    def package(self, key: str, name: str, dependencies: dict | None = None, version: str = "0.1.0") -> None:
        self.write(
            f"bindings/{key}/typescript/package.json",
            json.dumps({"name": name, "version": version, "dependencies": dependencies or {}}),
        )
        self.write(f"bindings/{key}/typescript/tsconfig.json", "{}")

    def commands(self, calls) -> list[list[str]]:
        return [call.args[0] for call in calls]

    def test_dependencies_are_published_before_their_dependents(self) -> None:
        packages = {
            "@example/owner": {"dependencies": {"@example/addon": "^0.1.0", "left-pad": "^1.0.0"}},
            "@example/addon": {},
            "@example/leaf": {"dependencies": {"@example/owner": "^0.1.0"}},
        }
        self.assertEqual(
            script.publication_order(packages),
            ["@example/addon", "@example/owner", "@example/leaf"],
        )
        packages["@example/addon"] = {"dependencies": {"@example/leaf": "^0.1.0"}}
        with self.assertRaisesRegex(ValueError, "cycle"):
            script.publication_order(packages)

    def test_trusted_publishing_needs_a_recent_npm(self) -> None:
        for version in ("11.5.1\n", "11.6.0", "12.0.0-pre.1"):
            script.check_npm_version(version)
        for version in ("10.8.2", "11.5.0"):
            with self.assertRaisesRegex(ValueError, "11.5.1 or later"):
                script.check_npm_version(version)

    def test_a_package_must_match_its_catalog_entry(self) -> None:
        self.package("owner", "@example/other")
        catalog = {"packages": self.packages}
        with self.assertRaisesRegex(ValueError, "catalog says"):
            script.read_package(self.root, catalog, self.targets[1])

    def test_a_dry_run_builds_and_checks_but_never_publishes(self) -> None:
        with patch.object(script, "run") as run, patch.object(
            script, "already_published"
        ) as published:
            script.publish(self.root, self.targets, False)
        commands = self.commands(run.call_args_list)
        self.assertFalse(any(command[:2] == ["npm", "publish"] for command in commands))
        self.assertEqual(sum(command[:2] == ["npm", "pack"] for command in commands), 2)
        builds = [command[3] for command in commands if command[0] == "node"]
        self.assertTrue(builds[0].endswith("node_modules/@example/addon/tsconfig.json"))
        self.assertTrue(builds[1].endswith("node_modules/@example/owner/tsconfig.json"))
        published.assert_not_called()

    def test_publication_skips_versions_that_are_already_on_npm(self) -> None:
        def run(command, cwd, **options):
            return SimpleNamespace(stdout="11.6.0\n")

        with patch.object(script, "run", side_effect=run) as runner, patch.object(
            script, "already_published", side_effect=lambda name, version: name == "@example/addon"
        ):
            script.publish(self.root, self.targets, True)
        publishes = [
            call for call in runner.call_args_list if call.args[0][:2] == ["npm", "publish"]
        ]
        self.assertEqual(len(publishes), 1)
        self.assertEqual(
            publishes[0].args[0], ["npm", "publish", "--access", "public", "--ignore-scripts"]
        )
        self.assertTrue(str(publishes[0].args[1]).endswith("node_modules/@example/owner"))

    def test_publication_refuses_an_old_npm(self) -> None:
        with patch.object(
            script, "run", return_value=SimpleNamespace(stdout="10.8.2\n")
        ), self.assertRaisesRegex(ValueError, "npm 11.5.1"):
            script.publish(self.root, self.targets, True)

    def test_publication_needs_the_emitter_dependencies(self) -> None:
        (self.root / "tooling/extension-bindings/emitters/typescript/node_modules/typescript/bin/tsc").unlink()
        with self.assertRaisesRegex(ValueError, "npm ci"):
            script.publish(self.root, self.targets, False)

    def test_other_languages_are_not_published(self) -> None:
        targets = select_targets(self.catalog, "owner:go")
        with patch.object(script, "run") as run:
            script.publish(self.root, targets, True)
        run.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()

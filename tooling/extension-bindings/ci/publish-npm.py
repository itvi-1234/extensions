"""Build the committed TypeScript bindings and publish them to npm with trusted publishing."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from generation import Target, of_language, select_targets, summarize

LANGUAGE = "typescript"
TOOLING = Path("tooling/extension-bindings")
EMITTER = TOOLING / "emitters/typescript"
MINIMUM_NPM = (11, 5, 1)


def read_package(root: Path, catalog: dict, target: Target) -> dict:
    """Read a committed package.json and check it against the catalog entry."""
    key, directory, _ = target
    package = json.loads((root / directory / "package.json").read_text(encoding="utf-8"))
    expected = catalog["packages"][key.split(":")[0]]["languages"][LANGUAGE]
    if package["name"] != expected["name"] or package["version"] != str(expected["version"]):
        raise ValueError(
            f"{key}: {directory}/package.json is "
            f"{package['name']}@{package['version']}, but the catalog says "
            f"{expected['name']}@{expected['version']}"
        )
    return package


def publication_order(packages: dict[str, dict]) -> list[str]:
    """Order package names so every selected dependency comes before its dependents."""
    ordered: list[str] = []
    state: dict[str, int] = {}

    def visit(name: str) -> None:
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            raise ValueError(f"package dependency cycle at {name}")
        state[name] = 1
        for dependency in sorted(packages[name].get("dependencies", {})):
            if dependency in packages:
                visit(dependency)
        state[name] = 2
        ordered.append(name)

    for name in sorted(packages):
        visit(name)
    return ordered


def check_npm_version(version: str) -> None:
    numbers = tuple(int(part) for part in version.strip().split("-")[0].split(".")[:3])
    if numbers < MINIMUM_NPM:
        raise ValueError(
            "trusted publishing needs npm "
            + ".".join(map(str, MINIMUM_NPM))
            + f" or later, but npm {version.strip()} is installed"
        )


def run(command: list[str], cwd: Path, **options) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, check=True, text=True, **options)


def already_published(name: str, version: str) -> bool:
    result = subprocess.run(
        ["npm", "view", f"{name}@{version}", "version"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == version


def publish(root: Path, targets: list[Target], execute: bool) -> None:
    selected = of_language(targets, LANGUAGE)
    if not selected:
        summarize("No TypeScript targets selected; nothing to publish.")
        return
    tsc = root / EMITTER / "node_modules/typescript/bin/tsc"
    if not tsc.is_file():
        raise ValueError(f"install the emitter dependencies first (npm ci in {root / EMITTER}): {tsc} is missing")
    if execute:
        check_npm_version(run(["npm", "--version"], root, capture_output=True).stdout)
    catalog = yaml.safe_load((root / TOOLING / "packages.yaml").read_text(encoding="utf-8"))
    packages = {}
    directories = {}
    for target in selected:
        package = read_package(root, catalog, target)
        packages[package["name"]] = package
        directories[package["name"]] = root / target[1]
    published = []
    with tempfile.TemporaryDirectory(prefix="npm-bindings-") as name:
        # Each package is built where its dependencies resolve, from the same
        # committed tree a consumer would receive.
        workspace = Path(name)
        for package_name in publication_order(packages):
            destination = workspace / "node_modules" / package_name
            shutil.copytree(directories[package_name], destination)
            run(["node", str(tsc), "-p", str(destination / "tsconfig.json")], root)
            run(["npm", "pack", "--dry-run", "--ignore-scripts"], destination, capture_output=True)
            version = packages[package_name]["version"]
            if not execute:
                summarize(f"Built and checked {package_name}@{version}; dry run, nothing was published.")
            elif already_published(package_name, version):
                summarize(f"{package_name}@{version} is already on npm; skipped.")
            else:
                run(["npm", "publish", "--access", "public", "--ignore-scripts"], destination)
                published.append(f"{package_name}@{version}")
                summarize(f"Published {package_name}@{version}.")
    if execute:
        summarize("Published to npm: " + (", ".join(published) if published else "nothing new."))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--targets", default="")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="publish; without it the packages are only built and checked",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        targets = select_targets(root / TOOLING / "packages.yaml", args.targets)
        publish(root, targets, args.execute)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr)
        parser.exit(1, f"npm publication failed: {error}\n")


if __name__ == "__main__":
    main()

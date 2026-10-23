"""Configure, update, and check TypeScript bindings for the Actions workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from generation import (
    Target,
    exact_version,
    of_language,
    select_targets,
    summarize,
    write_outputs,
)

LANGUAGE = "typescript"
TOOLING = Path("tooling/extension-bindings")
EMITTER = TOOLING / "emitters/typescript"
TARGET_API = "runtimeconditions.io/typescript-package-target/v1alpha1"
TARGET_KIND = "RuntimeConditionsTypeScriptPackageTarget"
FILE_MANIFEST = "runtimeconditions.file-manifest.yaml"
MODEL_FILE = "runtimeconditions.binding-model.yaml"
EXTENSION_FILE = "runtimeconditions.extension.yaml"
RESOURCES = "runtimeconditions"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def emitter_digest(emitter: Path) -> str:
    """Identify the emitter by its source, so the digest does not depend on a build."""
    names = ["package.json", "package-lock.json", "package-target.schema.yaml"]
    for folder, pattern in (("src", "*.ts"), ("templates", "*")):
        names += sorted(
            path.relative_to(emitter).as_posix()
            for path in (emitter / folder).glob(pattern)
            if path.is_file()
        )
    files = {name: sha256((emitter / name).read_bytes()) for name in names}
    return sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def file_manifest(directory: Path) -> str:
    """List every file except the manifest itself, in the format the Go tooling writes."""
    files = {
        path.relative_to(directory).as_posix(): sha256(path.read_bytes())
        for path in directory.rglob("*")
        if path.is_file() and path.name != FILE_MANIFEST
    }
    lines = [
        "apiVersion: runtimeconditions.io/file-manifest/v1alpha1",
        "kind: RuntimeConditionsFileManifest",
        "files:",
    ]
    for name in sorted(files, key=lambda item: item.encode("utf-8")):
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
            raise ValueError(f"unexpected generated file name: {name}")
        lines.append(f"    {name}: {files[name]}")
    return "\n".join(lines) + "\n"


def package_target(
    catalog: dict, key: str, model: dict, emitter_sha256: str
) -> dict:
    """Build the emitter's package target from the catalog and the normalized model."""
    package = catalog["packages"][key]
    config = package["languages"][LANGUAGE]
    root = package["rootExtension"]
    dependencies = []
    for edge in sorted(
        item["to"]
        for item in model.get("dependencyEdges") or []
        if item["from"] == root
    ):
        providers = [
            other["languages"][LANGUAGE]
            for other in catalog["packages"].values()
            if other["rootExtension"] == edge and LANGUAGE in other["languages"]
        ]
        if len(providers) != 1:
            raise ValueError(
                f"{key}:{LANGUAGE}: direct dependency {edge} requires exactly one "
                f"{LANGUAGE} catalog provider (found {len(providers)})"
            )
        dependencies.append(
            {
                "extension": edge,
                "packageName": providers[0]["name"],
                "version": str(providers[0]["version"]),
            }
        )
    target = {
        "apiVersion": TARGET_API,
        "kind": TARGET_KIND,
        "packageKey": key,
        "rootExtension": root,
        "packageName": config["name"],
        "version": str(config["version"]),
        "sourceDirectory": config["sourceDirectory"],
        "minimumNodeVersion": ".".join(str(config["languageVersion"]).split(".")[:2]),
        "publicationMode": config["publicationMode"],
        "repositoryUrl": catalog["repositoryUrl"],
        "dependencies": dependencies,
        "emitterSha256": emitter_sha256,
    }
    if "registryId" in config:
        target["registryId"] = config["registryId"]
    return target


def root_extension_source(root: Path, lock: dict, extension: str) -> bytes:
    """Read the root extension from the catalog, checking it against the dependency lock."""
    entries = [item for item in lock["extensions"] if item["id"] == extension]
    if len(entries) != 1:
        raise ValueError(f"the dependency lock must list {extension} exactly once")
    backend, _, locator = entries[0]["sourceLocator"].partition(":")
    if backend != "catalog":
        raise ValueError(f"{extension}: only catalog extension sources are supported")
    data = (root / "catalog" / locator).read_bytes()
    if sha256(data) != entries[0]["sourceSha256"]:
        raise ValueError(f"{extension}: catalog source differs from the dependency lock")
    return data


def tools(root: Path) -> tuple[str, Path]:
    node = os.environ.get("RC_BINDINGS_NODE", "node")
    main = Path(
        os.environ.get("RC_TYPESCRIPT_EMITTER", root / EMITTER / "dist/src/main.js")
    )
    if not main.is_file():
        raise ValueError(
            f"build the TypeScript emitter first (npm ci && npm run build in {root / EMITTER}): "
            f"{main} is missing"
        )
    return node, main


def generate(
    root: Path, catalog: dict, key: str, rc: Path, core: Path, work: Path
) -> Path:
    """Generate one verified package tree beneath work and return its directory."""
    node, main = tools(root)
    tooling = root / TOOLING
    model_path, lock_path = work / f"{key}.model.yaml", work / f"{key}.lock.yaml"
    subprocess.run(
        [
            str(rc.resolve()),
            "bindings",
            "normalize",
            "--packages",
            str(tooling / "packages.yaml"),
            "--toolchain-lock",
            str(tooling / "toolchain.lock.yaml"),
            "--core-schema",
            str(core.resolve()),
            "--target",
            f"{key}:{LANGUAGE}",
            "--output",
            str(model_path),
            "--dependency-lock-output",
            str(lock_path),
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    target = package_target(catalog, key, model, emitter_digest(root / EMITTER))
    target_path = work / f"{key}.target.yaml"
    target_path.write_text(yaml.safe_dump(target, sort_keys=False), encoding="utf-8")
    package = work / key
    common = ["--model", str(model_path), "--package-config", str(target_path)]
    subprocess.run(
        [node, str(main), "emit", *common, "--output", str(package)],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [node, str(main), "verify", *common, "--input", str(package)],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    resources = package / RESOURCES
    shutil.copyfile(model_path, resources / MODEL_FILE)
    (resources / EXTENSION_FILE).write_bytes(
        root_extension_source(root, lock, target["rootExtension"])
    )
    (package / FILE_MANIFEST).write_text(file_manifest(package), encoding="utf-8")
    return package


def tree(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def differences(expected: Path, actual: Path) -> list[str]:
    left, right = tree(expected), tree(actual) if actual.is_dir() else {}
    return [
        name
        for name in sorted(set(left) | set(right))
        if left.get(name) != right.get(name)
    ]


def run(
    root: Path, targets: list[Target], rc: Path, core: Path, synchronize: bool
) -> None:
    selected = of_language(targets, LANGUAGE)
    if not selected:
        summarize("No TypeScript targets selected; nothing to do.")
        return
    catalog = yaml.safe_load(
        (root / TOOLING / "packages.yaml").read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="typescript-bindings-") as name:
        for key, directory, _ in selected:
            package = generate(root, catalog, key.split(":")[0], rc, core, Path(name))
            destination = root / directory
            if synchronize:
                shutil.rmtree(destination, ignore_errors=True)
                shutil.copytree(package, destination)
            elif changed := differences(package, destination):
                raise ValueError(
                    f"{key}: generated source differs from {directory}: "
                    + ", ".join(changed)
                )
    verb = "Verified and synchronized" if synchronize else "Verified"
    summarize(f"{verb} {len(selected)} TypeScript binding targets.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["configure", "update", "check"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--targets", default="")
    parser.add_argument("--rc", type=Path)
    parser.add_argument("--core-schema", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        targets = select_targets(root / TOOLING / "packages.yaml", args.targets)
        if args.command == "configure":
            version = exact_version(targets, LANGUAGE)
            write_outputs(
                typescript_version=version,
                has_typescript="true" if version else "false",
            )
        else:
            if args.rc is None or args.core_schema is None:
                raise ValueError(f"{args.command} requires --rc and --core-schema")
            run(root, targets, args.rc, args.core_schema, args.command == "update")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"binding generation failed: {error}\n")


if __name__ == "__main__":
    main()

"""Configure and update verified Go bindings for the Actions workflow."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from generation import (
    Target,
    exact_version,
    git,
    load_targets,
    of_language,
    select_targets,
    summarize,
    write_outputs,
)

LANGUAGE = "go"


def generator_version(catalog: Path, targets: list[Target]) -> str:
    version = exact_version(targets, LANGUAGE)
    if version:
        return version
    versions = {
        target[2] for target in load_targets(catalog, (LANGUAGE,)).values()
    }
    if len(versions) != 1:
        raise ValueError("the shared generator requires one exact Go version")
    return versions.pop()


def update(root: Path, targets: list[Target], rc: Path, core: Path) -> None:
    selected = of_language(targets, LANGUAGE)
    if not selected:
        summarize("No Go targets selected; nothing to update.")
        return
    tooling = root / "tooling" / "extension-bindings"
    args = [
        str(rc.resolve()),
        "bindings",
        "update",
        "--packages",
        str(tooling / "packages.yaml"),
        "--toolchain-lock",
        str(tooling / "toolchain.lock.yaml"),
        "--core-schema",
        str(core.resolve()),
    ]
    for key, _, _ in selected:
        args.extend(["--target", key])
    subprocess.run(args, cwd=root, check=True)
    summarize(f"Verified and synchronized {len(selected)} Go binding targets.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["configure", "update"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--targets", default="")
    parser.add_argument("--rc", type=Path)
    parser.add_argument("--core-schema", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        catalog = root / "tooling/extension-bindings/packages.yaml"
        targets = select_targets(catalog, args.targets)
        if args.command == "configure":
            write_outputs(go_version=generator_version(catalog, targets))
        else:
            if args.rc is None or args.core_schema is None:
                raise ValueError("update requires --rc and --core-schema")
            update(root, targets, args.rc, args.core_schema)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"binding generation failed: {error}\n")


if __name__ == "__main__":
    main()

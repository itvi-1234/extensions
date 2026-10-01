"""Python identifier derivation and whole-plan symbol allocation."""

from __future__ import annotations

from dataclasses import dataclass
import builtins
import keyword
import unicodedata

from .package import fail


@dataclass(frozen=True)
class Symbol:
    key: str
    coordinate: str
    source: str
    style: str
    namespace: str = "module"
    parents: tuple[str, ...] = ()  # nearest canonical parent first
    fixed: bool = False


_HELPERS = {
    "ClassVar",
    "Literal",
    "Protocol",
    "Sequence",
    "StrEnum",
    "TypeAlias",
    "dataclass",
    "field",
    "annotations",
    "JSONValue",
}
_RESERVED = {
    **{name: f"python-builtin:{name}" for name in dir(builtins)},
    **{name: f"python-helper:{name}" for name in _HELPERS},
}


def _tokens(source: str) -> list[str]:
    source = unicodedata.normalize("NFKC", source)
    chunks: list[str] = []
    current = ""
    for index, character in enumerate(source):
        if not character.isalnum():
            if current:
                chunks.append(current)
                current = ""
            continue
        previous = source[index - 1] if index else ""
        following = source[index + 1] if index + 1 < len(source) else ""
        boundary = bool(current) and (
            character.isupper()
            and (previous.islower() or previous.isdigit())
            or character.isupper()
            and previous.isupper()
            and following.islower()
        )
        if boundary:
            chunks.append(current)
            current = ""
        current += character
    if current:
        chunks.append(current)
    return chunks


def python_name(source: str, style: str, coordinate: str) -> str:
    parts = _tokens(source)
    if not parts or style not in {"pascal", "snake", "upper"}:
        fail(
            "python-naming",
            "RCP2000",
            coordinate,
            f"cannot derive Python identifier from {source!r}",
        )
    if style == "pascal":
        name = "".join(part[:1].upper() + part[1:].lower() for part in parts)
    else:
        name = "_".join(
            part.lower() if style == "snake" else part.upper() for part in parts
        )
    if name[0].isdigit():
        name = ("X" if style == "pascal" else "x_") + name
    if source.startswith("__") and source.endswith("__"):
        name = "__" + name + "__"
    if keyword.iskeyword(name):
        name += "_"
    if name.startswith("__") and name.endswith("__"):
        name = "rc_" + name
    if not name.isidentifier():
        fail(
            "python-naming",
            "RCP2000",
            coordinate,
            f"invalid Python identifier {name!r}",
        )
    return name


def allocate_symbols(package_coordinate: str, symbols: list[Symbol]) -> dict[str, str]:
    """Allocate all namespaces before source emission, with canonical prefixes."""
    ordered = sorted(
        symbols, key=lambda item: (item.namespace, item.coordinate, item.key)
    )
    if len({item.key for item in ordered}) != len(ordered):
        fail(
            "python-naming",
            "RCP2001",
            package_coordinate,
            "duplicate symbol request key",
        )
    levels = {item.key: 0 for item in ordered}

    def candidate(item: Symbol) -> str:
        parts = list(reversed(item.parents[: levels[item.key]])) + [item.source]
        return python_name("_".join(parts), item.style, item.coordinate)

    for _ in range(
        len(ordered) * (max((len(item.parents) for item in ordered), default=0) + 1) + 1
    ):
        groups: dict[tuple[str, str], list[Symbol]] = {}
        for item in ordered:
            name = candidate(item)
            groups.setdefault((item.namespace, name), []).append(item)
        collisions: list[tuple[str, list[Symbol]]] = []
        for (namespace, name), group in sorted(groups.items()):
            reserved = _RESERVED.get(name) if namespace == "module" else None
            if len(group) > 1 or reserved:
                if reserved:
                    fail(
                        "python-naming",
                        "RCP2001",
                        package_coordinate,
                        f"symbol {name!r} conflicts: {group[0].coordinate} and {reserved}",
                    )
                if any(item.fixed for item in group):
                    pair = sorted(group, key=lambda item: item.coordinate)[:2]
                    fail(
                        "python-naming",
                        "RCP2001",
                        package_coordinate,
                        f"fixed symbol {name!r} conflicts: {pair[0].coordinate} and {pair[1].coordinate}",
                    )
                collisions.append((name, group))
        if not collisions:
            return {item.key: candidate(item) for item in ordered}
        for name, group in collisions:
            for item in group:
                if levels[item.key] == len(item.parents):
                    pair = sorted(group, key=lambda member: member.coordinate)[:2]
                    fail(
                        "python-naming",
                        "RCP2001",
                        package_coordinate,
                        f"symbol {name!r} conflicts after full path: {pair[0].coordinate} and {pair[1].coordinate}",
                    )
                levels[item.key] += 1
    raise AssertionError("symbol allocation did not converge")

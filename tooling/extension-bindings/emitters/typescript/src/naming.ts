import { fail } from "./diagnostics.js";

export type Style = "pascal" | "camel" | "exact";

export interface Symbol {
  readonly key: string;
  readonly coordinate: string;
  readonly source: string;
  readonly style: Style;
  readonly namespace?: string;
  readonly parents?: readonly string[];
  readonly fixed?: boolean;
}

const KEYWORDS = new Set([
  "abstract",
  "arguments",
  "await",
  "boolean",
  "break",
  "byte",
  "case",
  "catch",
  "char",
  "class",
  "const",
  "constructor",
  "continue",
  "debugger",
  "default",
  "delete",
  "do",
  "double",
  "else",
  "enum",
  "eval",
  "export",
  "extends",
  "false",
  "final",
  "finally",
  "float",
  "for",
  "function",
  "goto",
  "if",
  "implements",
  "import",
  "in",
  "instanceof",
  "int",
  "interface",
  "let",
  "long",
  "native",
  "new",
  "null",
  "package",
  "private",
  "protected",
  "prototype",
  "public",
  "return",
  "short",
  "static",
  "super",
  "switch",
  "synchronized",
  "this",
  "throw",
  "throws",
  "transient",
  "true",
  "try",
  "typeof",
  "var",
  "void",
  "volatile",
  "while",
  "with",
  "yield",
]);

const HELPERS = [
  "JSONValue",
  "Readonly",
  "ReadonlyArray",
  "Record",
  "Array",
  "Object",
  "String",
  "Number",
  "Boolean",
  "Map",
  "Set",
  "Date",
  "Error",
  "Function",
  "Promise",
  "Symbol",
  "JSON",
  "Math",
  "Partial",
  "Required",
  "Pick",
  "Omit",
  "Exclude",
  "Extract",
  "NonNullable",
  "Iterable",
  "Awaited",
  "BigInt",
  "RegExp",
  "Infinity",
  "NaN",
  "undefined",
  "globalThis",
];

const RESERVED = new Map<string, string>(
  HELPERS.map((name) => [name, `typescript-global:${name}`]),
);

const IDENTIFIER = /^[\p{ID_Start}$_][\p{ID_Continue}$‌‍]*$/u;
const ALNUM = /^[\p{L}\p{N}]$/u;
const UPPER = /^\p{Lu}$/u;
const LOWER = /^\p{Ll}$/u;
const DIGIT = /^\p{Nd}$/u;

function tokens(input: string): string[] {
  const characters = Array.from(input.normalize("NFKC"));
  const chunks: string[] = [];
  let current = "";
  characters.forEach((character, index) => {
    if (!ALNUM.test(character)) {
      if (current) {
        chunks.push(current);
        current = "";
      }
      return;
    }
    const previous = index > 0 ? characters[index - 1]! : "";
    const following = index + 1 < characters.length ? characters[index + 1]! : "";
    const boundary =
      current !== "" &&
      ((UPPER.test(character) && (LOWER.test(previous) || DIGIT.test(previous))) ||
        (UPPER.test(character) && UPPER.test(previous) && LOWER.test(following)));
    if (boundary) {
      chunks.push(current);
      current = "";
    }
    current += character;
  });
  if (current) chunks.push(current);
  return chunks;
}

function capitalize(part: string): string {
  const [first = "", ...rest] = Array.from(part);
  return first.toUpperCase() + rest.join("").toLowerCase();
}

export function typescriptName(source: string, style: Style, coordinate: string): string {
  if (style === "exact") {
    if (!IDENTIFIER.test(source)) {
      fail(
        "typescript-naming",
        "RCT2000",
        coordinate,
        `invalid TypeScript identifier ${JSON.stringify(source)}`,
      );
    }
    return source;
  }
  const parts = tokens(source);
  if (parts.length === 0) {
    fail(
      "typescript-naming",
      "RCT2000",
      coordinate,
      `cannot derive TypeScript identifier from '${source}'`,
    );
  }
  let name =
    style === "pascal"
      ? parts.map(capitalize).join("")
      : parts.map((part, index) => (index === 0 ? part.toLowerCase() : capitalize(part))).join("");
  if (DIGIT.test(Array.from(name)[0]!)) name = (style === "pascal" ? "X" : "x") + name;
  if (KEYWORDS.has(name)) name += "_";
  if (!IDENTIFIER.test(name)) {
    fail(
      "typescript-naming",
      "RCT2000",
      coordinate,
      `invalid TypeScript identifier ${JSON.stringify(name)}`,
    );
  }
  return name;
}

function compare(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function allocateSymbols(
  packageCoordinate: string,
  symbols: readonly Symbol[],
): Map<string, string> {
  const ordered = [...symbols].sort(
    (a, b) =>
      compare(a.namespace ?? "module", b.namespace ?? "module") ||
      compare(a.coordinate, b.coordinate) ||
      compare(a.key, b.key),
  );
  if (new Set(ordered.map((item) => item.key)).size !== ordered.length) {
    fail("typescript-naming", "RCT2001", packageCoordinate, "duplicate symbol request key");
  }
  const levels = new Map(ordered.map((item) => [item.key, 0]));
  const candidate = (item: Symbol): string => {
    const parents = [...(item.parents ?? []).slice(0, levels.get(item.key))].reverse();
    return typescriptName([...parents, item.source].join("_"), item.style, item.coordinate);
  };
  const maxDepth = Math.max(0, ...ordered.map((item) => item.parents?.length ?? 0));
  for (let round = 0; round < ordered.length * (maxDepth + 1) + 1; round += 1) {
    const groups = new Map<string, Symbol[]>();
    for (const item of ordered) {
      const groupKey = JSON.stringify([item.namespace ?? "module", candidate(item)]);
      groups.set(groupKey, [...(groups.get(groupKey) ?? []), item]);
    }
    const collisions: [string, Symbol[]][] = [];
    for (const [groupKey, group] of [...groups.entries()].sort(([a], [b]) => compare(a, b))) {
      const [namespace, name] = JSON.parse(groupKey) as [string, string];
      const reserved = namespace === "module" ? RESERVED.get(name) : undefined;
      if (group.length > 1 || reserved !== undefined) {
        const pair = [...group].sort((a, b) => compare(a.coordinate, b.coordinate)).slice(0, 2);
        if (reserved !== undefined) {
          fail(
            "typescript-naming",
            "RCT2001",
            packageCoordinate,
            `symbol '${name}' conflicts: ${group[0]!.coordinate} and ${reserved}`,
          );
        }
        if (group.some((item) => item.fixed)) {
          fail(
            "typescript-naming",
            "RCT2001",
            packageCoordinate,
            `fixed symbol '${name}' conflicts: ${pair[0]!.coordinate} and ${pair[1]!.coordinate}`,
          );
        }
        collisions.push([name, group]);
      }
    }
    if (collisions.length === 0) {
      return new Map(ordered.map((item) => [item.key, candidate(item)]));
    }
    for (const [name, group] of collisions) {
      for (const item of group) {
        if (levels.get(item.key) === (item.parents?.length ?? 0)) {
          const pair = [...group].sort((a, b) => compare(a.coordinate, b.coordinate)).slice(0, 2);
          fail(
            "typescript-naming",
            "RCT2001",
            packageCoordinate,
            `symbol '${name}' conflicts after full path: ${pair[0]!.coordinate} and ${pair[1]!.coordinate}`,
          );
        }
        levels.set(item.key, levels.get(item.key)! + 1);
      }
    }
  }
  throw new Error("symbol allocation did not converge");
}

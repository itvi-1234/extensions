import { closeSync, openSync, readSync } from "node:fs";
import {
  CST,
  Lexer,
  isAlias,
  isMap,
  isNode,
  isPair,
  isScalar,
  parseAllDocuments,
  visit,
} from "yaml";

import { fail } from "./diagnostics.js";

export const MAX_BYTES = 64 * 1024 * 1024;
export const MAX_NODES = 1_000_000;
export const MAX_DEPTH = 256;
export const MAX_ALIASES = 100;

export type JsonObject = Record<string, unknown>;

/** Reads at most `limit` bytes, so an oversized or endless input is never held in memory. */
function readAtMost(path: string, limit: number): Buffer {
  const descriptor = openSync(path, "r");
  try {
    const chunks: Buffer[] = [];
    let total = 0;
    while (total < limit) {
      const chunk = Buffer.allocUnsafe(Math.min(1024 * 1024, limit - total));
      const count = readSync(descriptor, chunk, 0, chunk.length, null);
      if (count === 0) break;
      chunks.push(chunk.subarray(0, count));
      total += count;
    }
    return Buffer.concat(chunks, total);
  } finally {
    closeSync(descriptor);
  }
}

function strictDecode(data: Buffer, coordinate: string): string {
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(data);
  } catch {
    return fail("input", "RCT1002", coordinate, "input is not valid UTF-8");
  }
}

function checkModelBytes(data: Buffer, coordinate: string): void {
  const startsWithBom = data[0] === 0xef && data[1] === 0xbb && data[2] === 0xbf;
  if (
    startsWithBom ||
    data.includes(0x0d) ||
    data[data.length - 1] !== 0x0a ||
    (data.length > 1 && data[data.length - 2] === 0x0a)
  ) {
    fail(
      "input",
      "RCT1002",
      coordinate,
      "binding model must use UTF-8 without BOM and LF with one trailing newline",
    );
  }
}

function checkModelTokens(source: string, coordinate: string): void {
  for (const token of new Lexer().lex(source)) {
    if (token.startsWith("#")) {
      fail("input", "RCT1002", coordinate, "binding model may not contain YAML comments");
    }
  }
  void CST;
}

function checkDataTree(value: unknown, coordinate: string): void {
  let count = 0;
  const visitValue = (node: unknown, depth: number): void => {
    count += 1;
    if (count > MAX_NODES) {
      fail("input", "RCT1002", coordinate, "decoded YAML node limit exceeded");
    }
    if (depth > MAX_DEPTH) {
      fail("input", "RCT1002", coordinate, "decoded YAML nesting limit exceeded");
    }
    if (typeof node === "number" && !Number.isFinite(node)) {
      fail("input", "RCT1002", coordinate, "non-finite YAML number");
    }
    if (Array.isArray(node)) {
      for (const child of node) visitValue(child, depth + 1);
    } else if (node !== null && typeof node === "object") {
      for (const child of Object.values(node)) visitValue(child, depth + 1);
    }
  };
  visitValue(value, 0);
}

export function loadYaml(path: string, model: boolean): JsonObject {
  const coordinate = model ? "model" : "package-target";
  let data: Buffer;
  try {
    data = readAtMost(path, MAX_BYTES + 1);
  } catch (error) {
    const reason = (error as NodeJS.ErrnoException).code ?? "unreadable";
    return fail("input", "RCT1001", coordinate, `cannot read YAML input: ${reason}`);
  }
  if (data.length > MAX_BYTES) {
    fail("input", "RCT1001", coordinate, "YAML input exceeds 64 MiB");
  }
  if (model) checkModelBytes(data, coordinate);
  const source = strictDecode(data, coordinate);
  if (model) checkModelTokens(source, coordinate);

  const documents = parseAllDocuments(source, { uniqueKeys: true, merge: false, version: "1.2" });
  const list = Array.isArray(documents) ? documents : [documents];
  if (list.length === 0) fail("input", "RCT1002", coordinate, "YAML document is empty");
  if (list.length > 1) {
    fail("input", "RCT1002", coordinate, "YAML input must contain exactly one document");
  }
  const document = list[0]!;
  const first = document.errors[0];
  if (first) fail("input", "RCT1002", coordinate, first.message.split("\n")[0] ?? first.message);
  if (document.contents === null) fail("input", "RCT1002", coordinate, "YAML document is empty");

  let nodes = 0;
  let aliases = 0;
  visit(document, (_key, node, path_) => {
    if (isPair(node)) return undefined;
    nodes += 1;
    if (nodes > MAX_NODES) fail("input", "RCT1002", coordinate, "YAML node limit exceeded");
    if (path_.length > MAX_DEPTH)
      fail("input", "RCT1002", coordinate, "YAML nesting limit exceeded");
    if (isAlias(node)) {
      aliases += 1;
      if (model) {
        fail("input", "RCT1002", coordinate, "binding model may not contain YAML aliases");
      }
      if (aliases > MAX_ALIASES) fail("input", "RCT1002", coordinate, "YAML alias limit exceeded");
    }
    if (isNode(node)) {
      if (model && "anchor" in node && node.anchor) {
        fail(
          "input",
          "RCT1002",
          coordinate,
          "binding model may not contain YAML anchors, aliases, or tags",
        );
      }
      if (model && "tag" in node && node.tag) {
        fail(
          "input",
          "RCT1002",
          coordinate,
          "binding model may not contain YAML anchors, aliases, or tags",
        );
      }
    }
    if (isMap(node)) {
      for (const pair of node.items) {
        const key = pair.key;
        if (!isScalar(key) || typeof key.value !== "string") {
          fail("input", "RCT1002", coordinate, "YAML mapping keys must be strings");
        }
      }
    }
    return undefined;
  });

  let value: unknown;
  try {
    value = document.toJS({ maxAliasCount: MAX_ALIASES });
  } catch (error) {
    return fail("input", "RCT1002", coordinate, (error as Error).message);
  }
  checkDataTree(value, coordinate);
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail("input", "RCT1002", coordinate, "YAML document must be a mapping");
  }
  return value as JsonObject;
}

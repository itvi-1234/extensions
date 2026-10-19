import assert from "node:assert/strict";
import { test } from "node:test";

import { DiagnosticError } from "../src/diagnostics.js";
import { allocateSymbols, typescriptName } from "../src/naming.js";

test("names are derived from tokens with Pascal and camel case", () => {
  const cases: [string, "pascal" | "camel", string][] = [
    ["base_url", "pascal", "BaseUrl"],
    ["base_url", "camel", "baseUrl"],
    ["HTTPServer", "pascal", "HttpServer"],
    ["requestBody Schema", "camel", "requestBodySchema"],
    ["key-value", "pascal", "KeyValue"],
    ["GET", "pascal", "Get"],
    ["3d", "pascal", "X3d"],
    ["3d", "camel", "x3d"],
    ["Ünï cøde", "pascal", "ÜnïCøde"],
  ];
  for (const [source, style, expected] of cases) {
    assert.equal(typescriptName(source, style, "coordinate"), expected);
  }
});

test("reserved words gain a trailing underscore", () => {
  assert.equal(typescriptName("delete", "camel", "c"), "delete_");
  assert.equal(typescriptName("class", "camel", "c"), "class_");
  assert.equal(typescriptName("constructor", "camel", "c"), "constructor_");
  assert.equal(typescriptName("default", "camel", "c"), "default_");
});

test("a source with no letters or digits has no identifier", () => {
  assert.throws(
    () => typescriptName("💥", "pascal", "c"),
    (error: unknown) => error instanceof DiagnosticError && error.diagnostic.code === "RCT2000",
  );
  assert.throws(() => typescriptName("---", "camel", "c"), DiagnosticError);
});

test("exact names must already be identifiers", () => {
  assert.equal(typescriptName("rcMarker_0123", "exact", "c"), "rcMarker_0123");
  assert.throws(() => typescriptName("not-valid", "exact", "c"), DiagnosticError);
});

test("collisions are resolved with parent path components, nearest first", () => {
  const names = allocateSymbols("pkg", [
    { key: "a", coordinate: "c1", source: "mode", style: "pascal", parents: ["http", "service"] },
    { key: "b", coordinate: "c2", source: "mode", style: "pascal", parents: ["grpc", "service"] },
  ]);
  assert.equal(names.get("a"), "HttpMode");
  assert.equal(names.get("b"), "GrpcMode");
});

test("a collision that survives the full path stops emission without renaming", () => {
  assert.throws(
    () =>
      allocateSymbols("pkg", [
        { key: "a", coordinate: "c1", source: "mode", style: "pascal", parents: ["x"] },
        { key: "b", coordinate: "c2", source: "Mode", style: "pascal", parents: ["x"] },
      ]),
    (error: unknown) =>
      error instanceof DiagnosticError && /after full path/.test(error.diagnostic.message),
  );
});

test("fixed symbols and TypeScript globals are never renamed", () => {
  assert.throws(
    () =>
      allocateSymbols("pkg", [
        { key: "a", coordinate: "c1", source: "service", style: "camel", fixed: true },
        { key: "b", coordinate: "c2", source: "Service", style: "camel", fixed: true },
      ]),
    (error: unknown) =>
      error instanceof DiagnosticError && /fixed symbol/.test(error.diagnostic.message),
  );
  assert.throws(
    () =>
      allocateSymbols("pkg", [{ key: "a", coordinate: "c1", source: "Promise", style: "pascal" }]),
    (error: unknown) =>
      error instanceof DiagnosticError &&
      /typescript-global:Promise/.test(error.diagnostic.message),
  );
  assert.throws(
    () =>
      allocateSymbols("pkg", [
        { key: "a", coordinate: "c1", source: "x", style: "pascal" },
        { key: "a", coordinate: "c2", source: "y", style: "pascal" },
      ]),
    (error: unknown) =>
      error instanceof DiagnosticError &&
      /duplicate symbol request key/.test(error.diagnostic.message),
  );
});

test("allocation is independent of input order", () => {
  const symbols = [
    { key: "a", coordinate: "c1", source: "mode", style: "pascal" as const, parents: ["http"] },
    { key: "b", coordinate: "c2", source: "mode", style: "pascal" as const, parents: ["grpc"] },
    { key: "c", coordinate: "c3", source: "other", style: "camel" as const },
  ];
  const forward = [...allocateSymbols("pkg", symbols).entries()].sort();
  const reversed = [...allocateSymbols("pkg", [...symbols].reverse()).entries()].sort();
  assert.deepEqual(forward, reversed);
});

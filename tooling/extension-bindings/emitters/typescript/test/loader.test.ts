import assert from "node:assert/strict";
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { stringify } from "yaml";

import { DiagnosticError } from "../src/diagnostics.js";
import { loadModel } from "../src/model.js";
import { loadTarget } from "../src/target.js";
import { modelPath, temporaryDirectory, TARGET } from "./support.js";

const GOOD = readFileSync(modelPath("01-owned-kind-interface"), "utf-8");

function expectDiagnostic(action: () => unknown, code: string, message?: RegExp): void {
  assert.throws(action, (error: unknown) => {
    assert.ok(error instanceof DiagnosticError, String(error));
    assert.equal(error.diagnostic.code, code, error.message);
    if (message) assert.match(error.diagnostic.message, message);
    return true;
  });
}

function withFile(content: string, action: (path: string) => void): void {
  const directory = temporaryDirectory();
  try {
    const path = join(directory, "input.yaml");
    writeFileSync(path, content);
    action(path);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("the committed conformance model loads", () => {
  withFile(GOOD, (path) => assert.equal(loadModel(path)["kind"], "RuntimeConditionsBindingModel"));
});

test("a binding model rejects a BOM, CRLF, and missing or doubled trailing newlines", () => {
  const cases: [string, RegExp][] = [
    [`﻿${GOOD}`, /without BOM and LF/],
    [GOOD.replace(/\n/g, "\r\n"), /without BOM and LF/],
    [GOOD.replace(/\n$/, ""), /without BOM and LF/],
    [`${GOOD}\n`, /without BOM and LF/],
  ];
  for (const [content, message] of cases) {
    withFile(content, (path) => expectDiagnostic(() => loadModel(path), "RCT1002", message));
  }
});

test("a binding model rejects comments, anchors, aliases, tags, and duplicate keys", () => {
  const withComment = GOOD.replace(
    "kind: RuntimeConditionsBindingModel",
    "kind: RuntimeConditionsBindingModel # note",
  );
  withFile(withComment, (path) => expectDiagnostic(() => loadModel(path), "RCT1002", /comments/));
  withFile(`# leading\n${GOOD}`, (path) =>
    expectDiagnostic(() => loadModel(path), "RCT1002", /comments/),
  );
  withFile(
    GOOD.replace("kind: RuntimeConditionsBindingModel", "kind: &a RuntimeConditionsBindingModel"),
    (path) => expectDiagnostic(() => loadModel(path), "RCT1002", /anchors/),
  );
  withFile(
    GOOD.replace(
      "kind: RuntimeConditionsBindingModel",
      "kind: !!str RuntimeConditionsBindingModel",
    ),
    (path) => expectDiagnostic(() => loadModel(path), "RCT1002", /tags/),
  );
  withFile(`${GOOD}kind: RuntimeConditionsBindingModel\n`, (path) =>
    expectDiagnostic(() => loadModel(path), "RCT1002"),
  );
  withFile(`x: &a 1\ny: *a\n`, (path) =>
    expectDiagnostic(() => loadModel(path), "RCT1002", /aliases/),
  );
});

test("a binding model rejects empty, multi-document, non-mapping, and non-string-key input", () => {
  withFile("\n", (path) => expectDiagnostic(() => loadModel(path), "RCT1002", /empty/));
  withFile("a: 1\n---\nb: 2\n", (path) =>
    expectDiagnostic(() => loadModel(path), "RCT1002", /exactly one document/),
  );
  withFile("- 1\n- 2\n", (path) => expectDiagnostic(() => loadModel(path), "RCT1002", /mapping/));
  withFile("1: x\n", (path) =>
    expectDiagnostic(() => loadModel(path), "RCT1002", /keys must be strings/),
  );
  withFile("a: .nan\n", (path) => expectDiagnostic(() => loadModel(path), "RCT1002", /non-finite/));
});

test("a missing file is reported as unreadable input", () => {
  expectDiagnostic(() => loadModel("/nonexistent/model.yaml"), "RCT1001", /cannot read/);
});

test("unsupported model versions and shapes are rejected with distinct codes", () => {
  const model = (change: (value: any) => void): string => {
    const value = JSON.parse(JSON.stringify(loadModel(modelPath("01-owned-kind-interface"))));
    change(value);
    return stringify(value);
  };
  withFile(
    model((value) => (value.apiVersion = "runtimeconditions.io/binding-model/v9")),
    (path) => expectDiagnostic(() => loadModel(path), "RCT1004"),
  );
  withFile(
    model((value) => (value.kind = "Other")),
    (path) => expectDiagnostic(() => loadModel(path), "RCT1005"),
  );
  withFile(
    model((value) => (value.schemas[0].projection.kind = "tuple")),
    (path) => expectDiagnostic(() => loadModel(path), "RCT1003"),
  );
  withFile(
    model((value) => delete value.vocabulary),
    (path) => expectDiagnostic(() => loadModel(path), "RCT1003"),
  );
  withFile(
    model((value) => (value.surprise = true)),
    (path) => expectDiagnostic(() => loadModel(path), "RCT1003"),
  );
});

test("package targets are validated field by field", () => {
  const base = readFileSync(TARGET, "utf-8");
  assert.equal(
    loadTarget(TARGET).packageName,
    "@runtimeconditions/conformance-owned-kind-interface",
  );
  const bad: [string, string, string, RegExp?][] = [
    ["packageKey: conformance-owned-kind-interface", "packageKey: Bad_Key", "RCT1006"],
    [
      "packageName: '@runtimeconditions/conformance-owned-kind-interface'",
      "packageName: 'Bad Name'",
      "RCT1006",
    ],
    ["version: 1.0.0", "version: 1.0", "RCT1006"],
    [
      "sourceDirectory: bindings/conformance-owned-kind-interface/typescript",
      "sourceDirectory: bindings/other/typescript",
      "RCT1007",
    ],
    ["minimumNodeVersion: '20.0'", "minimumNodeVersion: '18.0'", "RCT1008"],
    ["minimumNodeVersion: '20.0'", "minimumNodeVersion: '20'", "RCT1008"],
    ["publicationMode: github-tag", "publicationMode: registry", "RCT1006", /registryId/],
    ["publicationMode: github-tag", "publicationMode: other", "RCT1006"],
    [
      "repositoryUrl: https://github.com/runtimeconditions/extensions",
      "repositoryUrl: http://example.com/x",
      "RCT1006",
    ],
    ["kind: RuntimeConditionsTypeScriptPackageTarget", "kind: Other", "RCT1006"],
  ];
  for (const [from, to, code, message] of bad) {
    assert.ok(base.includes(from), from);
    withFile(base.replace(from, to), (path) =>
      expectDiagnostic(() => loadTarget(path), code, message),
    );
  }
  withFile(`${base}extra: 1\n`, (path) =>
    expectDiagnostic(() => loadTarget(path), "RCT1006", /unknown field 'extra'/),
  );
  withFile(base.replace(/^repositoryUrl:.*\n/m, ""), (path) =>
    expectDiagnostic(() => loadTarget(path), "RCT1006", /missing required field/),
  );
  withFile(`${base}emitterSha256: nothex\n`, (path) =>
    expectDiagnostic(() => loadTarget(path), "RCT1006", /emitterSha256/),
  );
  withFile(`${base}registryId: pypi\n`, (path) =>
    expectDiagnostic(() => loadTarget(path), "RCT1006", /registryId/),
  );
  const dependency = (entry: string): string => `${base}dependencies:\n${entry}`;
  withFile(
    dependency(
      "  - extension: a\n    packageName: dep\n    version: 1.0.0\n  - extension: a\n    packageName: dep2\n    version: 1.0.0\n",
    ),
    (path) => expectDiagnostic(() => loadTarget(path), "RCT1006", /duplicate dependency/),
  );
  withFile(dependency("  - extension: a\n    packageName: dep\n"), (path) =>
    expectDiagnostic(() => loadTarget(path), "RCT1006", /missing dependency field/),
  );
  withFile(dependency("  - extension: a\n    packageName: Bad\n    version: 1.0.0\n"), (path) =>
    expectDiagnostic(() => loadTarget(path), "RCT1006", /invalid dependency/),
  );
  withFile(dependency("  - bad\n"), (path) =>
    expectDiagnostic(() => loadTarget(path), "RCT1006", /mapping/),
  );
});

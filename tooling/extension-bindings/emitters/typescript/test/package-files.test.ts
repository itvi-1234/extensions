import assert from "node:assert/strict";
import { readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { verifyPackage } from "../src/verification.js";
import { buildCase, temporaryDirectory } from "./support.js";

const CASE = "03-transitive-closure";

async function expectRejected(
  name: string,
  change: (directory: string) => void,
  message: RegExp,
): Promise<void> {
  const workspace = temporaryDirectory();
  try {
    const built = await buildCase(CASE, workspace);
    verifyPackage(built.plan, built.directory, built.model);
    change(built.directory);
    assert.throws(() => verifyPackage(built.plan, built.directory, built.model), message, name);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
}

function edit(directory: string, file: string, from: RegExp | string, to: string): void {
  const path = join(directory, file);
  const text = readFileSync(path, "utf-8");
  const changed = text.replace(from, to);
  assert.notEqual(changed, text, `${file} was not changed`);
  writeFileSync(path, changed);
}

test("verify compares package.json and tsconfig.json with the target and model", async () => {
  await expectRejected(
    "missing package.json",
    (directory) => unlinkSync(join(directory, "package.json")),
    /package\.json is missing from the package/,
  );
  await expectRejected(
    "changed name",
    (directory) => edit(directory, "package.json", /"name": "[^"]+"/, '"name": "other"'),
    /package\.json differs from the package target and normalized model/,
  );
  await expectRejected(
    "dropped dependency",
    (directory) =>
      edit(directory, "package.json", /"dependencies": \{[^}]*\}/, '"dependencies": {}'),
    /package\.json differs/,
  );
  await expectRejected(
    "weaker compiler options",
    (directory) => edit(directory, "tsconfig.json", '"strict": true', '"strict": false'),
    /tsconfig\.json differs/,
  );
});

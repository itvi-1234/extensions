import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { Ajv2020 } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";

import { PRETTIER_VERSION, TYPESCRIPT_VERSION } from "../src/metadata.js";
import { renderPackage } from "../src/source.js";
import { EMITTER_ROOT, TARGET, TOOLING, buildCase, temporaryDirectory } from "./support.js";
import { rmSync } from "node:fs";

function validator(path: string) {
  const ajv = new Ajv2020({ strict: false, allowUnionTypes: true });
  addFormats.default(ajv);
  return ajv.compile(parse(readFileSync(path, "utf-8")) as object);
}

const manifestSchema = validator(
  join(TOOLING, "model/runtimeconditions.binding-manifest.schema.yaml"),
);

test("the package-target schema accepts the test target and rejects drift", () => {
  const validate = validator(join(EMITTER_ROOT, "package-target.schema.yaml"));
  const target = parse(readFileSync(TARGET, "utf-8")) as Record<string, unknown>;
  assert.ok(validate(target), JSON.stringify(validate.errors));
  for (const change of [
    { sourceDirectory: "bindings/other/python" },
    { minimumNodeVersion: "18.0" },
    { packageName: "Bad Name" },
    { publicationMode: "registry" },
    { extra: true },
  ]) {
    assert.equal(validate({ ...target, ...change }), false, JSON.stringify(change));
  }
});

test("every emitted manifest validates against the shared binding-manifest schema", async () => {
  const workspace = temporaryDirectory();
  try {
    for (const name of [
      "01-owned-kind-interface",
      "02-additive-field",
      "06-recursive-reference",
      "08-heterogeneous-union",
      "09-collections-and-maps",
      "10-scoped-domains-collisions",
    ]) {
      const built = await buildCase(name, workspace);
      const files = await renderPackage(built.plan, built.model);
      const manifest = parse(files["runtimeconditions/runtimeconditions.bindings.yaml"]!);
      assert.ok(manifestSchema(manifest), `${name}: ${JSON.stringify(manifestSchema.errors?.[0])}`);
    }
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("the manifest schema keeps each language's identity separate", async () => {
  const workspace = temporaryDirectory();
  try {
    const built = await buildCase("01-owned-kind-interface", workspace);
    const files = await renderPackage(built.plan, built.model);
    const manifest = parse(files["runtimeconditions/runtimeconditions.bindings.yaml"]!) as any;
    const mutations: [string, (value: any) => void][] = [
      [
        "a TypeScript manifest needs minimumNodeVersion",
        (value) => delete value.package.minimumNodeVersion,
      ],
      [
        "a TypeScript manifest cannot carry a Python version",
        (value) => (value.package.minimumPythonVersion = "3.12"),
      ],
      [
        "a TypeScript manifest cannot name a Python file",
        (value) => (value.declarations[0].file = "bindings.py"),
      ],
      [
        "an npm package name must be a valid npm name",
        (value) => (value.package.name = "Bad Name"),
      ],
      ["an unknown language is rejected", (value) => (value.package.language = "ruby")],
    ];
    for (const [description, change] of mutations) {
      const copy = structuredClone(manifest);
      change(copy);
      assert.equal(manifestSchema(copy), false, description);
    }
    const python = structuredClone(manifest);
    python.package = {
      language: "python",
      coordinate: "x",
      name: "x",
      version: "1.0.0",
      minimumNodeVersion: "20.0",
    };
    assert.equal(manifestSchema(python), false, "a Python manifest cannot carry a Node version");
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("the emitter's tool pins equal the shared toolchain lock", () => {
  const lock = parse(readFileSync(join(TOOLING, "toolchain.lock.yaml"), "utf-8")) as any;
  const tools = lock.languages.typescript.tools;
  assert.equal(tools.typescript, TYPESCRIPT_VERSION);
  assert.equal(tools.prettier, PRETTIER_VERSION);
  const manifest = JSON.parse(readFileSync(join(EMITTER_ROOT, "package.json"), "utf-8"));
  for (const [name, version] of Object.entries(tools)) {
    assert.equal(manifest.dependencies[name], version, `${name} dependency matches the lock`);
  }
  assert.equal(lock.languages.typescript.packageManager, "npm");
});

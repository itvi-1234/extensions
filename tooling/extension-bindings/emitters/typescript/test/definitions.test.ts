import assert from "node:assert/strict";
import { readFileSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { DiagnosticError } from "../src/diagnostics.js";
import { loadModel, type Model } from "../src/model.js";
import { emitPackage } from "../src/source.js";
import { verifyPackage } from "../src/verification.js";
import {
  modelPath,
  planFor,
  runTsc,
  temporaryDirectory,
  writeConformance,
  type BuiltCase,
} from "./support.js";

const CASE = "06-recursive-reference";

function provenance(base: any, pointer: string): any {
  return { ...base, jsonPointer: pointer };
}

function reference(base: any, pointer: string, target: string): any {
  return { kind: "ref", ref: `#/$defs/${target}`, provenance: provenance(base, pointer) };
}

function addDefinition(definitions: any[], base: any, name: string, shape: any): void {
  definitions.push({
    name,
    jsonPointer: `/$defs/${name}`,
    shape,
    provenance: provenance(base, `/$defs/${name}`),
  });
}

function addProperty(properties: any[], base: any, name: string, shape: any): void {
  properties.push({
    name,
    required: true,
    shape,
    provenance: provenance(base, `/$defs/node/properties/${name}`),
  });
}

function modelWithScalarDefinitions(
  extra: (definitions: any[], base: any, properties: any[]) => void,
): Model {
  const model = loadModel(modelPath(CASE));
  const definitions: any[] = model["schemas"][0].definitions;
  const node = definitions[0];
  const base = node.provenance;
  addDefinition(definitions, base, "label", {
    kind: "scalar",
    scalar: "string",
    provenance: provenance(base, "/$defs/label"),
  });
  addDefinition(definitions, base, "anything", {
    kind: "any",
    provenance: provenance(base, "/$defs/anything"),
  });
  addDefinition(definitions, base, "labelAlias", reference(base, "/$defs/labelAlias", "label"));
  addDefinition(
    definitions,
    base,
    "labelAliasAlias",
    reference(base, "/$defs/labelAliasAlias", "labelAlias"),
  );
  const properties: any[] = node.shape.properties;
  addProperty(properties, base, "label", reference(base, "/$defs/node/properties/label", "label"));
  addProperty(
    properties,
    base,
    "anything",
    reference(base, "/$defs/node/properties/anything", "anything"),
  );
  addProperty(
    properties,
    base,
    "chained",
    reference(base, "/$defs/node/properties/chained", "labelAliasAlias"),
  );
  addProperty(properties, base, "labels", {
    kind: "array",
    items: reference(base, "/$defs/node/properties/labels/items", "labelAlias"),
    provenance: provenance(base, "/$defs/node/properties/labels"),
  });
  extra(definitions, base, properties);
  return model;
}

test("scalar, any, and chained definitions keep their resolved types", async () => {
  const workspace = temporaryDirectory();
  try {
    const model = modelWithScalarDefinitions(() => undefined);
    const plan = planFor(model, CASE);
    const directory = join(workspace, "pkg");
    await emitPackage(plan, model, directory);
    verifyPackage(plan, directory, model);
    const built: BuiltCase = { directory, model, plan };
    writeConformance(built);
    const source = readFileSync(join(directory, "src/bindings.ts"), "utf-8");
    assert.ok(!source.includes("undefined"), "no undefined annotation");
    assert.match(source, /readonly label: string;/);
    assert.match(source, /readonly anything: JSONValue;/);
    assert.match(source, /readonly chained: string;/);
    assert.match(source, /export type Labels = ReadonlyArray<string>;/);
    const manifest = readFileSync(
      join(directory, "runtimeconditions/runtimeconditions.bindings.yaml"),
      "utf-8",
    );
    assert.ok(!manifest.includes("undefined"), "no undefined manifest type");
    const compiled = runTsc(directory, true);
    assert.equal(compiled.status, 0, compiled.output);
    assert.ok(readdirSync(directory).includes("package.json"));
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("a definition that only refers to itself is rejected", () => {
  const model = modelWithScalarDefinitions((definitions, base, properties) => {
    addDefinition(definitions, base, "loopA", reference(base, "/$defs/loopA", "loopB"));
    addDefinition(definitions, base, "loopB", reference(base, "/$defs/loopB", "loopA"));
    addProperty(properties, base, "loop", reference(base, "/$defs/node/properties/loop", "loopA"));
  });
  assert.throws(
    () => planFor(model, CASE),
    (error: unknown) => error instanceof DiagnosticError && error.diagnostic.code === "RCT1012",
  );
});

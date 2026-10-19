import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { parse } from "yaml";

import { DiagnosticError } from "../src/diagnostics.js";
import { createValidator, loadModel, modelSchemaPath, type Model } from "../src/model.js";
import { buildPlan } from "../src/plan.js";
import { EMITTER_ROOT, developmentTarget, modelPath } from "./support.js";

interface Fixture {
  case: string;
  positiveCase: string;
  expected: Record<string, string>;
}

function mutate(name: string, model: Model): void {
  if (name === "reserved-global") {
    model["schemas"][0].projection.properties[1].name = "record";
  } else if (name === "fixed-function-collision") {
    const second = structuredClone(model["vocabulary"].ownedDeclarations[0]);
    second.coordinate = "kind:Service";
    second.kind = "Service";
    model["vocabulary"].ownedDeclarations.push(second);
  } else if (name === "enum-member-collision") {
    const shape = model["schemas"][0].projection.properties.find(
      (item: any) => item.name === "mode",
    ).shape;
    shape.values.push({ value: shape.values[0].value.toUpperCase() });
    const scoped = model["scopes"][0].projection.properties.find(
      (item: any) => item.name === "mode",
    ).shape;
    for (const key of Object.keys(scoped)) delete scoped[key];
    Object.assign(scoped, structuredClone(shape));
  } else if (name === "unnameable-field") {
    model["schemas"][0].projection.properties[1].name = "💥";
  } else {
    throw new Error(name);
  }
}

const fixtures = parse(
  readFileSync(join(EMITTER_ROOT, "testdata/negative-diagnostics.yaml"), "utf-8"),
) as Fixture[];

for (const fixture of fixtures) {
  test(`negative diagnostic: ${fixture.case}`, () => {
    const model = loadModel(modelPath(fixture.positiveCase));
    mutate(fixture.case, model);
    const validate = createValidator(modelSchemaPath()).getSchema("model")!;
    assert.ok(validate(model), "the mutated model must stay schema-valid");
    assert.throws(
      () => buildPlan(model, { ...developmentTarget(), rootExtension: model["rootExtension"].id }),
      (error: unknown) => {
        assert.ok(error instanceof DiagnosticError);
        const { category, code, coordinate, jsonPointer, message } = error.diagnostic;
        assert.deepEqual({ category, code, coordinate, jsonPointer, message }, fixture.expected);
        return true;
      },
    );
  });
}

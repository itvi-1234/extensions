import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Ajv2020 } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";

import { fail } from "./diagnostics.js";
import { loadYaml, type JsonObject } from "./yamlio.js";

export const MODEL_API = "runtimeconditions.io/binding-model/v1alpha1";
export const MODEL_KIND = "RuntimeConditionsBindingModel";

export type Model = Record<string, any>;

export function modelSchemaPath(): string {
  return (
    process.env["RC_BINDING_MODEL_SCHEMA"] ??
    fileURLToPath(
      new URL("../../../../model/runtimeconditions.binding-model.schema.yaml", import.meta.url),
    )
  );
}

export function createValidator(schemaPath: string): Ajv2020 {
  const ajv = new Ajv2020({ strict: true, allowUnionTypes: true, allErrors: false });
  addFormats.default(ajv);
  ajv.addKeyword("x-runtimeconditions-ordering");
  ajv.addSchema(parse(readFileSync(schemaPath, "utf-8")) as object, "model");
  return ajv;
}

let validator: Ajv2020 | undefined;

export function loadModel(path: string): Model {
  const model: JsonObject = loadYaml(path, true);
  if (model["apiVersion"] !== MODEL_API) {
    fail("model", "RCT1004", "model", "unsupported binding-model apiVersion", "/apiVersion");
  }
  if (model["kind"] !== MODEL_KIND) {
    fail("model", "RCT1005", "model", "unsupported binding-model kind", "/kind");
  }
  validator ??= createValidator(modelSchemaPath());
  const validate = validator.getSchema("model");
  if (validate === undefined) fail("model", "RCT1003", "model", "model schema is unavailable");
  if (!validate(model)) {
    const error = validate.errors?.[0];
    fail(
      "model",
      "RCT1003",
      "model",
      `${error?.message ?? "schema validation failed"}`,
      error?.instancePath ?? "",
    );
  }
  return model as Model;
}

import { parseArgs } from "node:util";

import { DiagnosticError } from "./diagnostics.js";
import { loadModel } from "./model.js";
import { buildPlan } from "./plan.js";
import { emitPackage } from "./source.js";
import { apiSurface, verifyPackage } from "./verification.js";
import { loadTarget } from "./target.js";
import { EMITTER_VERSION } from "./metadata.js";

const USAGE =
  "usage: runtimeconditions-binding-emitter-typescript emit|verify|api --model FILE --package-config FILE (--output DIR | --input DIR)";

export async function main(argv: readonly string[]): Promise<number> {
  const [command, ...rest] = argv;
  if (command === "--version") {
    process.stdout.write(`${EMITTER_VERSION}\n`);
    return 0;
  }
  try {
    if (command !== "emit" && command !== "verify" && command !== "api") {
      throw new Error(USAGE);
    }
    const { values } = parseArgs({
      args: rest,
      options: {
        model: { type: "string" },
        "package-config": { type: "string" },
        output: { type: "string" },
        input: { type: "string" },
        assembled: { type: "boolean", default: false },
      },
      strict: true,
    });
    let result: object;
    if (command === "api") {
      if (values.input === undefined) throw new Error(USAGE);
      result = { api: apiSurface(values.input) };
    } else {
      if (values.model === undefined || values["package-config"] === undefined)
        throw new Error(USAGE);
      const model = loadModel(values.model);
      const plan = buildPlan(model, loadTarget(values["package-config"]));
      if (command === "emit") {
        if (values.output === undefined) throw new Error(USAGE);
        await emitPackage(plan, model, values.output);
        result = { output: values.output };
      } else {
        if (values.input === undefined) throw new Error(USAGE);
        result = verifyPackage(plan, values.input, model);
      }
    }
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return 0;
  } catch (error) {
    if (error instanceof DiagnosticError || error instanceof Error) {
      process.stderr.write(`${error.message}\n`);
      return 1;
    }
    throw error;
  }
}

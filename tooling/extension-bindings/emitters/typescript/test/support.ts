import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { conformanceSource } from "../src/conformance.js";
import { loadModel, type Model } from "../src/model.js";
import { buildPlan, type EmissionPlan } from "../src/plan.js";
import { emitPackage } from "../src/source.js";
import { loadTarget, type PackageTarget } from "../src/target.js";

const here = dirname(fileURLToPath(import.meta.url));
export const EMITTER_ROOT = resolve(here, "../..");
export const TOOLING = resolve(EMITTER_ROOT, "../..");
export const MODELS = join(TOOLING, "model/conformance/expected");
export const TARGET = join(EMITTER_ROOT, "testdata/package-target.yaml");
export const TSC = join(EMITTER_ROOT, "node_modules/typescript/bin/tsc");

export const CASES = readdirSync(MODELS)
  .filter((name) => existsSync(join(MODELS, name, "runtimeconditions.binding-model.yaml")))
  .sort();

export function modelPath(name: string): string {
  return join(MODELS, name, "runtimeconditions.binding-model.yaml");
}

export function temporaryDirectory(): string {
  return mkdtempSync(join(tmpdir(), "rc-ts-emitter-"));
}

export function emitterDigest(): string {
  const files = [
    "package.json",
    ...readdirSync(join(EMITTER_ROOT, "src"))
      .filter((name) => name.endsWith(".ts"))
      .sort()
      .map((name) => `src/${name}`),
  ];
  const inventory = Object.fromEntries(
    files.map((path) => [
      path,
      createHash("sha256")
        .update(readFileSync(join(EMITTER_ROOT, path)))
        .digest("hex"),
    ]),
  );
  return createHash("sha256").update(JSON.stringify(inventory)).digest("hex");
}

export function developmentTarget(): PackageTarget {
  return { ...loadTarget(TARGET), emitterSha256: emitterDigest() };
}

export function rootOf(model: Model): string {
  return model["rootExtension"].id as string;
}

function directDependencies(model: Model): string[] {
  return model["extensions"].find((item: any) => item.id === rootOf(model)).dependencies ?? [];
}

export function targetFor(
  name: string,
  model: Model,
  providers: Map<string, string>,
): PackageTarget {
  return {
    ...developmentTarget(),
    packageKey: name,
    sourceDirectory: `bindings/${name}/typescript`,
    packageName: `@rc/${name}`,
    rootExtension: rootOf(model),
    dependencies: directDependencies(model).map((extension) => ({
      extension,
      packageName:
        providers.get(extension) ??
        `unresolved-${createHash("sha256").update(extension).digest("hex").slice(0, 8)}`,
      version: "1.0.0",
    })),
  };
}

export function planFor(model: Model, name = "case"): EmissionPlan {
  const providers = new Map<string, string>();
  for (const extension of directDependencies(model))
    providers.set(extension, `provider-${providers.size}`);
  return buildPlan(model, targetFor(name, model, providers));
}

export function runTsc(
  projectDirectory: string,
  noEmit: boolean,
): { status: number; output: string } {
  try {
    const output = execFileSync(
      process.execPath,
      [TSC, "-p", join(projectDirectory, "tsconfig.json"), ...(noEmit ? ["--noEmit"] : [])],
      {
        encoding: "utf-8",
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    return { status: 0, output };
  } catch (error) {
    const failure = error as { status?: number; stdout?: string; stderr?: string };
    return {
      status: failure.status ?? 1,
      output: `${failure.stdout ?? ""}${failure.stderr ?? ""}`,
    };
  }
}

export interface BuiltCase {
  readonly directory: string;
  readonly model: Model;
  readonly plan: EmissionPlan;
}

/** Declare the provider packages a consumer imports, from its plan, as type-only stubs. */
export function writeProviderStubs(
  plan: EmissionPlan,
  workspace: string,
  markerOverride?: string,
): void {
  const byProvider = new Map<string, EmissionPlan["importedDeclarations"][number][]>();
  for (const item of plan.importedDeclarations) {
    byProvider.set(item.providerPackage!, [...(byProvider.get(item.providerPackage!) ?? []), item]);
  }
  for (const [name, declarations] of byProvider) {
    const directory = join(workspace, "node_modules", name);
    mkdirSync(directory, { recursive: true });
    writeFileSync(
      join(directory, "package.json"),
      JSON.stringify({
        name,
        version: "1.0.0",
        type: "module",
        types: "./index.d.ts",
        exports: { ".": { types: "./index.d.ts" } },
      }),
    );
    const lines = ["export declare class Declaration {}"];
    for (const item of declarations) {
      lines.push(`export interface ${item.protocol} { ${markerOverride ?? item.method}(): void }`);
      lines.push(
        `export declare function ${item.function}(...fields: ${item.protocol}[]): Declaration;`,
      );
    }
    writeFileSync(join(directory, "index.d.ts"), `${lines.join("\n")}\n`);
  }
}

/** Emit a case into a workspace whose node_modules hold stubs of its direct providers. */
export async function buildCase(
  name: string,
  workspace: string,
  markerOverride?: string,
): Promise<BuiltCase> {
  const model = loadModel(modelPath(name));
  const providers = new Map<string, string>();
  for (const extension of directDependencies(model))
    providers.set(extension, `provider-${providers.size}`);
  const plan = buildPlan(model, targetFor(name, model, providers));
  writeProviderStubs(plan, workspace, markerOverride);
  const directory = join(workspace, "pkg", name);
  mkdirSync(dirname(directory), { recursive: true });
  await emitPackage(plan, model, directory);
  return { directory, model, plan };
}

export function writeConformance(built: BuiltCase): void {
  writeFileSync(
    join(built.directory, "src/_conformance.ts"),
    conformanceSource(built.plan, built.model),
    "utf-8",
  );
}

export function snapshot(directory: string): Record<string, string> {
  const result: Record<string, string> = {};
  const visit = (current: string): void => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "node_modules" && entry.name !== "dist") visit(path);
      } else {
        result[relative(directory, path)] = readFileSync(path, "utf-8");
      }
    }
  };
  visit(directory);
  return result;
}

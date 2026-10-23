import { existsSync, lstatSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import * as prettier from "prettier";

import { fail } from "./diagnostics.js";
import type { Model } from "./model.js";
import type { EmissionPlan, TypePlan } from "./plan.js";
import { header, renderResources } from "./metadata.js";
import { JSON_VALUE_ALIAS_RHS } from "./plan.js";
import { readTemplate } from "./templates.js";

function sourceHeader(model: Model): string {
  return `// ${header(model)}`;
}

function compare(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function exportedNames(plan: EmissionPlan): string[] {
  const names = new Set<string>(plan.declarations.length > 0 ? ["Declaration"] : []);
  for (const item of plan.types) names.add(item.name);
  for (const item of [...plan.declarations, ...plan.importedDeclarations]) {
    names.add(item.function);
    names.add(item.protocol);
  }
  if (plan.usesJsonValue) names.add("JSONValue");
  return [...names].sort(compare);
}

function renderObject(item: TypePlan): string[] {
  const lines: string[] = [];
  const implement = item.marker !== null ? ` implements ${item.marker.protocol}` : "";
  lines.push(`export class ${item.name}${implement} {`);
  for (const field of item.fields) {
    lines.push(`  readonly ${field.name}${field.required ? "" : "?"}: ${field.annotation};`);
  }
  if (item.fields.length > 0) {
    const parameter = item.fields
      .map((field) => `readonly ${field.name}${field.required ? "" : "?"}: ${field.annotation}`)
      .join("; ");
    const optional = item.fields.every((field) => !field.required) ? " = {}" : "";
    lines.push("", `  constructor(fields: { ${parameter} }${optional}) {`);
    for (const field of item.fields) lines.push(`    this.${field.name} = fields.${field.name};`);
    lines.push("  }");
  }
  if (item.marker !== null) {
    lines.push("", `  ${item.marker.method}(): void {}`);
  }
  lines.push("}");
  return lines;
}

function bindingsSource(plan: EmissionPlan, model: Model): string {
  const lines: string[] = [sourceHeader(model), ""];
  const imports = new Map<string, Set<string>>();
  const importedTypes = new Set<string>();
  for (const item of plan.importedDeclarations) {
    if (item.providerPackage === null) {
      fail(
        "model",
        "RCT1011",
        item.coordinate,
        "imported declaration has no direct dependency provider",
      );
    }
    const names = imports.get(item.providerPackage) ?? new Set<string>();
    names.add(item.function);
    names.add(item.protocol);
    importedTypes.add(item.protocol);
    imports.set(item.providerPackage, names);
  }
  for (const provider of [...imports.keys()].sort(compare)) {
    const specifiers = [...imports.get(provider)!]
      .sort(compare)
      .map((name) => (importedTypes.has(name) ? `type ${name}` : name));
    lines.push(`import { ${specifiers.join(", ")} } from ${JSON.stringify(provider)};`);
  }
  if (imports.size > 0) {
    const reexports = [...imports.values()].flatMap((names) => [...names]).sort(compare);
    lines.push(
      "",
      `export { ${reexports.map((name) => (importedTypes.has(name) ? `type ${name}` : name)).join(", ")} };`,
    );
  }
  if (plan.declarations.length > 0) lines.push("", "export class Declaration {}");
  for (const declaration of [...plan.declarations].sort((a, b) =>
    compare(a.protocol, b.protocol),
  )) {
    lines.push(
      "",
      `export interface ${declaration.protocol} {`,
      `  ${declaration.method}(): void;`,
      "}",
    );
  }
  if (plan.usesJsonValue) lines.push("", `export type JSONValue = ${JSON_VALUE_ALIAS_RHS};`);
  for (const item of [...plan.types].sort((a, b) => compare(a.name, b.name))) {
    lines.push("");
    if (item.kind === "enum") {
      lines.push(`export enum ${item.name} {`);
      for (const [name, value] of item.members) lines.push(`  ${name} = ${JSON.stringify(value)},`);
      lines.push("}");
    } else if (item.kind === "alias") {
      lines.push(`export type ${item.name} = ${item.annotation};`);
    } else {
      lines.push(...renderObject(item));
    }
  }
  for (const declaration of [...plan.declarations].sort((a, b) =>
    compare(a.function, b.function),
  )) {
    lines.push(
      "",
      `export function ${declaration.function}(...fields: ${declaration.protocol}[]): Declaration {`,
      "  void fields;",
      "  return new Declaration();",
      "}",
    );
  }
  lines.push("");
  return lines.join("\n");
}

function indexSource(model: Model): string {
  return `${sourceHeader(model)}\n\nexport * from "./bindings.js";\n`;
}

export const FORMAT_OPTIONS: prettier.Options = JSON.parse(readTemplate("prettier.json"));

export async function formatSource(source: string, filepath: string): Promise<string> {
  return prettier.format(source, { ...FORMAT_OPTIONS, filepath });
}

export async function renderSources(
  plan: EmissionPlan,
  model: Model,
): Promise<Record<string, string>> {
  if (
    model["metadata"].semanticSha256 !== plan.modelDigest ||
    model["rootExtension"].id !== plan.target.rootExtension
  ) {
    fail("model", "RCT1003", "model", "emission plan does not match supplied model");
  }
  const sources = {
    "src/index.ts": indexSource(model),
    "src/bindings.ts": bindingsSource(plan, model),
  };
  const formatted: Record<string, string> = {};
  for (const [path, source] of Object.entries(sources)) {
    try {
      formatted[path] = await formatSource(source, path);
    } catch (error) {
      fail(
        "toolchain",
        "RCT4002",
        plan.target.packageKey,
        `Prettier could not format ${path}: ${(error as Error).message.split("\n")[0]}`,
      );
    }
  }
  return formatted;
}

export async function renderPackage(
  plan: EmissionPlan,
  model: Model,
): Promise<Record<string, string>> {
  return { ...(await renderSources(plan, model)), ...renderResources(plan, model) };
}

export function writeFiles(
  files: Record<string, string>,
  plan: EmissionPlan,
  outputDirectory: string,
): string[] {
  let occupied = false;
  try {
    occupied =
      existsSync(outputDirectory) &&
      (lstatSync(outputDirectory).isSymbolicLink() ||
        !lstatSync(outputDirectory).isDirectory() ||
        readdirSync(outputDirectory).length > 0);
  } catch {
    fail("output", "RCT3002", plan.target.packageKey, "cannot inspect output directory");
  }
  if (occupied) {
    fail(
      "output",
      "RCT3001",
      plan.target.packageKey,
      "output directory must be new or empty and not a symbolic link",
    );
  }
  try {
    mkdirSync(outputDirectory, { recursive: true });
    for (const relative of Object.keys(files).sort(compare)) {
      const destination = join(outputDirectory, relative);
      mkdirSync(dirname(destination), { recursive: true });
      writeFileSync(destination, files[relative]!, { encoding: "utf-8", flag: "wx" });
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EEXIST") {
      fail(
        "output",
        "RCT3001",
        plan.target.packageKey,
        "output directory must be new or empty and not a symbolic link",
      );
    }
    fail("output", "RCT3002", plan.target.packageKey, "cannot write generated package files");
  }
  return Object.keys(files).sort(compare);
}

export async function emitPackage(
  plan: EmissionPlan,
  model: Model,
  outputDirectory: string,
): Promise<string[]> {
  return writeFiles(await renderPackage(plan, model), plan, outputDirectory);
}

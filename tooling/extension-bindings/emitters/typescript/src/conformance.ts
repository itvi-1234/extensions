import { DiagnosticError, fail } from "./diagnostics.js";
import type { Model } from "./model.js";
import { header } from "./metadata.js";
import type { EmissionPlan, TypeExpr, TypePlan } from "./plan.js";

function attempt(build: () => string): string | undefined {
  try {
    return build();
  } catch (error) {
    if (error instanceof DiagnosticError) return undefined;
    throw error;
  }
}

function sample(
  expression: TypeExpr,
  plan: EmissionPlan,
  types: ReadonlyMap<string, TypePlan>,
  active: readonly string[] = [],
  selectedOptional: string | null = null,
): string {
  switch (expression.kind) {
    case "string":
    case "any":
      return '"sample"';
    case "boolean":
      return "true";
    case "integer":
    case "number":
      return "1";
    case "null":
      return "null";
    case "array":
      return attempt(() => `[${sample(expression.arguments[0]!, plan, types, active)}]`) ?? "[]";
    case "map":
      return (
        attempt(() => `{ sample: ${sample(expression.arguments[0]!, plan, types, active)} }`) ??
        "{}"
      );
    case "union": {
      let last: unknown;
      for (const variant of expression.arguments) {
        try {
          return sample(variant, plan, types, active);
        } catch (error) {
          if (!(error instanceof DiagnosticError)) throw error;
          last = error;
        }
      }
      throw last;
    }
    default:
  }
  const name = plan.names.get(expression.symbolKey)!;
  const type = types.get(name)!;
  if (type.kind === "enum") return `b.${name}.${type.members[0]![0]}`;
  if (type.kind === "alias") {
    if (active.includes(name)) {
      fail("model", "RCT1012", type.coordinate, "recursive alias has no finite conformance sample");
    }
    return sample(type.expression!, plan, types, [...active, name]);
  }
  const repeated = active.includes(name);
  const optional = type.fields.filter((field) => !field.required).map((field) => field.name);
  const selected = selectedOptional ?? optional[0] ?? null;
  const entries: string[] = [];
  for (const field of type.fields) {
    if (!field.required) {
      if (!repeated && field.name === selected) {
        entries.push(`${field.name}: ${sample(field.typeExpr, plan, types, [...active, name])}`);
      }
      continue;
    }
    if (repeated && ["object", "ref", "alias"].includes(field.typeExpr.kind)) {
      fail(
        "model",
        "RCT1012",
        field.coordinate,
        "required recursive field has no finite conformance sample",
      );
    }
    entries.push(`${field.name}: ${sample(field.typeExpr, plan, types, [...active, name])}`);
  }
  return `new b.${name}(${type.fields.length > 0 ? `{ ${entries.join(", ")} }` : ""})`;
}

function fieldGroups(fields: readonly TypePlan[]): TypePlan[][] {
  const groups = new Map<string, TypePlan[]>();
  for (const field of fields)
    groups.set(field.schemaCoordinate, [...(groups.get(field.schemaCoordinate) ?? []), field]);
  const result = [...groups.keys()]
    .sort()
    .map((key) => [...groups.get(key)!].sort((a, b) => (a.name < b.name ? -1 : 1)));
  return result.length > 0 ? result : [[]];
}

export function conformanceSource(plan: EmissionPlan, model: Model): string {
  const lines = [
    `// ${header(model)}`,
    "",
    'import * as b from "./bindings.js";',
    "",
    "export function exercise(): void {",
  ];
  if (plan.usesJsonValue) {
    lines.push(
      '  const _jsonScalar: b.JSONValue = "sample";',
      '  const _jsonArray: b.JSONValue = ["sample"];',
      '  const _jsonMap: b.JSONValue = { sample: "sample" };',
    );
  }
  const types = new Map(plan.types.map((item) => [item.name, item]));
  const objectVariables = new Map<string, string>();
  const alternates = new Map<string, string[]>();
  const ordered = [...plan.types].sort((a, b) => (a.name < b.name ? -1 : 1));
  ordered.forEach((type, index) => {
    if (type.kind === "enum") {
      type.members.forEach(([member], memberIndex) => {
        lines.push(
          `  const _enum${index}_${memberIndex}: b.${type.name} = b.${type.name}.${member};`,
        );
      });
    } else if (type.kind === "alias") {
      lines.push(
        `  const _alias${index}: b.${type.name} = ${sample(type.expression!, plan, types)};`,
      );
      if (type.expression!.kind === "union") {
        type.expression!.arguments.forEach((variant, variantIndex) => {
          lines.push(
            `  const _variant${index}_${variantIndex}: b.${type.name} = ${sample(variant, plan, types)};`,
          );
        });
      }
    } else {
      const key = [...plan.names.entries()].find(
        ([k, v]) => v === type.name && k.startsWith("type:"),
      )![0];
      const objectExpression: TypeExpr = { kind: "object", arguments: [], symbolKey: key };
      const variable = `_object${index}`;
      objectVariables.set(type.name, variable);
      lines.push(`  const ${variable}: b.${type.name} = ${sample(objectExpression, plan, types)};`);
      const optional = type.fields.filter((field) => !field.required).map((field) => field.name);
      optional.slice(1).forEach((name, offset) => {
        const alternate = `_objectOptional${index}_${offset + 1}`;
        alternates.set(type.name, [...(alternates.get(type.name) ?? []), alternate]);
        lines.push(
          `  const ${alternate}: b.${type.name} = ${sample(objectExpression, plan, types, [], name)};`,
        );
      });
    }
  });
  let declarationIndex = 0;
  for (const declaration of [...plan.declarations].sort((a, b) =>
    a.function < b.function ? -1 : 1,
  )) {
    const fields = plan.types.filter(
      (item) =>
        item.isDeclarationField &&
        item.marker !== null &&
        item.marker.owner === plan.target.rootExtension &&
        item.marker.protocol === declaration.protocol,
    );
    if (fields.length === 0) {
      lines.push(`  const _deferred_${declaration.function} = b.${declaration.function};`);
      continue;
    }
    for (const group of fieldGroups(fields)) {
      lines.push(
        `  const _declaration${declarationIndex}: b.Declaration = b.${declaration.function}(${group.map((item) => objectVariables.get(item.name)).join(", ")});`,
      );
      declarationIndex += 1;
      for (const item of group) {
        for (const alternate of alternates.get(item.name) ?? []) {
          const args = group.map((field) =>
            field.name === item.name ? alternate : objectVariables.get(field.name),
          );
          lines.push(
            `  const _declaration${declarationIndex}: b.Declaration = b.${declaration.function}(${args.join(", ")});`,
          );
          declarationIndex += 1;
        }
      }
    }
  }
  let importedIndex = 0;
  for (const declaration of [...plan.importedDeclarations].sort((a, b) =>
    a.function < b.function ? -1 : 1,
  )) {
    const fields = plan.types.filter(
      (item) =>
        item.isDeclarationField &&
        item.marker !== null &&
        item.marker.protocol === declaration.protocol,
    );
    if (fields.length === 0) {
      lines.push(`  const _deferredImported${importedIndex} = b.${declaration.function};`);
      importedIndex += 1;
      continue;
    }
    for (const group of fieldGroups(fields)) {
      lines.push(
        `  const _imported${importedIndex} = b.${declaration.function}(${group.map((item) => objectVariables.get(item.name)).join(", ")});`,
      );
      importedIndex += 1;
    }
  }
  lines.push("}", "");
  return lines.join("\n");
}

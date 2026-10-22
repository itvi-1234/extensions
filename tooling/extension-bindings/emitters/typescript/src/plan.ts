import { createHash } from "node:crypto";

import { fail } from "./diagnostics.js";
import type { Model } from "./model.js";
import { allocateSymbols, type Symbol } from "./naming.js";
import type { PackageTarget } from "./target.js";

export interface TypeExpr {
  readonly kind: string;
  readonly arguments: readonly TypeExpr[];
  readonly symbolKey: string;
}

export interface FieldPlan {
  readonly coordinate: string;
  readonly sourceName: string;
  readonly name: string;
  readonly typeExpr: TypeExpr;
  readonly annotation: string;
  readonly required: boolean;
}

export interface MarkerReference {
  readonly owner: string;
  readonly protocol: string;
  readonly method: string;
  readonly providerPackage: string | null;
}

export interface TypePlan {
  readonly coordinate: string;
  readonly name: string;
  readonly kind: "object" | "alias" | "enum";
  readonly fields: readonly FieldPlan[];
  readonly expression: TypeExpr | null;
  readonly annotation: string;
  readonly members: readonly (readonly [string, string])[];
  readonly marker: MarkerReference | null;
  readonly isDeclarationField: boolean;
  readonly schemaCoordinate: string;
  readonly sourceName: string;
}

export interface DeclarationPlan {
  readonly coordinate: string;
  readonly kind: string;
  readonly function: string;
  readonly protocol: string;
  readonly method: string;
}

export interface ImportedDeclarationPlan extends DeclarationPlan {
  readonly owner: string;
  readonly providerPackage: string | null;
}

export interface EmissionPlan {
  readonly target: PackageTarget;
  readonly names: ReadonlyMap<string, string>;
  readonly declarations: readonly DeclarationPlan[];
  readonly importedDeclarations: readonly ImportedDeclarationPlan[];
  readonly types: readonly TypePlan[];
  readonly usesJsonValue: boolean;
  readonly modelDigest: string;
}

export const JSON_VALUE_ALIAS_RHS =
  "string | number | boolean | null | ReadonlyArray<JSONValue> | { readonly [key: string]: JSONValue }";

const SCALAR_ANNOTATIONS: Record<string, string> = {
  string: "string",
  boolean: "boolean",
  integer: "number",
  number: "number",
  null: "null",
};

function expr(kind: string, args: readonly TypeExpr[] = [], symbolKey = ""): TypeExpr {
  return { kind, arguments: args, symbolKey };
}

/**
 * Replaces a reference to a definition that has no type of its own (a scalar, `any`, or another
 * reference) with that definition's expression, following chains. Objects, enums, and collections
 * keep their named reference.
 */
export function resolve(
  expression: TypeExpr,
  definitions: ReadonlyMap<string, TypeExpr>,
  active: readonly string[] = [],
): TypeExpr {
  if (expression.kind === "ref") {
    const key = expression.symbolKey;
    const definition = definitions.get(key);
    if (definition === undefined) {
      return fail("model", "RCT1012", key, "reference to a definition that was not planned");
    }
    if (definition.symbolKey === key) return expression;
    if (active.includes(key)) {
      return fail("model", "RCT1012", key, "definition refers to itself without a structure");
    }
    return resolve(definition, definitions, [...active, key]);
  }
  if (expression.arguments.length === 0) return expression;
  return {
    ...expression,
    arguments: expression.arguments.map((item) => resolve(item, definitions, active)),
  };
}

export function annotate(expression: TypeExpression, names: ReadonlyMap<string, string>): string {
  const { kind } = expression;
  if (kind in SCALAR_ANNOTATIONS) return SCALAR_ANNOTATIONS[kind]!;
  if (kind === "any") return "JSONValue";
  if (kind === "object" || kind === "enum" || kind === "ref" || kind === "alias") {
    return names.get(expression.symbolKey)!;
  }
  const inner = expression.arguments.map((item) => annotate(item, names));
  if (kind === "array") return `ReadonlyArray<${inner[0]}>`;
  if (kind === "map") return `{ readonly [key: string]: ${inner[0]} }`;
  if (kind === "union") return inner.join(" | ");
  throw new Error(`unplanned type kind ${kind}`);
}

type TypeExpression = TypeExpr;

function markerMethod(owner: string, coordinate: string): string {
  const digest = createHash("sha256").update(owner).update("\0").update(coordinate).digest("hex");
  return `rcMarker_${digest.slice(0, 16)}`;
}

function directDependencies(model: Model): Set<string> {
  const root = model["rootExtension"].id as string;
  for (const extension of model["extensions"]) {
    if (extension.id === root) return new Set<string>(extension.dependencies ?? []);
  }
  return fail("model", "RCT1011", root, "root extension is absent from resolved extension closure");
}

function providerPackage(model: Model, target: PackageTarget, owner: string): string {
  const graph = new Map<string, string[]>(
    model["extensions"].map((item: any) => [item.id, item.dependencies ?? []]),
  );
  const reaches = (current: string, visited: Set<string>): boolean => {
    if (current === owner) return true;
    if (visited.has(current)) return false;
    visited.add(current);
    return (graph.get(current) ?? []).some((dependency) => reaches(dependency, visited));
  };
  const dependencies = [...target.dependencies].sort((a, b) =>
    a.extension < b.extension ? -1 : 1,
  );
  for (const dependency of dependencies) {
    if (reaches(dependency.extension, new Set())) return dependency.packageName;
  }
  return fail("model", "RCT1011", owner, "imported declaration has no direct dependency provider");
}

function location(item: any): string {
  return item.provenance.coordinate + (item.provenance.jsonPointer ?? "");
}

interface RawType {
  kind: "object" | "alias" | "enum";
  shape: any;
  expression: TypeExpr | null;
  fields: [string, string, string, TypeExpr, boolean][];
  members: [string, string][];
  marker: MarkerReference | null;
}

export function buildPlan(model: Model, target: PackageTarget): EmissionPlan {
  const root: string = model["rootExtension"].id;
  const pkg = target.packageKey;
  if (root !== target.rootExtension) {
    fail(
      "package-config",
      "RCT1009",
      pkg,
      `target root '${target.rootExtension}' differs from model root '${root}'`,
      "/rootExtension",
    );
  }
  const direct = directDependencies(model);
  const configured = new Set(target.dependencies.map((item) => item.extension));
  if (JSON.stringify([...direct].sort()) !== JSON.stringify([...configured].sort())) {
    fail(
      "package-config",
      "RCT1009",
      pkg,
      `direct dependency set differs: model=${JSON.stringify([...direct].sort())}, target=${JSON.stringify([...configured].sort())}`,
      "/dependencies",
    );
  }
  const extensionIds = new Set<string>(model["extensions"].map((item: any) => item.id));
  if (![...configured].every((item) => extensionIds.has(item))) {
    fail("model", "RCT1011", root, "target dependency is absent from resolved closure");
  }

  const vocabulary = model["vocabulary"];
  const symbols: Symbol[] = [];
  const declarations: [string, string, string][] = [];
  const imported: (Omit<ImportedDeclarationPlan, "function" | "protocol"> & {
    functionKey: string;
    protocolKey: string;
  })[] = [];
  const importedKinds = new Map<string, (typeof imported)[number]>();
  const ownedKinds = new Map<string, string>();

  for (const item of vocabulary.ownedDeclarations ?? []) {
    const { coordinate, kind } = item;
    if (item.owner !== root)
      fail("model", "RCT1011", coordinate, "owned declaration has a foreign owner");
    if (ownedKinds.has(kind))
      fail("model", "RCT1011", coordinate, `duplicate owned kind '${kind}'`);
    ownedKinds.set(kind, coordinate);
    symbols.push(
      { key: `function:${coordinate}`, coordinate, source: kind, style: "camel", fixed: true },
      {
        key: `protocol:${coordinate}`,
        coordinate,
        source: `${kind} Field`,
        style: "pascal",
        fixed: true,
      },
    );
    declarations.push([coordinate, `function:${coordinate}`, `protocol:${coordinate}`]);
  }
  if (declarations.length > 0) {
    symbols.push({
      key: "builtin:Declaration",
      coordinate: "typescript:Declaration",
      source: "Declaration",
      style: "pascal",
      fixed: true,
    });
  }
  for (const item of vocabulary.importedDeclarations ?? []) {
    if (item.owner === root || !extensionIds.has(item.owner)) {
      fail("model", "RCT1011", item.coordinate, "invalid imported declaration owner");
    }
    const { coordinate } = item;
    const functionKey = `import:function:${coordinate}`;
    const protocolKey = `import:protocol:${coordinate}`;
    symbols.push(
      { key: functionKey, coordinate, source: item.kind, style: "camel", fixed: true },
      { key: protocolKey, coordinate, source: `${item.kind} Field`, style: "pascal", fixed: true },
    );
    const plan = {
      coordinate,
      owner: item.owner as string,
      kind: item.kind as string,
      functionKey,
      protocolKey,
      method: markerMethod(item.owner, coordinate),
      providerPackage: providerPackage(model, target, item.owner),
    };
    imported.push(plan);
    if (importedKinds.has(item.kind))
      fail("model", "RCT1011", coordinate, "duplicate imported kind");
    importedKinds.set(item.kind, plan);
  }

  const rawTypes = new Map<string, RawType>();
  const typeSources = new Map<string, string>();
  const declarationFieldSchemas = new Map<string, string>();
  let anyUsed = false;
  const definitionKeys = new Map<string, string>();
  const referencedDefinitions = new Set<string>();
  const definitionExpressions = new Map<string, TypeExpr>();
  const pendingDefinitions = new Map<string, [any, readonly string[], string]>();
  const ownedFieldRoots = new Set<string>(
    (vocabulary.conditionFields ?? [])
      .filter((item: any) => item.owner === root)
      .map((item: any) =>
        JSON.stringify([item.kind, item.interfaceType ?? "", item.segments[0].name]),
      ),
  );
  const scopeProjections = new Map<string, any>(
    (model["scopes"] ?? []).map((item: any) => [
      JSON.stringify([item.kind, item.interfaceType ?? ""]),
      item.projection ?? {},
    ]),
  );
  for (const schema of model["schemas"] ?? []) {
    for (const definition of schema.definitions ?? []) {
      definitionKeys.set(
        JSON.stringify([schema.coordinate, definition.jsonPointer]),
        `type:${schema.coordinate}:${definition.jsonPointer}`,
      );
    }
  }

  const registerShape = (
    shape: any,
    key: string,
    source: string,
    parents: readonly string[],
    marker: MarkerReference | null = null,
    exactSource: string | null = null,
  ): TypeExpr => {
    const coordinate = location(shape);
    const kind = shape.kind as string;
    const sourceName = exactSource ?? source;
    if (kind === "any") {
      anyUsed = true;
      return expr("any");
    }
    if (kind === "scalar") {
      const values: any[] = shape.values ?? [];
      if (values.length > 0 && shape.scalar === "string") {
        if (values.some((entry) => typeof entry.value !== "string")) {
          fail("model", "RCT1012", coordinate, "string domain contains non-string value");
        }
        symbols.push({ key, coordinate, source, style: "pascal", parents });
        const members: [string, string][] = [];
        values.forEach((entry, index) => {
          const memberKey = `member:${key}:${index}`;
          symbols.push({
            key: memberKey,
            coordinate: `${coordinate}#value:${entry.value}`,
            source: entry.value,
            style: "pascal",
            namespace: `enum:${key}`,
          });
          members.push([memberKey, entry.value]);
        });
        rawTypes.set(key, { kind: "enum", shape, expression: null, fields: [], members, marker });
        typeSources.set(key, sourceName);
        return expr("enum", [], key);
      }
      return expr(shape.scalar);
    }
    if (kind === "ref") {
      const referenceKey = definitionKeys.get(
        JSON.stringify([shape.provenance.coordinate, shape.ref.replace(/^#/, "")]),
      );
      if (referenceKey === undefined)
        fail("model", "RCT1012", coordinate, `unresolved reference '${shape.ref}'`);
      referencedDefinitions.add(referenceKey);
      return expr("ref", [], referenceKey);
    }
    if (kind === "object") {
      symbols.push({ key, coordinate, source, style: "pascal", parents });
      if (marker) {
        symbols.push({
          key: `method:${key}`,
          coordinate: marker.owner,
          source: marker.method,
          style: "exact",
          namespace: `fields:${key}`,
          fixed: true,
        });
      }
      const rawFields: RawType["fields"] = [];
      const required = new Set<string>(shape.required ?? []);
      const properties: any[] = shape.properties ?? [];
      const propertyNames = new Set(properties.map((item) => item.name as string));
      const missing = [...required].filter((name) => !propertyNames.has(name)).sort();
      if (missing.length > 0)
        fail(
          "model",
          "RCT1012",
          coordinate,
          `required properties are missing: ${JSON.stringify(missing)}`,
        );
      if (propertyNames.size !== properties.length)
        fail("model", "RCT1012", coordinate, "duplicate object property");
      for (const property of properties) {
        const { name } = property;
        const propertyCoordinate = location(property);
        const fieldKey = `field:${key}:${name}`;
        symbols.push({
          key: fieldKey,
          coordinate: propertyCoordinate,
          source: name,
          style: "camel",
          namespace: `fields:${key}`,
        });
        const expression = registerShape(property.shape, `type:${key}:${name}`, name, [
          source,
          ...parents,
        ]);
        rawFields.push([
          fieldKey,
          propertyCoordinate,
          name,
          expression,
          required.has(name) || property.required === true,
        ]);
      }
      rawTypes.set(key, {
        kind: "object",
        shape,
        expression: null,
        fields: rawFields,
        members: [],
        marker,
      });
      typeSources.set(key, sourceName);
      return expr("object", [], key);
    }
    if (kind === "array" || kind === "map" || kind === "union") {
      let children: any[];
      if (kind === "union") {
        children = shape.variants;
        if (children.length === 0) fail("model", "RCT1012", coordinate, "union has no variants");
      } else {
        children = [kind === "array" ? shape.items : shape.mapValues];
      }
      const expressions: TypeExpr[] = [];
      children.forEach((child, index) => {
        const suffix = kind === "array" ? "Item" : kind === "map" ? "Value" : `Variant${index + 1}`;
        const childSource = `${kind === "array" ? source.replace(/ Value$/, "") : source} ${suffix}`;
        expressions.push(
          registerShape(child, `type:${key}:${suffix}`, childSource, parents, null, sourceName),
        );
      });
      symbols.push({ key, coordinate, source, style: "pascal", parents });
      rawTypes.set(key, {
        kind: "alias",
        shape,
        expression: expr(kind, expressions),
        fields: [],
        members: [],
        marker,
      });
      typeSources.set(key, sourceName);
      return expr("alias", [], key);
    }
    return fail("model", "RCT1010", coordinate, `unknown structural node '${kind}'`);
  };

  for (const schema of model["schemas"] ?? []) {
    if (schema.owner !== root) continue;
    const schemaCoordinate: string = schema.coordinate;
    const kind: string = schema.kind ?? schema.id;
    const interfaceType: string | undefined = schema.interfaceType;
    const scope = [interfaceType, kind].filter((part): part is string => Boolean(part));
    let marker: MarkerReference | null = null;
    if (ownedKinds.has(kind)) {
      const declarationCoordinate = ownedKinds.get(kind)!;
      marker = {
        owner: root,
        protocol: `protocol:${declarationCoordinate}`,
        method: markerMethod(root, declarationCoordinate),
        providerPackage: null,
      };
    } else if (importedKinds.has(kind)) {
      const item = importedKinds.get(kind)!;
      marker = {
        owner: item.owner,
        protocol: item.protocolKey,
        method: item.method,
        providerPackage: item.providerPackage,
      };
    }
    const projection = schema.projection;
    if (projection.kind !== "object") {
      fail("model", "RCT1012", schemaCoordinate, "root condition projection must be an object");
    }
    for (const property of projection.properties ?? []) {
      const propertyName: string = property.name;
      const isInterface = propertyName === "interface" && Boolean(interfaceType);
      const fieldSource = isInterface ? interfaceType! : propertyName;
      const fieldParents = isInterface ? [propertyName, ...scope] : scope;
      const key = `type:field:${schemaCoordinate}:${propertyName}`;
      declarationFieldSchemas.set(key, schemaCoordinate);
      let shape = property.shape;
      if (ownedFieldRoots.has(JSON.stringify([kind, interfaceType ?? "", propertyName]))) {
        const scopeProperties: any[] =
          scopeProjections.get(JSON.stringify([kind, interfaceType ?? ""]))?.properties ?? [];
        const projected = scopeProperties.find((item) => item.name === propertyName);
        if (projected === undefined) {
          fail(
            "model",
            "RCT1012",
            schemaCoordinate,
            `condition field '${propertyName}' is absent from its scope projection`,
          );
        }
        shape = projected.shape;
      }
      if (shape.kind === "object") {
        registerShape(shape, key, fieldSource, fieldParents, marker);
        continue;
      }
      if (marker === null) {
        fail(
          "model",
          "RCT1011",
          schemaCoordinate,
          `field '${propertyName}' has no declaration contract`,
        );
      }
      const coordinate = location(property);
      symbols.push({
        key,
        coordinate,
        source: fieldSource,
        style: "pascal",
        parents: fieldParents,
      });
      symbols.push({
        key: `method:${key}`,
        coordinate: marker.owner,
        source: marker.method,
        style: "exact",
        namespace: `fields:${key}`,
        fixed: true,
      });
      const valueKey = `field:${key}:value`;
      symbols.push({
        key: valueKey,
        coordinate,
        source: "value",
        style: "camel",
        namespace: `fields:${key}`,
        fixed: true,
      });
      const fieldExpression = registerShape(
        shape,
        `type:${key}:value`,
        `${fieldSource} Value`,
        fieldParents,
      );
      rawTypes.set(key, {
        kind: "object",
        shape,
        expression: null,
        fields: [[valueKey, coordinate, "value", fieldExpression, true]],
        members: [],
        marker,
      });
      typeSources.set(key, fieldSource);
    }
    for (const definition of schema.definitions ?? []) {
      const definitionKey = definitionKeys.get(
        JSON.stringify([schemaCoordinate, definition.jsonPointer]),
      )!;
      pendingDefinitions.set(definitionKey, [definition, scope, schemaCoordinate]);
      if ((projection.properties ?? []).length === 0) referencedDefinitions.add(definitionKey);
    }
  }

  for (;;) {
    const required = [...referencedDefinitions]
      .filter((item) => pendingDefinitions.has(item))
      .sort();
    if (required.length === 0) break;
    for (const definitionKey of required) {
      const [definition, scope] = pendingDefinitions.get(definitionKey)!;
      pendingDefinitions.delete(definitionKey);
      definitionExpressions.set(
        definitionKey,
        registerShape(definition.shape, definitionKey, definition.name, scope),
      );
    }
  }

  const names = allocateSymbols(pkg, symbols);
  const types: TypePlan[] = [];
  for (const key of [...rawTypes.keys()].sort()) {
    const raw = rawTypes.get(key)!;
    const fields: FieldPlan[] = raw.fields.map(
      ([fieldKey, coordinate, sourceName, planned, required]) => {
        const typeExpr = resolve(planned, definitionExpressions);
        return {
          coordinate,
          sourceName,
          name: names.get(fieldKey)!,
          typeExpr,
          annotation: annotate(typeExpr, names),
          required,
        };
      },
    );
    fields.sort(
      (a, b) =>
        Number(!a.required) - Number(!b.required) ||
        (a.name < b.name ? -1 : a.name > b.name ? 1 : 0) ||
        (a.coordinate < b.coordinate ? -1 : a.coordinate > b.coordinate ? 1 : 0),
    );
    const expression = raw.expression ? resolve(raw.expression, definitionExpressions) : null;
    const annotation = expression ? annotate(expression, names) : "";
    types.push({
      coordinate: location(raw.shape),
      name: names.get(key)!,
      kind: raw.kind,
      fields,
      expression,
      annotation,
      members: raw.members.map(([memberKey, value]) => [names.get(memberKey)!, value] as const),
      marker: raw.marker
        ? {
            owner: raw.marker.owner,
            protocol: names.get(raw.marker.protocol)!,
            method: raw.marker.method,
            providerPackage: raw.marker.providerPackage,
          }
        : null,
      isDeclarationField: raw.marker !== null && raw.kind === "object",
      schemaCoordinate: declarationFieldSchemas.get(key) ?? "",
      sourceName: typeSources.get(key)!,
    });
  }
  const sortedDeclarations = [...declarations].sort((a, b) =>
    a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0,
  );
  const resultDeclarations: DeclarationPlan[] = sortedDeclarations.map(
    ([coordinate, functionKey, protocolKey]) => ({
      coordinate,
      kind: (vocabulary.ownedDeclarations as any[]).find((item) => item.coordinate === coordinate)
        .kind,
      function: names.get(functionKey)!,
      protocol: names.get(protocolKey)!,
      method: markerMethod(root, coordinate),
    }),
  );
  const resultImported: ImportedDeclarationPlan[] = [...imported]
    .sort((a, b) => (a.coordinate < b.coordinate ? -1 : a.coordinate > b.coordinate ? 1 : 0))
    .map((item) => ({
      coordinate: item.coordinate,
      owner: item.owner,
      kind: item.kind,
      function: names.get(item.functionKey)!,
      protocol: names.get(item.protocolKey)!,
      method: item.method,
      providerPackage: item.providerPackage,
    }));
  return {
    target,
    names,
    declarations: resultDeclarations,
    importedDeclarations: resultImported,
    types,
    usesJsonValue: anyUsed,
    modelDigest: model["metadata"].semanticSha256,
  };
}

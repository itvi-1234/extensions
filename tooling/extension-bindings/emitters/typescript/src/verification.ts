import { readFileSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";

import type { Model } from "./model.js";
import { renderResources } from "./metadata.js";
import type { EmissionPlan } from "./plan.js";

const MISMATCH = "native API or conformance mismatch";

function check(condition: boolean, description: string): void {
  if (!condition) throw new Error(`${MISMATCH}: ${description}`);
}

function parse(path: string): ts.SourceFile {
  return ts.createSourceFile(
    path,
    readFileSync(path, "utf-8"),
    ts.ScriptTarget.ES2022,
    true,
    ts.ScriptKind.TS,
  );
}

function squash(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function isExported(node: ts.Node): boolean {
  return (ts.getCombinedModifierFlags(node as ts.Declaration) & ts.ModifierFlags.Export) !== 0;
}

function exportedNames(source: ts.SourceFile): Set<string> {
  const names = new Set<string>();
  for (const statement of source.statements) {
    if (
      (ts.isClassDeclaration(statement) ||
        ts.isInterfaceDeclaration(statement) ||
        ts.isEnumDeclaration(statement) ||
        ts.isTypeAliasDeclaration(statement) ||
        ts.isFunctionDeclaration(statement)) &&
      isExported(statement) &&
      statement.name
    ) {
      names.add(statement.name.text);
    } else if (
      ts.isExportDeclaration(statement) &&
      statement.exportClause &&
      ts.isNamedExports(statement.exportClause)
    ) {
      for (const element of statement.exportClause.elements) names.add(element.name.text);
    }
  }
  return names;
}

function expectedNames(plan: EmissionPlan): Set<string> {
  const names = new Set(plan.types.map((item) => item.name));
  for (const declaration of [...plan.declarations, ...plan.importedDeclarations]) {
    names.add(declaration.function);
    names.add(declaration.protocol);
  }
  if (plan.declarations.length > 0) names.add("Declaration");
  if (plan.usesJsonValue) names.add("JSONValue");
  return names;
}

function sameSet(left: Set<string>, right: Set<string>): boolean {
  return left.size === right.size && [...left].every((item) => right.has(item));
}

function checkPublicApi(plan: EmissionPlan, directory: string): void {
  const index = parse(join(directory, "src/index.ts"));
  const bindings = parse(join(directory, "src/bindings.ts"));
  const reexports = index.statements.filter(ts.isExportDeclaration);
  check(
    reexports.length === 1 &&
      reexports[0]!.exportClause === undefined &&
      reexports[0]!.moduleSpecifier !== undefined &&
      ts.isStringLiteral(reexports[0]!.moduleSpecifier) &&
      reexports[0]!.moduleSpecifier.text === "./bindings.js",
    "index re-exports bindings",
  );
  check(sameSet(exportedNames(bindings), expectedNames(plan)), "exported names == expected");

  const classes = new Map<string, ts.ClassDeclaration>();
  const interfaces = new Map<string, ts.InterfaceDeclaration>();
  const enums = new Map<string, ts.EnumDeclaration>();
  const aliases = new Map<string, ts.TypeAliasDeclaration>();
  const functions = new Map<string, ts.FunctionDeclaration>();
  for (const statement of bindings.statements) {
    if (ts.isClassDeclaration(statement) && statement.name)
      classes.set(statement.name.text, statement);
    if (ts.isInterfaceDeclaration(statement)) interfaces.set(statement.name.text, statement);
    if (ts.isEnumDeclaration(statement)) enums.set(statement.name.text, statement);
    if (ts.isTypeAliasDeclaration(statement)) aliases.set(statement.name.text, statement);
    if (ts.isFunctionDeclaration(statement) && statement.name)
      functions.set(statement.name.text, statement);
  }
  const expectedClasses = new Set(
    plan.types.filter((item) => item.kind === "object").map((item) => item.name),
  );
  if (plan.declarations.length > 0) expectedClasses.add("Declaration");
  check(sameSet(new Set(classes.keys()), expectedClasses), "classes == object types + Declaration");
  check(
    sameSet(
      new Set(enums.keys()),
      new Set(plan.types.filter((item) => item.kind === "enum").map((item) => item.name)),
    ),
    "enums == enum types",
  );
  check(
    sameSet(new Set(interfaces.keys()), new Set(plan.declarations.map((item) => item.protocol))),
    "interfaces == declaration protocols",
  );
  check(
    sameSet(new Set(functions.keys()), new Set(plan.declarations.map((item) => item.function))),
    "functions == declaration functions",
  );
  const expectedAliases = new Set(
    plan.types.filter((item) => item.kind === "alias").map((item) => item.name),
  );
  if (plan.usesJsonValue) expectedAliases.add("JSONValue");
  check(sameSet(new Set(aliases.keys()), expectedAliases), "aliases == alias types + JSONValue");

  for (const declaration of plan.declarations) {
    const protocol = interfaces.get(declaration.protocol)!;
    const methods = protocol.members
      .filter(ts.isMethodSignature)
      .map((member) => (member.name as ts.Identifier).text);
    check(
      JSON.stringify(methods) === JSON.stringify([declaration.method]),
      "protocol has only the marker method",
    );
    const fn = functions.get(declaration.function)!;
    const parameters = fn.parameters;
    check(
      parameters.length === 1 && parameters[0]!.dotDotDotToken !== undefined,
      "declaration takes rest fields",
    );
    check(
      (parameters[0]!.name as ts.Identifier).text === "fields",
      "rest parameter is named fields",
    );
    check(
      squash(parameters[0]!.type!.getText()) === `${declaration.protocol}[]`,
      "rest parameter type is the protocol array",
    );
    check(
      fn.type !== undefined && squash(fn.type.getText()) === "Declaration",
      "declaration returns Declaration",
    );
  }
  for (const declaration of plan.importedDeclarations) {
    check(
      !functions.has(declaration.function) && !interfaces.has(declaration.protocol),
      "imported declaration is not redeclared",
    );
  }
  for (const item of plan.types) {
    if (item.kind === "alias") {
      check(
        squash(aliases.get(item.name)!.type.getText()) === item.annotation,
        `alias ${item.name} matches the plan`,
      );
      continue;
    }
    if (item.kind === "enum") {
      const members = enums
        .get(item.name)!
        .members.map((member) => [
          (member.name as ts.Identifier).text,
          (member.initializer as ts.StringLiteral).text,
        ]);
      check(
        JSON.stringify(members) === JSON.stringify(item.members),
        `enum ${item.name} members match the plan`,
      );
      continue;
    }
    const declaration = classes.get(item.name)!;
    const properties = declaration.members.filter(ts.isPropertyDeclaration);
    const actual = properties.map((property) => [
      (property.name as ts.Identifier).text,
      squash(property.type!.getText()),
      property.questionToken === undefined,
      property.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ReadonlyKeyword) ===
        true,
    ]);
    const expected = item.fields.map((field) => [
      field.name,
      field.annotation,
      field.required,
      true,
    ]);
    check(
      JSON.stringify(actual) === JSON.stringify(expected),
      `class ${item.name} fields match the plan`,
    );
    const markers = declaration.members
      .filter(ts.isMethodDeclaration)
      .map((member) => (member.name as ts.Identifier).text);
    check(
      JSON.stringify(markers) === JSON.stringify(item.marker ? [item.marker.method] : []),
      `class ${item.name} markers match the plan`,
    );
    const implemented = (declaration.heritageClauses ?? []).flatMap((clause) =>
      clause.types.map((type) => squash(type.getText())),
    );
    check(
      JSON.stringify(implemented) === JSON.stringify(item.marker ? [item.marker.protocol] : []),
      `class ${item.name} implements its marker`,
    );
  }
}

export function apiSurface(directory: string): string[] {
  const source = parse(join(directory, "src/bindings.ts"));
  const exports = exportedNames(source);
  const result: string[] = [];
  for (const statement of source.statements) {
    if (ts.isClassDeclaration(statement) && statement.name && exports.has(statement.name.text)) {
      const name = statement.name.text;
      const heritage = (statement.heritageClauses ?? []).flatMap((clause) =>
        clause.types.map((type) => squash(type.getText())),
      );
      result.push(`class|${name}|${heritage.join(",")}`);
      for (const member of statement.members) {
        if (ts.isPropertyDeclaration(member)) {
          result.push(
            `field|${name}|${(member.name as ts.Identifier).text}|${squash(member.type!.getText())}|${member.questionToken ? "optional" : "required"}`,
          );
        } else if (ts.isConstructorDeclaration(member)) {
          result.push(
            `constructor|${name}|${member.parameters.map((parameter) => squash(parameter.getText())).join(",")}`,
          );
        } else if (ts.isMethodDeclaration(member)) {
          result.push(
            `method|${name}|${(member.name as ts.Identifier).text}|${member.parameters.map((parameter) => squash(parameter.getText())).join(",")}|${member.type ? squash(member.type.getText()) : ""}`,
          );
        }
      }
    } else if (ts.isInterfaceDeclaration(statement) && exports.has(statement.name.text)) {
      result.push(`interface|${statement.name.text}`);
      for (const member of statement.members) {
        if (ts.isMethodSignature(member)) {
          result.push(
            `method|${statement.name.text}|${(member.name as ts.Identifier).text}|${member.parameters.map((parameter) => squash(parameter.getText())).join(",")}|${member.type ? squash(member.type.getText()) : ""}`,
          );
        }
      }
    } else if (ts.isEnumDeclaration(statement) && exports.has(statement.name.text)) {
      result.push(`enum|${statement.name.text}`);
      for (const member of statement.members) {
        result.push(`member|${statement.name.text}|${squash(member.getText())}`);
      }
    } else if (
      ts.isFunctionDeclaration(statement) &&
      statement.name &&
      exports.has(statement.name.text)
    ) {
      result.push(
        `function|${statement.name.text}|${statement.parameters.map((parameter) => squash(parameter.getText())).join(",")}|${statement.type ? squash(statement.type.getText()) : ""}`,
      );
    } else if (ts.isTypeAliasDeclaration(statement) && exports.has(statement.name.text)) {
      result.push(`alias|${statement.name.text}|${squash(statement.type.getText())}`);
    } else if (
      ts.isImportDeclaration(statement) &&
      statement.importClause?.namedBindings &&
      ts.isNamedImports(statement.importClause.namedBindings)
    ) {
      for (const element of statement.importClause.namedBindings.elements) {
        if (exports.has(element.name.text)) {
          result.push(
            `import|${(statement.moduleSpecifier as ts.StringLiteral).text}|${element.name.text}`,
          );
        }
      }
    }
  }
  return result.sort();
}

export function verifyPackage(
  plan: EmissionPlan,
  directory: string,
  model: Model,
): { api: string[]; modelMapping: boolean } {
  checkPublicApi(plan, directory);
  const expected = renderResources(plan, model)[
    "runtimeconditions/runtimeconditions.bindings.yaml"
  ];
  const actual = readFileSync(
    join(directory, "runtimeconditions/runtimeconditions.bindings.yaml"),
    "utf-8",
  );
  if (actual !== expected)
    throw new Error("binding manifest mappings differ from normalized model");
  return { api: apiSurface(directory), modelMapping: true };
}

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Ajv2020, type ErrorObject, type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";

import { fail } from "./diagnostics.js";
import { loadYaml, type JsonObject } from "./yamlio.js";

export interface PackageDependency {
  readonly extension: string;
  readonly packageName: string;
  readonly version: string;
  readonly versionRange?: string;
}

export interface PackageTarget {
  readonly packageKey: string;
  readonly rootExtension: string;
  readonly packageName: string;
  readonly version: string;
  readonly sourceDirectory: string;
  readonly minimumNodeVersion: string;
  readonly publicationMode: string;
  readonly repositoryUrl: string;
  readonly registryId: string | null;
  readonly dependencies: readonly PackageDependency[];
  readonly emitterSha256: string;
}

interface Described {
  readonly code: string;
  readonly message: string;
  readonly pointer: string;
}

export function targetSchemaPath(): string {
  return (
    process.env["RC_PACKAGE_TARGET_SCHEMA"] ??
    fileURLToPath(new URL("../../package-target.schema.yaml", import.meta.url))
  );
}

let validator: ValidateFunction | undefined;

function targetValidator(): ValidateFunction {
  if (validator === undefined) {
    const ajv = new Ajv2020({ strict: false, allErrors: true, allowUnionTypes: true });
    addFormats.default(ajv);
    validator = ajv.compile(parse(readFileSync(targetSchemaPath(), "utf-8")) as object);
  }
  return validator;
}

function configError(message: string, pointer = ""): Described {
  return { code: "RCT1006", message, pointer };
}

function describe(error: ErrorObject): Described {
  const path = error.instancePath;
  const registry = configError(
    "registryId is required exactly for registry publication",
    "/registryId",
  );
  if (error.keyword === "required") {
    const missing = (error.params as { missingProperty: string }).missingProperty;
    if (path === "") {
      return missing === "registryId"
        ? registry
        : configError(`missing required field '${missing}'`, `/${missing}`);
    }
    return configError(`missing dependency field '${missing}'`, `${path}/${missing}`);
  }
  if (error.keyword === "additionalProperties") {
    const extra = (error.params as { additionalProperty: string }).additionalProperty;
    return path === ""
      ? configError(`unknown field '${extra}'`, `/${extra}`)
      : configError(`unknown dependency field '${extra}'`, `${path}/${extra}`);
  }
  if (error.keyword === "if" || error.keyword === "not") return registry;
  if (path === "/apiVersion" || path === "/kind") {
    return configError("unsupported target apiVersion or kind");
  }
  if (path === "/sourceDirectory") {
    return {
      code: "RCT1007",
      message: "source directory does not match package key",
      pointer: path,
    };
  }
  if (path === "/minimumNodeVersion") {
    return { code: "RCT1008", message: "unsupported minimum Node.js version", pointer: path };
  }
  if (path === "/emitterSha256") {
    return configError(
      "emitterSha256 must be a 64-character lowercase SHA-256 of the emitter tool",
      path,
    );
  }
  if (path === "/version") return configError("unsupported package version", path);
  if (path === "/publicationMode") return configError("unsupported publication mode", path);
  if (path === "/repositoryUrl") return configError("repositoryUrl must use https", path);
  if (path === "/dependencies") return configError("dependencies must be a sequence", path);
  const dependency = /^\/dependencies\/\d+(?:\/\w+)?$/.exec(path);
  if (dependency) {
    return configError(
      path.split("/").length === 3 ? "dependency must be a mapping" : "invalid dependency package metadata",
      path,
    );
  }
  return configError(`invalid ${path.split("/").pop()}`, path);
}

function rank(error: ErrorObject): number {
  if (error.instancePath !== "") return 3;
  if (error.keyword === "required") {
    return (error.params as { missingProperty: string }).missingProperty === "registryId" ? 2 : 0;
  }
  if (error.keyword === "additionalProperties") return 1;
  return error.keyword === "if" || error.keyword === "not" ? 2 : 3;
}

function first(errors: readonly ErrorObject[]): ErrorObject {
  const key = (error: ErrorObject): string =>
    String(rank(error)) +
    ((error.params as Record<string, string>)["missingProperty"] ??
      (error.params as Record<string, string>)["additionalProperty"] ??
      "") +
    error.instancePath +
    error.keyword;
  return [...errors].sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0))[0]!;
}

export function loadTarget(path: string): PackageTarget {
  const value: JsonObject = loadYaml(path, false);
  const validate = targetValidator();
  const coordinate = typeof value["packageKey"] === "string" ? value["packageKey"] : "package-target";
  if (!validate(value)) {
    const described = describe(first(validate.errors!));
    fail("package-config", described.code, coordinate, described.message, described.pointer);
  }
  const packageKey = value["packageKey"] as string;
  if (value["sourceDirectory"] !== `bindings/${packageKey}/typescript`) {
    fail(
      "package-config",
      "RCT1007",
      packageKey,
      "source directory does not match package key",
      "/sourceDirectory",
    );
  }
  const dependencies: PackageDependency[] = [];
  const seen = new Set<string>();
  ((value["dependencies"] ?? []) as JsonObject[]).forEach((entry, index) => {
    const extension = entry["extension"] as string;
    if (seen.has(extension)) {
      fail("package-config", "RCT1006", packageKey, `duplicate dependency '${extension}'`, `/dependencies/${index}`);
    }
    seen.add(extension);
    dependencies.push({
      extension,
      packageName: entry["packageName"] as string,
      version: entry["version"] as string,
      ...(typeof entry["versionRange"] === "string" ? { versionRange: entry["versionRange"] } : {}),
    });
  });
  return {
    packageKey,
    rootExtension: value["rootExtension"] as string,
    packageName: value["packageName"] as string,
    version: value["version"] as string,
    sourceDirectory: value["sourceDirectory"] as string,
    minimumNodeVersion: value["minimumNodeVersion"] as string,
    publicationMode: value["publicationMode"] as string,
    repositoryUrl: value["repositoryUrl"] as string,
    registryId: typeof value["registryId"] === "string" ? value["registryId"] : null,
    dependencies,
    emitterSha256: typeof value["emitterSha256"] === "string" ? value["emitterSha256"] : "",
  };
}

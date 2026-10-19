import { fail } from "./diagnostics.js";
import { loadYaml, type JsonObject } from "./yamlio.js";

export const TARGET_API = "runtimeconditions.io/typescript-package-target/v1alpha1";
export const TARGET_KIND = "RuntimeConditionsTypeScriptPackageTarget";
export const VERSION_PATTERN =
  /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)\.(0|[1-9][0-9]*))?$/;
export const KEY_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
export const PACKAGE_NAME_PATTERN = /^(?:@[a-z0-9][a-z0-9-]*\/)?[a-z0-9][a-z0-9-]*$/;
export const SHA_PATTERN = /^[0-9a-f]{64}$/;
const MINIMUM_NODE = [20, 0] as const;

export interface PackageDependency {
  readonly extension: string;
  readonly packageName: string;
  readonly version: string;
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

const ALLOWED = [
  "apiVersion",
  "kind",
  "packageKey",
  "rootExtension",
  "packageName",
  "version",
  "sourceDirectory",
  "minimumNodeVersion",
  "publicationMode",
  "registryId",
  "repositoryUrl",
  "dependencies",
  "emitterSha256",
];
const REQUIRED = ALLOWED.filter(
  (name) => !["registryId", "dependencies", "emitterSha256"].includes(name),
);

function configFail(message: string, pointer = "", coordinate = "package-target"): never {
  return fail("package-config", "RCT1006", coordinate, message, pointer);
}

function text(value: unknown, name: string): string {
  if (typeof value !== "string" || value === "") return configFail(`invalid ${name}`, `/${name}`);
  return value;
}

export function loadTarget(path: string): PackageTarget {
  const value: JsonObject = loadYaml(path, false);
  for (const name of REQUIRED.filter((item) => !(item in value)).sort()) {
    configFail(`missing required field '${name}'`, `/${name}`);
  }
  for (const name of Object.keys(value)
    .filter((item) => !ALLOWED.includes(item))
    .sort()) {
    configFail(`unknown field '${name}'`, `/${name}`);
  }
  if (value["apiVersion"] !== TARGET_API || value["kind"] !== TARGET_KIND) {
    configFail("unsupported target apiVersion or kind");
  }
  const emitterSha256 = value["emitterSha256"] ?? "";
  if (
    "emitterSha256" in value &&
    (typeof emitterSha256 !== "string" || !SHA_PATTERN.test(emitterSha256))
  ) {
    configFail(
      "emitterSha256 must be a 64-character lowercase SHA-256 of the emitter tool",
      "/emitterSha256",
    );
  }
  for (const name of REQUIRED.filter((item) => item !== "apiVersion" && item !== "kind")) {
    text(value[name], name);
  }
  const packageKey = value["packageKey"] as string;
  const packageName = value["packageName"] as string;
  const version = value["version"] as string;
  if (!KEY_PATTERN.test(packageKey)) configFail("invalid packageKey", "/packageKey");
  if (!PACKAGE_NAME_PATTERN.test(packageName) || packageName.length > 214) {
    configFail("invalid packageName", "/packageName");
  }
  if (!VERSION_PATTERN.test(version)) configFail("unsupported package version", "/version");
  if (value["sourceDirectory"] !== `bindings/${packageKey}/typescript`) {
    fail(
      "package-config",
      "RCT1007",
      packageKey,
      "source directory does not match package key",
      "/sourceDirectory",
    );
  }
  const minimum = value["minimumNodeVersion"] as string;
  const parts = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.exec(minimum);
  const major = Number(parts?.[1]);
  const minor = Number(parts?.[2]);
  if (
    parts === null ||
    major < MINIMUM_NODE[0] ||
    (major === MINIMUM_NODE[0] && minor < MINIMUM_NODE[1])
  ) {
    fail(
      "package-config",
      "RCT1008",
      packageKey,
      "unsupported minimum Node.js version",
      "/minimumNodeVersion",
    );
  }
  const mode = value["publicationMode"];
  if (mode !== "github-tag" && mode !== "registry") {
    configFail("unsupported publication mode", "/publicationMode", packageKey);
  }
  const repositoryUrl = value["repositoryUrl"] as string;
  if (!repositoryUrl.startsWith("https://") || /\s/.test(repositoryUrl)) {
    configFail("repositoryUrl must use https", "/repositoryUrl", packageKey);
  }
  const registry = "registryId" in value ? text(value["registryId"], "registryId") : null;
  if ((mode === "registry") !== (registry !== null)) {
    configFail(
      "registryId is required exactly for registry publication",
      "/registryId",
      packageKey,
    );
  }
  const entries = value["dependencies"] ?? [];
  if (!Array.isArray(entries)) {
    configFail("dependencies must be a sequence", "/dependencies", packageKey);
  }
  const dependencies: PackageDependency[] = [];
  const seen = new Set<string>();
  entries.forEach((entry: unknown, index: number) => {
    const pointer = `/dependencies/${index}`;
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      configFail("dependency must be a mapping", pointer, packageKey);
    }
    const record = entry as JsonObject;
    const fields = ["extension", "packageName", "version"];
    for (const name of fields.filter((item) => !(item in record)).sort()) {
      configFail(`missing dependency field '${name}'`, `${pointer}/${name}`, packageKey);
    }
    for (const name of Object.keys(record)
      .filter((item) => !fields.includes(item))
      .sort()) {
      configFail(`unknown dependency field '${name}'`, `${pointer}/${name}`, packageKey);
    }
    const extension = text(record["extension"], "extension");
    const dependencyName = text(record["packageName"], "packageName");
    const dependencyVersion = text(record["version"], "version");
    if (seen.has(extension)) {
      configFail(`duplicate dependency '${extension}'`, pointer, packageKey);
    }
    seen.add(extension);
    if (!PACKAGE_NAME_PATTERN.test(dependencyName) || !VERSION_PATTERN.test(dependencyVersion)) {
      configFail("invalid dependency package metadata", pointer, packageKey);
    }
    dependencies.push({ extension, packageName: dependencyName, version: dependencyVersion });
  });
  return {
    packageKey,
    rootExtension: value["rootExtension"] as string,
    packageName,
    version,
    sourceDirectory: value["sourceDirectory"] as string,
    minimumNodeVersion: minimum,
    publicationMode: mode,
    repositoryUrl,
    registryId: registry,
    dependencies,
    emitterSha256: emitterSha256 as string,
  };
}

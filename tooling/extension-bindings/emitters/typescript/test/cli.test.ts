import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, rmSync, writeFileSync, mkdirSync, truncateSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { EMITTER_ROOT, TARGET, emitterDigest, modelPath, temporaryDirectory } from "./support.js";
import { loadTarget } from "../src/target.js";

const MAIN = join(EMITTER_ROOT, "dist/src/main.js");

function run(...args: string[]): { status: number | null; stdout: string; stderr: string } {
  const result = spawnSync(process.execPath, [MAIN, ...args], { encoding: "utf-8" });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

function targetFile(directory: string): string {
  const path = join(directory, "target.yaml");
  const target = loadTarget(TARGET);
  writeFileSync(
    path,
    readFileSync(TARGET, "utf-8").replace(
      "repositoryUrl:",
      `emitterSha256: ${emitterDigest()}\nrepositoryUrl:`,
    ),
  );
  void target;
  return path;
}

test("emit, verify, and api work end to end through the command line", () => {
  const directory = temporaryDirectory();
  try {
    const target = targetFile(directory);
    const model = modelPath("01-owned-kind-interface");
    const output = join(directory, "package");
    const emitted = run("emit", "--model", model, "--package-config", target, "--output", output);
    assert.equal(emitted.status, 0, emitted.stderr);
    assert.deepEqual(JSON.parse(emitted.stdout), { output });
    const verified = run("verify", "--model", model, "--package-config", target, "--input", output);
    assert.equal(verified.status, 0, verified.stderr);
    const result = JSON.parse(verified.stdout) as { api: string[]; modelMapping: boolean };
    assert.equal(result.modelMapping, true);
    assert.ok(result.api.includes("function|service|...fields: ServiceField[]|Declaration"));
    const api = run("api", "--input", output);
    assert.equal(api.status, 0, api.stderr);
    assert.deepEqual(JSON.parse(api.stdout), { api: result.api });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("emit refuses an occupied output directory and writes nothing", () => {
  const directory = temporaryDirectory();
  try {
    const target = targetFile(directory);
    const output = join(directory, "occupied");
    mkdirSync(output);
    writeFileSync(join(output, "keep.txt"), "keep");
    const result = run(
      "emit",
      "--model",
      modelPath("01-owned-kind-interface"),
      "--package-config",
      target,
      "--output",
      output,
    );
    assert.equal(result.status, 1);
    assert.match(result.stderr, /RCT3001/);
    assert.equal(readFileSync(join(output, "keep.txt"), "utf-8"), "keep");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("emit requires the emitter digest for package resources", () => {
  const result = run(
    "emit",
    "--model",
    modelPath("01-owned-kind-interface"),
    "--package-config",
    TARGET,
    "--output",
    join(temporaryDirectory(), "out"),
  );
  assert.equal(result.status, 1);
  assert.match(result.stderr, /emitterSha256/);
});

test("bad usage and mismatched targets fail with a nonzero status", () => {
  assert.equal(run().status, 1);
  assert.equal(run("generate").status, 1);
  assert.equal(run("emit", "--model", "x").status, 1);
  assert.equal(run("emit", "--bogus").status, 1);
  assert.equal(run("api").status, 1);
  assert.equal(
    run("--version").stdout.trim(),
    JSON.parse(readFileSync(join(EMITTER_ROOT, "package.json"), "utf-8")).version,
  );
  const directory = temporaryDirectory();
  try {
    const target = targetFile(directory);
    const result = run(
      "emit",
      "--model",
      modelPath("02-additive-field"),
      "--package-config",
      target,
      "--output",
      join(directory, "out"),
    );
    assert.equal(result.status, 1);
    assert.match(result.stderr, /RCT1009/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("verify rejects a tampered API or manifest", () => {
  const directory = temporaryDirectory();
  try {
    const target = targetFile(directory);
    const model = modelPath("01-owned-kind-interface");
    const output = join(directory, "package");
    assert.equal(
      run("emit", "--model", model, "--package-config", target, "--output", output).status,
      0,
    );
    const bindings = join(output, "src/bindings.ts");
    const original = readFileSync(bindings, "utf-8");
    writeFileSync(
      bindings,
      original.replace("readonly endpoint: string;", "readonly endpoint: number;"),
    );
    const tamperedApi = run(
      "verify",
      "--model",
      model,
      "--package-config",
      target,
      "--input",
      output,
    );
    assert.equal(tamperedApi.status, 1);
    assert.match(tamperedApi.stderr, /native API or conformance mismatch/);
    writeFileSync(bindings, original);
    const manifest = join(output, "runtimeconditions/runtimeconditions.bindings.yaml");
    const text = readFileSync(manifest, "utf-8");
    writeFileSync(manifest, text.replace("#schema", "#wrong"));
    const tamperedManifest = run(
      "verify",
      "--model",
      model,
      "--package-config",
      target,
      "--input",
      output,
    );
    assert.equal(tamperedManifest.status, 1);
    assert.match(tamperedManifest.stderr, /manifest mappings/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("an oversized input is rejected without being read into memory", () => {
  const directory = temporaryDirectory();
  try {
    const target = targetFile(directory);
    const oversized = join(directory, "model.yaml");
    // A sparse 3 GiB file: reading it whole fails for another reason than the size limit.
    writeFileSync(oversized, "");
    truncateSync(oversized, 3 * 1024 * 1024 * 1024);
    const result = run(
      "emit",
      "--model",
      oversized,
      "--package-config",
      target,
      "--output",
      join(directory, "out"),
    );
    assert.equal(result.status, 1);
    assert.match(result.stderr, /RCT1001.*exceeds 64 MiB/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

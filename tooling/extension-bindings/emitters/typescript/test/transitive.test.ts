import assert from "node:assert/strict";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { loadModel, type Model } from "../src/model.js";
import { buildPlan } from "../src/plan.js";
import { emitPackage } from "../src/source.js";
import type { PackageTarget } from "../src/target.js";
import { verifyPackage } from "../src/verification.js";
import { developmentTarget, modelPath, runTsc, temporaryDirectory } from "./support.js";

function target(key: string, root: string, dependencies: [string, string][]): PackageTarget {
  return {
    ...developmentTarget(),
    packageKey: key,
    sourceDirectory: `bindings/${key}/typescript`,
    packageName: `@rc/${key}`,
    rootExtension: root,
    dependencies: dependencies.map(([extension, packageName]) => ({
      extension,
      packageName,
      version: "1.0.0",
    })),
  };
}

test("root -> middle -> leaf compile together through the middle package's re-export", async () => {
  const model = loadModel(modelPath("03-transitive-closure"));
  const rootId: string = model["rootExtension"].id;
  const leafId: string = model["vocabulary"].importedDeclarations[0].owner;
  const middle = model["extensions"].find((item: any) =>
    (item.dependencies ?? []).includes(leafId),
  );
  const middleId: string = middle.id;
  const extension = (id: string): any => model["extensions"].find((item: any) => item.id === id);

  const leafModel: Model = structuredClone(model);
  leafModel["rootExtension"] = { ...extension(leafId) };
  leafModel["extensions"] = [extension(leafId)];
  leafModel["vocabulary"].ownedDeclarations = model["vocabulary"].importedDeclarations;
  leafModel["vocabulary"].importedDeclarations = [];

  const middleModel: Model = structuredClone(model);
  middleModel["rootExtension"] = { ...extension(middleId) };
  middleModel["extensions"] = [extension(leafId), extension(middleId)];
  middleModel["vocabulary"].ownedDeclarations = [];

  const workspace = temporaryDirectory();
  try {
    const packages = [
      { key: "leaf", model: leafModel, target: target("leaf", leafId, []) },
      {
        key: "middle",
        model: middleModel,
        target: target("middle", middleId, [[leafId, "@rc/leaf"]]),
      },
      { key: "root", model, target: target("root", rootId, [[middleId, "@rc/middle"]]) },
    ];
    // Each package sits in node_modules, where the next one resolves it, and is built before its consumer.
    for (const item of packages) {
      const directory = join(workspace, "node_modules", "@rc", item.key);
      mkdirSync(directory, { recursive: true });
      const plan = buildPlan(item.model, item.target);
      await emitPackage(plan, item.model, directory);
      verifyPackage(plan, directory, item.model);
      const built = runTsc(directory, false);
      assert.equal(built.status, 0, `${item.key}: ${built.output}`);
    }
    const root = readFileSync(join(workspace, "node_modules/@rc/root/src/bindings.ts"), "utf-8");
    assert.match(root, /from "@rc\/middle"/);
    const middleSource = readFileSync(
      join(workspace, "node_modules/@rc/middle/src/bindings.ts"),
      "utf-8",
    );
    assert.match(middleSource, /from "@rc\/leaf"/);
    assert.match(middleSource, /export \{[^}]*WorkerField/);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

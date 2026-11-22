import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { apiSurface } from "../src/verification.js";

const plain = `export class Declaration {}
export interface ApiField {
  readonly __rc: "api";
}
export enum Method {
  Get = "GET",
}
export class Spec {
  readonly uri: string;
  readonly version?: string;
  constructor(fields: { readonly uri: string; readonly version?: string }) {
    this.uri = fields.uri;
    this.version = fields.version;
  }
}
export type Operations = ReadonlyArray<Spec>;
export function api(...fields: ApiField[]): Declaration {
  void fields;
  return new Declaration();
}
`;

const documented = `/** Generated bindings. */
/** The inert result of a declaration. */
export class Declaration {}
/** Field contract for api declarations. */
export interface ApiField {
  /** Marker. */
  readonly __rc: "api";
}
/** HTTP method. */
export enum Method {
  /** The GET method. */
  Get = "GET", // trailing note
}
/** An OpenAPI document reference. */
export class Spec {
  /** Catalog URI of the document. */
  readonly uri: string;
  /** Document version. */
  readonly version?: string;
  /** Creates a Spec. */
  constructor(fields: {
    /** Catalog URI of the document. */
    readonly uri: string;
    /** Document version. */
    readonly version?: string /* optional */
  }) {
    this.uri = fields.uri;
    this.version = fields.version;
  }
}
/** Operations list. */
export type Operations = ReadonlyArray</* item */ Spec>;
/** Declares an api Condition. */
export function api(/** fields */ ...fields: ApiField[]): Declaration {
  void fields;
  return new Declaration();
}
`;

function surface(source: string): string[] {
  const directory = mkdtempSync(join(tmpdir(), "rc-doc-comments-"));
  try {
    mkdirSync(join(directory, "src"));
    writeFileSync(join(directory, "src/bindings.ts"), source);
    return apiSurface(directory);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("doc comments never change the API surface used for release compatibility", () => {
  const expected = surface(plain);
  assert.ok(expected.some((entry) => entry.startsWith("constructor|Spec|")));
  assert.deepEqual(surface(documented), expected);
});

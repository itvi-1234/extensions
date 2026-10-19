# TypeScript emitter contract

This records the TypeScript target, layout, and naming decisions for the native
TypeScript emitter. It is written in TypeScript, as the implementation standard
requires of every emitter, and follows the Python emitter's structure.

The emitter consumes one validated binding model and one selected, resolved
TypeScript target through the shared command contract:

```text
runtimeconditions-binding-emitter-typescript emit \
  --model runtimeconditions.binding-model.yaml \
  --package-config <target.yaml> --output <new empty directory>
```

`verify --model --package-config --input <package>` parses the generated source
with the TypeScript compiler API (never importing or running it), checks its
public API against the model plan, and compares the structural manifest with a
fresh rendering. `api --input <package>` prints the structural signatures.

## Target configuration

The selected target uses `runtimeconditions.io/typescript-package-target/v1alpha1`
and `RuntimeConditionsTypeScriptPackageTarget`. Its shape is defined by
`package-target.schema.yaml`; the emitter validates it field by field with the
same diagnostics as the schema.

- `packageKey`, `rootExtension`, `version`, `sourceDirectory`, and
  `publicationMode` correspond to the package set and language entry in the
  catalog. `sourceDirectory` is exactly `bindings/<packageKey>/typescript`.
- `packageName` is the npm package name and is also the module specifier
  consumers import. It is never inferred from extension vocabulary.
- `minimumNodeVersion` is `<major>.<minor>` and at least `20.0`. It becomes
  `engines.node`.
- `repositoryUrl` supplies the package repository metadata and must use HTTPS.
  A registry target additionally requires `registryId`.
- `dependencies` contains only direct extension dependencies, with their npm
  package names and exact tested versions, and equals the model's direct
  dependency set.
- `emitterSha256` is supplied by the caller and recorded in the manifest.

Package versions are SemVer without a leading `v` or build metadata and map
unchanged to npm. Supported prerelease forms are `-alpha.N`, `-beta.N`, and
`-rc.N`. Direct dependency ranges use `>=<tested> <next-breaking>`, where
`next-breaking` is `0.(y+1).0` below `1.0.0` and `(major+1).0.0` otherwise.

## Generated source tree

```text
<new output directory>/
  package.json
  tsconfig.json
  src/
    index.ts
    bindings.ts
  runtimeconditions/
    runtimeconditions.bindings.yaml
```

`index.ts` re-exports `bindings.ts`. Package assembly adds the other three
resources beside the manifest in `runtimeconditions/`, and the package-tree file
manifest at the root, without rewriting emitter output; `package.json` already
lists both in `files`. Only readable TypeScript source is committed. `dist/` is
a build output produced by `tsc` during `npm pack`.

Generated source is formatted by the pinned Prettier release at emission time and
starts with the non-editable header naming the model digest and emitter version.
`package.json` carries the same header in a `//` property.

## API rules

1. Every owned kind becomes one function `kind(...fields: KindField[]): Declaration`.
   `Declaration` is an inert class; the function body does nothing.
2. `<Kind>Field` is an interface whose only member is a marker method named
   `rcMarker_<16 hex digits>`, derived from the owner and declaration
   coordinate. Every applicable object class declares that method and
   `implements` the interface, so a field belonging to another kind does not
   type-check. Cross-package additive fields implement the provider's interface
   in the same way.
3. Objects become classes with `readonly` properties and one constructor taking
   a single fields object. The emitter does not add factories or operation
   specific constructors. A constructor argument is optional only when every
   field is optional.
4. Optional fields use `?:`. Required fields have no modifier.
5. Arrays become `ReadonlyArray<T>`. Maps become `{ readonly [key: string]: T }`;
   an index-signature object type is required because `Readonly<Record<…>>`
   cannot be referenced recursively.
6. Unions become TypeScript unions. A JSON value becomes the recursive
   `JSONValue` alias.
7. String value domains become `enum` types whose members are Pascal case and
   scoped by the enum. Integer and number shapes both map to `number`.
8. Imported declarations are re-exported from their direct provider package.

Names derive only from exact source names. Types, enums, and marker interfaces
use Pascal case; properties, parameters, and functions use camel case. A leading
digit gains `X` (types) or `x`. A JavaScript reserved word, including
`constructor` and `prototype`, gains one trailing underscore. A name that equals
a TypeScript global or a generated helper (`Record`, `Promise`, `JSONValue`, …)
stops emission instead of being renamed. Collisions are resolved only by
prepending parent path components, nearest first, and otherwise stop emission.

## Diagnostics

Codes use the `RCT` prefix and mirror the meanings of the Python `RCP` codes.

| Code | Meaning |
| --- | --- |
| `RCT1001` | YAML input cannot be read or exceeds the size limit. |
| `RCT1002` | YAML syntax, profile, structure, or resource-limit failure. |
| `RCT1003` | Binding-model schema validation failure. |
| `RCT1004` | Unsupported binding-model `apiVersion`. |
| `RCT1005` | Unsupported binding-model `kind`. |
| `RCT1006` | Invalid TypeScript package-target field or dependency metadata. |
| `RCT1007` | Target source directory does not match its package key. |
| `RCT1008` | Unsupported minimum Node.js version. |
| `RCT1009` | Target root extension or direct dependency set differs from the model. |
| `RCT1010` | Unknown structural shape kind. |
| `RCT1011` | Inconsistent extension closure or declaration ownership. |
| `RCT1012` | Inconsistent shape details, value domain, or unresolved reference. |
| `RCT2000` | A source name cannot be derived as a valid TypeScript identifier. |
| `RCT2001` | Symbol collision or reserved-name conflict. |
| `RCT3001` | Output directory is not new or empty. |
| `RCT3002` | Output directory cannot be inspected or written. |
| `RCT4002` | Pinned toolchain mismatch. |

## Input loading

The model is read with the Python emitter's restrictions: UTF-8 without BOM, LF
line endings, one trailing newline, no comments, anchors, aliases, or tags,
string mapping keys only, no duplicate keys, finite numbers, and the same size,
node, and depth limits. It is then validated against
`model/runtimeconditions.binding-model.schema.yaml`. The shared schema location
can be overridden with `RC_BINDING_MODEL_SCHEMA` when the emitter runs outside this
checkout.

## Verification

The tests run the shared conformance models in `model/conformance/expected`
and the committed first-party models. For each, they check that three
independent emissions are byte-identical, that the output is Prettier-stable,
that `verify` accepts it, and that the package compiles under `tsc` with
`strict`, `noUncheckedIndexedAccess`, `isolatedModules`, and
`verbatimModuleSyntax`. A generated conformance source constructs every type,
enum member, collection, map, union variant, and declaration. Negative tests
cover invalid inputs, tampered output, and values the model does not allow.

The committed first-party models exposed one rule above: a recursive map needs
an index-signature type. The shared conformance fixtures do not cover it.

## Design notes

- **Language key and layout.** The catalog language key is `typescript`, and a
  package lives in `bindings/<key>/typescript`.
- **Resource location.** The four binding resources live in `runtimeconditions/`
  at the npm package root.
- **Classes and enums.** Object shapes are classes so that the marker method
  makes the additive-field check work across packages. String domains use `enum`,
  the native enum namespace.
- **Numbers.** The model's integer and number shapes both become `number`.
- **Tool pins.** TypeScript 5.9.3, Prettier 3.9.10, and Node 20.19.6 are recorded
  under `languages.typescript` in `toolchain.lock.yaml`. The emitter depends on
  the JavaScript compiler API, so it uses the 5.x release line.

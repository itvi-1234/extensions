# Phase 3: Python binding emitter exit review

Verified on 2026-10-01 on macOS arm64 with Python 3.11.16 and the pinned
Phase 3 tools in `toolchain.lock.yaml`. This review covers the nine positive
normalized conformance models and four Python-specific negative models.

## Applicable verification gates

| Gate | Result | Evidence |
| --- | --- | --- |
| 1: model schema | Pass | Every positive model and each mutated negative model validates with the Draft 2020-12 model schema. |
| 2: binding manifest schema | Pass | Every emitted manifest validates with the provisional shared schema. The fuller structural schema belongs to Phase 4. |
| 3: package metadata | Pass | `tomllib` parses every generated `pyproject.toml`; Python package metadata, dependency requirements, and installed distributions are checked through `packaging` and `importlib.metadata`. |
| 4: formatter | Pass | Pinned Ruff 0.16.9 formats generated source during emission; `ruff format --check` passes for every positive package and the emitter source. |
| 5: minimum-version compilation | Pass | Python 3.11.16 `compileall` passes for every positive package and emitter source. |
| 6: static typing | Pass | `mypy --strict` passes for every generated positive package with direct and transitive provider source packages available for import resolution, and for all emitter source modules. |
| 7: native tests | Pass | The complete Python suite reports 79 passed. |
| 8: conformance coverage | Pass | Native AST checks cover every planned declaration call, object type and field, enum member, collection, map, union variant, and JSON value where used. Direct and transitive additive composition also runs from source and installed wheels. |
| 12: repeated source emission | Pass | Each positive model emits into three new directories; relative file sets and all file bytes match. |
| 14: undeclared archive files | Pass | Tests reject undeclared source, wheel, and sdist entries and altered archive metadata. |
| 16: public API comparison | Pass | Native AST checks compare exports, declaration signatures, marker protocols, dataclass fields and defaults, aliases, and enum values with the normalized-model emission plan. |

The archive tests also build wheels and source distributions twice for each
positive model and compare their bytes. Clean installation tests verify
`importlib.resources`, `py.typed`, conformance source, source-distribution
rebuilds, and direct and transitive dependency resolution with pip.

The Python-specific negative fixtures assert exact category, code, coordinate,
JSON Pointer, and message for a reserved built-in, fixed symbol collision,
enum-member collision, and unnameable field. Existing tests also check malformed
inputs, unsupported shapes, package/target mismatches, and output rejection.

## Exit checks

- No extension definition YAML was changed during this phase.
- Production emitter source contains no conformance case ID, extension ID,
  kind, field, or value special case. Conformance names occur only in test data.
- Generated source and metadata contain no timestamps or temporary output
  paths. Three-run package emission and two-run archive builds are byte-identical
  for the positive fixtures.
- The protected `IMPLEMENTATION.md` checksum remains
  `a35761929748cf1f7fa659e518aeae0bd99fc891e38131e5b8df0ebe79b57e61`.

Verification here was run on macOS. The Phase 4 structural manifest and profile
gates are outside Phase 3; this report does not claim those later gates.

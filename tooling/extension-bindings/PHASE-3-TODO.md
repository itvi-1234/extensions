# Phase 3 Todo List: Python Emitter

This checklist tracks the Python emitter work required by
`IMPLEMENTATION.md`. That document is the implementation authority; this file
does not replace or amend it.

## 1. Resolve the Phase 3 contracts

- [ ] Consume the normalized binding model and one Python target from
      `packages.yaml` through the standard emitter command contract.
- [ ] Define the target metadata needed to map the distribution name to the
      import-package name.
- [ ] Use the shared `runtimeconditions.bindings.yaml` contract. Validate the
      emitted manifest against the available manifest schema for the Phase 3
      gate 2; Phase 4 delivers the structural binding-manifest schema.
- [ ] Define the generated Python package layout and minimum supported Python
      version. The minimum MUST be Python 3.11 or later because the standard
      requires `StrEnum`; tool versions MUST be pinned in
      `toolchain.lock.yaml`.

## 2. Define the Python type-system mapping

- [ ] Map normalized string, boolean, integer, number, null, object, array,
      map, union, reference, and recursive shapes to Python typing constructs.
- [ ] Define recursive type-alias syntax compatible with the minimum Python
      version and `mypy --strict`.
- [ ] Use `str` for JSON object map keys.
- [ ] Preserve requiredness separately from nullability: a required nullable
      field remains a required initializer argument; an optional field uses
      `T | None = None` as specified by the standard.
- [ ] Define exact scalar annotations and ensure unsupported shapes fail with a
      deterministic diagnostic rather than widening to `Any`.
- [ ] Implement the structural marker `Protocol` and cross-package additive
      behavior required by Sections 7 and 10.4.

## 3. Define Python naming and collision behavior

- [ ] Implement the Python naming rules in Sections 10.1 and 10.4, including
      case conversion, keywords, leading numeric tokens, and dunder names.
- [ ] Allocate the complete generated symbol set and detect collisions with
      fixed symbols, imported helpers, built-ins, generated classes, aliases,
      protocols, functions, fields, enum classes, and enum members.
- [ ] Define deterministic diagnostics for Python-specific naming and
      collision failures.
- [ ] Add exact negative fixtures for Python-relevant collision cases.

## 4. Define generated Python source structure

- [ ] Choose a module layout within the generated import-package directory and
      define its public exports and `__all__` policy.
- [ ] Generate the inert `Declaration` object and declaration functions
      required by Section 10.4.
- [ ] Generate frozen, keyword-only dataclasses with deterministic field order,
      defaults, and forward references.
- [ ] Generate `StrEnum` value domains with exact serialized member values.
- [ ] Generate aliases, collections, maps, unions, and recursive references
      using the Python mappings in Section 10.4.
- [ ] Emit the standard non-editable header in Python source and package
      metadata, without timestamps or host-specific paths.

## 5. Define Python package metadata and resources

- [ ] Generate deterministic `pyproject.toml` metadata using the pinned build
      backend and tool versions from `toolchain.lock.yaml`.
- [ ] Generate `Requires-Python` consistent with the declared minimum version.
- [ ] Generate direct Python binding dependencies using the required
      `>=<tested>,<next-breaking>` interval.
- [ ] Configure package data for `runtimeconditions.bindings.yaml` at the
      import-package location required by Section 11. The orchestrator adds
      the extension, model, release, and file-manifest resources in a later
      phase.
- [ ] Verify packaged resources through `importlib.resources` from an installed
      distribution.
- [ ] Include conformance source in the package artifacts as required by the
      generated-package contract.

## 6. Define archive and reproducibility behavior

- [ ] Build and inspect both wheels and source distributions using the pinned
      Python packaging tools.
- [ ] Make archive bytes deterministic for identical inputs and toolchain,
      including timestamps, file order, ownership, permissions, and compression
      metadata.
- [ ] Verify archive file manifests and reject undeclared files.
- [ ] Verify wheel installation and source-distribution build in clean isolated
      environments.
- [ ] Resolve package dependencies through the native Python package manager;
      do not scan package caches or filesystems.

## 7. Implement the Python emitter

- [ ] Add the Python emitter project under the planned emitter layout.
- [ ] Implement strict model and package-target loading, including duplicate-key
      rejection and the required input limits.
- [ ] Implement Python naming and complete-set collision allocation.
- [ ] Implement declaration functions, marker protocols, dataclasses, scalar
      types, enums, aliases, arrays, maps, unions, references, and recursive
      shapes.
- [ ] Implement direct and transitive dependency imports.
- [ ] Implement binding-manifest generation and validation for the Phase 3
      schema gate.
- [ ] Implement deterministic `pyproject.toml` generation, the standard
      emitter command, and wheel/source-distribution build and inspection.

## 8. Add Python conformance coverage

- [ ] Emit every positive language-neutral conformance model.
- [ ] Cover owned declarations, interface objects, direct additive fields, and
      transitive dependency closure.
- [ ] Cover recursive references, object-only alternatives with
      branch-dependent requiredness, and heterogeneous unions.
- [ ] Cover scalar arrays, object arrays, schema-valued maps, and scoped value
      domains.
- [ ] Cover Python naming boundaries, keywords, leading digits, Unicode, and
      relevant collision cases.
- [ ] Exercise every generated declaration, type, field, enum member,
      collection, map, and union in conformance source.
- [ ] Add exact Python diagnostics for every Python-relevant negative model.

## 9. Satisfy the Phase 3 verification gates

- [ ] Gate 1: validate the normalized model schema.
- [ ] Gate 2: validate the Python binding manifest schema.
- [ ] Gate 3: parse Python package metadata with native Python packaging tools.
- [ ] Gate 4: pass `ruff format --check`.
- [ ] Gate 5: compile with the minimum supported Python version.
- [ ] Gate 6: pass `mypy --strict`.
- [ ] Gate 7: pass the native Python test suite.
- [ ] Gate 8: verify complete conformance-source coverage.
- [ ] Gate 12: verify byte-identical repeated emission.
- [ ] Gate 14: reject undeclared archive files.
- [ ] Gate 16: compare the exported Python API from the native AST with the API
      derived mechanically from the model.
- [ ] Test direct and transitive additive package composition with source
      packages and built, installed wheel artifacts.
- [ ] Verify package resources from installed wheels and source distributions.

## 10. Phase 3 exit review

- [ ] Confirm no extension YAML was modified.
- [ ] Confirm emitter behavior is not keyed to a conformance identifier,
      extension identifier, kind, field, or value.
- [ ] Confirm generated source and metadata contain no timestamps or
      host-specific paths and repeated builds are byte-identical.
- [ ] Confirm all applicable diagnostics are deterministic and exact.
- [ ] Record Phase 3 verification results in `PHASE-3.md`.

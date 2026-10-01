# Phase 3 Python package contract

This records the Python target and layout decisions for Phase 3. The Python
emitter consumes one validated binding model and one selected, resolved Python
target through the Section 10 command contract. The production `packages.yaml`
catalog and orchestration arrive in Phase 5. The target under `testdata/` is a
Phase 3 conformance target, not a production catalog entry.

## Target configuration

The selected target uses
`runtimeconditions.io/python-package-target/v1alpha1` and
`RuntimeConditionsPythonPackageTarget`. Its complete shape is defined by
`package-target.schema.yaml`.
The initial test target reuses the `conformance-owned-kind-interface` package
key from the Go emitter's `testdata/package-targets/01-owned-kind-interface.yaml`.
That key is test configuration, not a prescribed production package name.

- `packageKey`, `rootExtension`, `version`, `sourceDirectory`, and
  `publicationMode` correspond to the package set and Python language entry in
  the eventual catalog. `sourceDirectory` is exactly
  `bindings/<packageKey>/python`.
- `distributionName` is the lowercase, hyphen-separated package-manager
  coordinate. `importPackage` is the distinct lowercase ASCII Python package
  identifier. Neither is inferred from the other or from extension vocabulary.
- `minimumPythonVersion` is `3.11`. Generated metadata will declare
  `Requires-Python: >=3.11`; verification compiles with Python 3.11.
- `repositoryUrl` supplies the source repository metadata for the generated
  distribution. A registry target additionally requires `registryId`.
- `dependencies` contains only direct extension dependencies, with their
  resolved Python distribution names, import packages, and exact tested
  versions. It is derived from the model's direct dependency edges and the
  catalog's Python targets. The future `packages.yaml` will not restate
  extension dependency semantics.

Package versions are SemVer without a leading `v` or build metadata. Stable
`MAJOR.MINOR.PATCH` maps unchanged to Python distribution metadata. Supported
prerelease forms `-alpha.N`, `-beta.N`, and `-rc.N` map respectively to `aN`,
`bN`, and `rcN`. An unsupported prerelease form is rejected instead of guessed.
Direct dependency metadata uses `>=<tested>,<next-breaking>` after the same
version conversion; `next-breaking` follows Section 7.

The emitter will reject a target whose root extension differs from the model,
whose direct dependency set differs from the model, whose import package is a
Python keyword, or whose output directory does not match its package key. The
target schema checks the static shape; semantic checks belong in the emitter.

## Generated source tree

```text
<new output directory>/
  pyproject.toml
  src/<importPackage>/
    __init__.py
    bindings.py
    _conformance.py
    py.typed
    runtimeconditions.bindings.yaml
```

`__init__.py` reexports the public API from `bindings.py` and declares an
explicit, sorted `__all__`. `bindings.py` is also a public importable module.
`_conformance.py` is generated source that exercises every declaration, type,
field, value member, collection, map, and union for Section 13 gate 8. It is
included in both wheels and source distributions but excluded from the public
API; importing the package does not run it. `py.typed` marks the installed
package as typed. The generated `pyproject.toml` uses the pinned setuptools
backend, explicit `src` package discovery, and package data for the binding
manifest. The orchestrator later adds the other three Section 11 resources
beside the manifest, without rewriting emitter output.

The emitter project itself follows the `emitters/python/` source layout in
Section 4. Its `pyproject.toml` and source files will be added with the emitter
implementation. Section 2 fixes `toolchain.lock.yaml` at the root of the shared
extension-binding tooling. It is a multi-language lock; its Python tool entries
are the first entries populated for Phase 3 development. Released tooling
digests and the complete production toolchain lock are Phase 5 work.

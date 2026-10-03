# Phase 4 installable binding fixtures

`assemble.py` builds **test-only** Go modules and Python wheels for the owned,
direct-additive, and transitive-additive conformance cases. It is a limited
fixture assembler, not the Phase 5 production orchestrator or a package
publication tool. The profiler runs later, from its installed CLI, against a
separate workload. Neither profiler is embedded in the binding package.

The six package roots are `01-owned-kind-interface`, the base and root of
`02-additive-field`, and the leaf, middle, and root of
`03-transitive-closure`. Each package contains the exact emitter-produced
structural manifest plus the normalized model, resolved root extension, and
schema-validated fixture release manifest at its final package-local resource
location. The assembler produces both languages in dependency order and records
SHA-256 of the actual normalizer executable, assembler script, profiler
artifact, extension source, and direct dependency archives. It rejects missing
or contradictory identities instead of inventing release provenance.

## Assemble

Use Python 3.11 or newer with `PyYAML==6.0.3`, `jsonschema==4.26.0`,
`rfc8785==0.1.4`, `setuptools==84.0.0`, `wheel==0.48.0`, and `ruff==0.16.9`
installed. The Python interpreter must have `pip` and the pinned Ruff executable
available. Go 1.22 or newer must be on `PATH`. Supply an actual Go profiler
executable built with the approved core schema and an actual Python profiler
wheel; the assembler hashes these artifacts for test provenance. The core
schema is read from the adjacent `spec` repository **only at assembly time**.

```sh
python3 tooling/extension-bindings/fixtures/assemble.py \
  --python /absolute/path/to/python \
  --go-profiler /absolute/path/to/go-rc-profiler \
  --python-profiler-wheel /absolute/path/to/runtimeconditions_profiler-0.1.0-py3-none-any.whl \
  --output /absolute/path/to/new-fixture-output
```

Run this command from the `extensions` checkout. The output directory must be
new or empty. Generated packages are written under `go/packages/` and
`python/packages/`; the installable artifacts are under `go/proxy/` and
`python/wheels/`. `models/` contains the exact normalized models consumed by
the emitters, and `tools/` contains the executables whose bytes were hashed.
No package is published, and the fixture output must not be treated as
production release evidence.

The checked-in normalizer conformance checkpoints still use a synthetic
normalizer hash to keep those golden files independent of a platform-specific
binary. `assemble.py` normalizes afresh with its built executable and places
that executable's actual SHA-256 in every installable fixture model.

## Consume through package managers

For a Go workload, add the desired generated module at `v1.0.0` to its
`go.mod`, then resolve it with `GOPROXY=file:///absolute/path/to/new-fixture-output/go/proxy`
and `GOSUMDB=off`. `go list -json <module-import-path>` must report a source
directory in the Go module cache. The four `runtimeconditions.*.yaml` files
are next to `bindings.go` in that directory. To check the dependency chain,
use `example.com/runtimeconditions/conformance/additive-field` or
`example.com/runtimeconditions/conformance/transitive-root` as the imported
module. The profiler CLI receives the workload directory and resolves that
module through Go; it receives no `extensions` checkout path.

For a Python workload, install the generated root wheel with
`python -m pip install --no-index --find-links /absolute/path/to/new-fixture-output/python/wheels runtimeconditions-conformance-transitive-root`.
Pip installs the direct and transitive dependency wheels. The four resources
are package data in the installed import package and can be located through
`importlib.resources` and distribution metadata. The installed Python
profiler resolves them from that environment without an `extensions` checkout.

Exact declaration workloads, profile YAML, and negative semantic expectations
belong to the subsequent Phase 4 fixture-results deliverable. This assembler
establishes installable inputs and the package trust chain; it does not claim
that either profiler already generates profiles successfully.
The positive cases 06, 07, 10, and 11 now explicitly include the required core
`kind` and `interface.type` properties in their closed extension schemas.
Their recursive shapes, union branches, scoped domains, and exact source names
retain their original constraints.

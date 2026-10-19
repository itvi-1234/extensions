# Extension Binding Generation Implementation Standard

## 1. Purpose and scope

This document defines the architecture, artifact contracts, verification, and
delivery process for generated Runtime Conditions extension bindings.

The system converts extension definitions and their complete dependency closure
into deterministic, language-native declaration packages. A shared Go resolver
and normalizer interpret extension semantics. Native Go and Python emitters
produce source and structural binding manifests. A Go orchestrator coordinates
resolution, generation, verification, repository updates, and release planning.

Automated delivery generates and commits selected Go packages to `main`, then
publishes them as public Go modules through a separate manual workflow. Public
imports use `runtimeconditions.io/x/<provider>/<extension>`. Python emission and
local packaging are supported; automated Python delivery and registry
publication are outside the enabled Go workflows.

The binding implementation remains in `extensions`. The downstream common `rc`
executable belongs to `rc-cli` and will expose this implementation through a
thin adapter. Language-specific profilers remain independently implemented and
released programs.

The following requirements apply throughout the pipeline:

1. Extension vocabulary and JSON Schema drive behavior. Production code MUST
   NOT select an algorithm by a particular extension ID, kind, interface type,
   field, value, package key, or repository path.
2. Extension definitions are immutable generation inputs. Generation MUST NOT
   rewrite them to accommodate an emitter limitation.
3. Unsupported structure MUST fail with a deterministic diagnostic. It MUST NOT
   be omitted, guessed, or widened to an unconstrained native type.
4. Identical semantic inputs, delivery configuration, and tool artifacts MUST
   produce identical persisted package bytes.
5. Runtime Conditions models, manifests, locks, plans, and reports use YAML.
   Native source, HTML discovery pages, package-manager metadata, and archives
   retain their required formats. Canonical JSON is an internal hashing and
   comparison representation.
6. Generated types enforce structure. Complete core and extension semantic
   validation belongs to profile generation.
7. Local commands and GitHub Actions use the same generation, verification,
   packaging, and compatibility implementations.
8. Publication promotes verified artifacts without rebuilding them.
9. Semantic identity and source-resolution evidence remain separate. Transport
   details and source-byte digests MUST NOT affect the normalized model digest.

## 2. Ownership and source layout

The source layout is:

```text
extensions/
  catalog/
  bindings/
    <package-key>/
      go/
      python/
  tooling/
    extension-bindings/
      IMPLEMENTATION.md
      README.md
      packages.yaml
      toolchain.lock.yaml
      model/
        runtimeconditions.extension-semantic.schema.yaml
        runtimeconditions.binding-model.schema.yaml
        runtimeconditions.binding-manifest.schema.yaml
        runtimeconditions.binding-release.schema.yaml
        runtimeconditions.package-catalog.schema.yaml
        runtimeconditions.toolchain-lock.schema.yaml
        runtimeconditions.file-manifest.schema.yaml
        conformance/cases/
        conformance/expected/
      normalizer/
        cmd/rc-binding-model/
      emitters/
        go/
          cmd/rc-go-bindings/
        python/
          src/runtimeconditions_binding_emitter/
      orchestrator/
        cmd/rc/
      ci/
        generate.py
        publish.py
        test_generate.py
        test_publish.py
    common/
      go_bindings.py
      build_extensions_site.py
      serialization.py
  .github/
    actions/binding-tools/action.yml
    workflows/
      extension-binding-normalizer.yml
      binding-generate.yml
      binding-promote.yml
      check-extensions-site-builds.yml
      notify-docs-site.yml
```

The normalizer, Go emitter, and orchestrator are separate Go modules. The Python
emitter is a Python package. Shared site and publication coordinate validation
lives in `tooling/common/go_bindings.py`.

Repository responsibilities are:

| Repository | Responsibility |
| --- | --- |
| `extensions` | Extension catalog, binding schemas, resolver, normalizer, emitters, orchestrator, shared conformance tests, committed generated packages, and binding delivery workflows. |
| `rc-cli` | Common `rc` executable, Cobra command tree, binding adapter, profiler dispatch, shared diagnostics, and system-package distribution. |
| `go-rc-profiler` | Go source analysis, installed Go binding inspection, semantic profile validation, and profiler releases. |
| `python-rc-profiler` | Python source analysis, installed Python binding inspection, semantic profile validation, and profiler releases. |
| `runtimeconditions.github.io` | Deployment of the documentation site and the static output produced by the extensions site builder. |

Generated binding packages are workload dependencies installed by the native
language package manager. The common CLI, generators, and profilers are developer
tools with their own release identities.

## 3. Pipeline and execution boundaries

The pipeline is:

```text
extension root + dependency definitions + core schema + package catalog
                              |
                              v
                    shared Go resolver
                       /             \
                      v               v
             dependency lock     semantic closure
                                       |
                                       v
                              shared Go normalizer
                                       |
                                       v
                       runtimeconditions.binding-model.yaml
                                       |
                         +-------------+-------------+
                         |                           |
                         v                           v
                    Go emitter                 Python emitter
                         |                           |
                         +-------------+-------------+
                                       |
                                       v
                         assembled package resources
                                       |
                                       v
                  native installation and package verification
                                       |
                                       v
                         committed generated source
                                       |
                                       v
                    package and compatibility verification
                                       |
                                       v
                   immutable module tags and release assets
```

The resolver owns dependency resolution, exact definition identity, semantic
validation, vocabulary ownership, and conflict detection. The normalizer owns
language-neutral schema interpretation and structural projection.

Each emitter consumes only a validated normalized model and a native package
target configuration. Emitters MUST NOT resolve extension definitions, read the
catalog for semantic rules, or reinterpret JSON Schema independently.

The orchestrator assembles package resources, verifies their relationships,
invokes native tooling, compares generated and committed trees, and prepares
release artifacts. CI helpers select targets, manage Git operations, check public
discovery, and publish the resulting artifacts.

## 4. Package catalog and tool identities

### 4.1 Delivery configuration

`tooling/extension-bindings/packages.yaml` has the envelope:

```yaml
apiVersion: runtimeconditions.io/package-catalog/v1alpha1
kind: RuntimeConditionsPackageCatalog
repositoryUrl: https://github.com/runtimeconditions/extensions
packages:
  common-integrations:
    rootExtension: https://runtimeconditions.io/extensions/common-integrations/v1alpha1/runtimeconditions.extension.yaml
    coreProfileSchemaVersion: 0.2.0
    languages:
      go:
        coordinate: runtimeconditions.io/x/rc/common
        name: common
        version: 0.1.0
        sourceDirectory: bindings/common-integrations/go
        languageVersion: 1.25.0
        publicationMode: github-tag
```

A package set declares one extension root and one core schema version. Each
language target declares its native coordinate, import/package name, independent
package version, generated source directory, exact compiler or interpreter
version, and publication mode. A `registry` target also declares `registryId`.

The target key is `<package-key>:<language>`. Package keys match
`^[a-z0-9]+(?:-[a-z0-9]+)*$`; language keys match `^[a-z][a-z0-9-]*$`.
The generated source directory is `bindings/<package-key>/<language>`.

The catalog contains delivery data. Kinds, fields, value domains, schemas,
dependencies, and requiredness come from the extension definitions.

### 4.2 Workspace and released tools

The pipeline supports workspace tooling and a released toolchain lock.
Automated Go generation and publication build the orchestrator, normalizer, and
Go emitter from the checked-out workspace. Publication does not require a
separate tooling release before a generated package can be published.

Generated artifacts record actual tool identities:

- The model records the normalizer name, version, and artifact SHA-256.
- The structural manifest records emitter identity as
  `<name>@sha256:<digest>` and an emitter version.
- The release manifest records orchestrator and profiler identities.
- Python emitter identity uses its installed artifact or the actual workspace
  source snapshot, as appropriate to the selected execution mode.

A lock with `status: released` requires the configured installed tools and
checks their versions and digests. Workspace mode builds or locates development
tools and records what actually ran. Neither mode may substitute an invented
release identity.

The language target controls the exact compiler or interpreter used for package
verification. The Go delivery catalog uses Go `1.25.0`; its Python targets
specify Python `3.12.10`. Helper scripts have a separate Python runtime and do
not enable Python binding delivery by themselves.

### 4.3 Shared Actions prerequisites

`.github/actions/binding-tools/action.yml` is shared by Go generation and
publication. It:

1. Validates the requested Go targets and selects their exact Go compiler.
2. Installs Python `3.12.10` and PyYAML `6.0.3` for CI helpers.
3. Installs the selected Go compiler with automatic toolchain switching disabled.
4. Downloads and verifies the pinned Go profiler archive and core schema.
5. Builds workspace `rc` from `orchestrator/cmd/rc`.
6. Exposes the selected targets, source commit, compiler version, generator path,
   and core-schema path to the calling workflow.

The action owns the prerequisite URLs and source checksums. Its core schema
snapshot supplies the catalog's `0.2.0` input. All downloads are verified before
use. Temporary tools, bytecode, and build intermediates remain outside the
checkout.

## 5. Extension identity and resolution

### 5.1 Definition identity

An extension definition uses `metadata.id` as its exact, absolute URI identity.
`metadata.version` is an optional annotation. Dependency lists contain exact
extension ID strings. A version annotation is not appended to an ID to form a
new resolver key.

For example:

```yaml
apiVersion: runtimeconditions.io/v1alpha1
kind: RuntimeConditionsExtensionDefinition
metadata:
  id: https://runtimeconditions.io/extensions/env-configuration/v1alpha1/runtimeconditions.extension.yaml
  version: v1alpha1
spec:
  dependencies:
    - https://runtimeconditions.io/extensions/common-integrations/v1alpha1/runtimeconditions.extension.yaml
```

The extension ID and public Go module coordinate serve different purposes. The
extension ID identifies semantic input; `runtimeconditions.io/x/rc/env`
identifies its Go package.

The resolver preserves the exact ID spelling. It MUST NOT infer identity from a
repository path, split an ID into provider/service/version components, or impose
a particular URI path layout. For HTTPS retrieval, the ID is the retrieval URL.
The returned document's `metadata.id` MUST equal the requested ID.

### 5.2 Resolution sources

Resolution supports explicitly supplied file overrides, configured catalog
roots, package-local extension resources, a verified content-addressed cache,
and HTTPS retrieval. Local candidates are indexed by parsed `metadata.id`.

An absolute URI may be supplied through an explicit local source without an
automatic transport for its scheme. Automatic network retrieval is provided for
HTTPS. An unsupported automatic transport fails with a diagnostic requiring an
explicit source. Plain HTTP is not an automatic retrieval backend.

Resolution MUST reject:

- An invalid or empty absolute URI, whitespace, or control characters in an ID.
- Different source bytes registered for the same ID.
- A requested ID that differs from the resolved definition's ID.
- Missing dependencies and dependency cycles.
- Duplicate or conflicting vocabulary ownership in the same semantic scope.
- A cache entry whose bytes differ from its content-addressed filename.

Local overrides are explicit development inputs and are forbidden with a
released toolchain lock. A package cache accelerates retrieval; it does not
establish identity.

### 5.3 HTTPS and lock behavior

HTTPS resolution validates certificates, rejects redirects, and requires a host
without embedded credentials. Downloads have bounded size and timeouts.

Development resolution may fetch an unlocked definition and record the exact
result. Released resolution requires a source digest and locator lock before
fetching. A locked locator MUST equal the requested HTTPS ID, and fetched bytes
MUST match the locked source digest. A supplied semantic digest is also checked.
Network-disabled resolution MUST perform no outbound request.

The extension cache stores files named `<sha256>`, `<sha256>.yaml`, or
`<sha256>.yml`. Each entry is hashed before it can participate in resolution.

### 5.4 Closure and dependency lock

Resolve the root and every transitive dependency, detect cycles through the
active traversal stack, then produce a stable topological order with providers
before dependents. Independent ties are ordered by exact ID.

Each dependency-lock entry contains:

- Extension ID and any declared version annotation.
- Exact source-byte SHA-256 and semantic SHA-256.
- Exact direct dependency ID strings.
- Source backend and locator.

The semantic closure contains the ID, optional version, semantic digest, and
direct dependency IDs. It excludes source-byte digests and transport evidence.

The lock MUST cover the closure exactly once per ID. Missing, extra, duplicate,
or mismatched entries stop generation. Source records are checked against the
resolved bytes; semantic records are checked against the normalized inputs.
The lock is embedded in `runtimeconditions.binding-release.yaml`.

## 6. Canonical data and normalized model

### 6.1 Canonicalization

Validate definitions against
`model/runtimeconditions.extension-semantic.schema.yaml` before interpreting
or hashing their semantics. Parsing is data-only and rejects duplicate mapping
keys and unsupported YAML constructs.

Source-byte SHA-256 hashes the exact input bytes. Semantic SHA-256 hashes the
canonical JSON representation of validated data after schema-defined sequence
normalization. Mapping keys use canonical ordering. Set-valued sequences are
sorted; source-ordered sequences retain their order.

Dependency and vocabulary lists are sets. JSON Schema `enum`, `required`,
`allOf`, `anyOf`, and `oneOf` lists are normalized as sets. Arrays used as data,
`prefixItems`, and `examples` preserve source order. Schema annotations identify
the applicable ordering rule.

Generated YAML uses UTF-8, LF line endings, one trailing newline, string mapping
keys, deterministic field order, quoted ambiguous strings, and omitted unused
optional fields. Persisted model YAML contains no comments, anchors, aliases,
merge keys, or custom tags.

### 6.2 Model envelope and contents

The checkpoint is `runtimeconditions.binding-model.yaml`:

```yaml
apiVersion: runtimeconditions.io/binding-model/v1alpha1
kind: RuntimeConditionsBindingModel
```

Its schema is `model/runtimeconditions.binding-model.schema.yaml`. The model
contains:

- Model API version and normalizer identity.
- Core schema ID, version, and semantic digest.
- Root extension ID, optional version annotation, and semantic digest.
- Complete extension closure and direct dependency edges, using exact ID
  strings for references.
- Vocabulary ownership, owned declarations, and imported declaration contracts.
- Kind and interface scopes, condition fields, and interface fields.
- Explicit field-path segments, including array traversal.
- Scoped value domains with exact serialized values.
- Complete applicable JSON Schemas and structural projections.
- Validation constraints and semantic provenance.
- A semantic SHA-256 for the model with its own digest field excluded.

Owned and imported declarations form a complete, non-overlapping partition of
kind declarations in the closure. Imported declarations remain owned by their
provider package.

The model MUST NOT contain source-byte hashes, source backends, source locators,
dependency-lock digests, native symbol names, package coordinates, or
language-specific types. Presentation-only definition changes and changes to
resolution transport MUST leave model bytes and the model digest unchanged.

Provenance identifies an owning extension and semantic digest, a vocabulary or
schema coordinate, and a JSON Pointer where a node comes from JSON Schema.
Set reordering MUST NOT change semantic coordinates.

## 7. Structural normalization

Schemas use JSON Schema Draft 2020-12. An omitted dialect selects Draft 2020-12;
a different explicit dialect fails. Exact schemas are retained for semantic
validation even when native type systems cannot express every constraint.

All extensions use these normalization rules:

1. An owned kind becomes a declaration. Dependency-owned kinds become imported
   declaration contracts.
2. An interface type becomes an object shape in its exact kind/interface scope.
   Fixed `kind` and `interface.type` values are generated metadata.
3. Condition and interface fields retain their exact serialized property names
   and placement. Scope expansion uses the complete resolved vocabulary.
4. Objects become object shapes; scalars retain their structural scalar type.
5. Arrays become collection shapes, with explicit array traversal in paths.
   Object-valued items receive shapes derived from their full property paths.
6. Schema-valued `additionalProperties` becomes a map-value shape.
7. String enums, string constants, and scoped string `fieldValues` become named
   value domains. Non-string values remain validation constraints.
8. Object-only `oneOf` and `anyOf` branches project to a merged property set.
   A property is structurally required only when every alternative requires it.
   Branch-specific requirements remain semantic constraints.
9. Heterogeneous alternatives remain explicit union shapes.
10. `allOf` combines constraints and object requirements conjunctively.
    Incompatible structural types fail normalization.
11. Local JSON Pointer `$ref` values resolve within the containing schema.
    Referenced definitions become named shapes; recursive references remain
    references instead of being expanded indefinitely.
12. External references, anchor references, and unsupported structure-changing
    keywords fail with the extension ID, schema coordinate, JSON Pointer, and
    relevant keyword.
13. Cardinality, uniqueness, ranges, lengths, patterns, formats, conditionals,
    and relationships between branches remain exact validation constraints.
14. Applicable schemas combine additively. Structural conflicts and empty value
    intersections fail normalization.
15. Each scoped value domain must name an existing field path, and every member
    must be accepted by all applicable schemas.

Descriptions, examples, repository paths, and operation-specific conventions
MUST NOT determine the generated API.

## 8. Native package dependencies

The extension dependency graph is projected onto each requested language.
Every direct extension dependency requires a corresponding native package
provider in that language. A missing provider fails before source emission.

Dependent packages import provider contracts. They MUST NOT copy provider-owned
declarations into their own package or claim ownership of imported vocabulary.
Marker interfaces and protocols support additive fields across packages.

Candidate builds use exact tested provider versions. Package release metadata
also records the compatible interval and exact provider archive SHA-256.

- Go `go.mod` declares the tested version as its minimum requirement.
- Python metadata declares `>=<tested>,<next-breaking>`.
- For a `0.y.z` dependency, the next breaking boundary is `0.(y+1).0`.
- For a dependency at or above `1.0.0`, it is `(major+1).0.0`.

Native package resolution determines the actual installed packages. Go uses
module download, verification, and listing commands. Isolated candidate
verification uses a local module proxy and module cache. Python uses isolated
virtual environments, wheel installation, and installed distribution metadata.

Workspace wiring and temporary native consumers are build inputs. Published Go
packages and end-user installation MUST NOT depend on local `replace`
directives, sibling source checkouts, or recursively scanning package caches.

## 9. Emitter and package contracts

### 9.1 Emitter interface

Each emitter accepts:

```text
<emitter> --model runtimeconditions.binding-model.yaml \
  --package-config <native-target.yaml> --output <new-empty-directory>
```

The Go executable is `rc-go-bindings`. The Python emitter exposes its native
package command and an `emit` operation. The orchestrator supplies its assembly
mode when preparing deliverable Python source.

An emitter rejects an unsupported model API, invalid target, unsupported shape,
or non-empty output directory. It writes formatted production source, native
package metadata, and `runtimeconditions.bindings.yaml`.

Native names derive from exact source names and the target language's naming
rules. The model remains free of native naming decisions. The manifest retains
exact serialized names and model coordinates.

Shared API rules are:

- Declaration functions are inert source anchors returning `Declaration`.
- Object, collection, and map shapes use native construction syntax.
- Root fields remain declaration arguments or root properties.
- Array-item names use the property path and `Item`, without singularization.
- Names are allocated for the complete package before source is written.
- Eligible collisions use parent path and scope components deterministically.
  Unresolvable collisions fail instead of gaining arbitrary suffixes.
- Alternative branches do not create operation-specific constructors.
- Cross-field semantic constraints are enforced by profile validation.

### 9.2 Go API

An owned kind becomes a declaration function accepting its generated
`<Kind>Field` marker interface. Applicable interface objects and additive fields
implement that interface. Cross-package marker methods are exported and derive
from the owning declaration coordinate.

Objects become structs, collections become slices, and maps use native map
types. Required scalar and enum fields use values; optional scalar and enum
fields use pointers. Optional structured values preserve omission according to
the generated reference shape. String domains become named scalar types with
typed constants qualified by their domain type.

Go names preserve Unicode letters and use language-specific token boundaries
and Pascal case for exported names. Invalid leading-digit identifiers and
collisions with fixed declaration symbols fail with semantic coordinates and
the conflicting native symbol. Declaration symbols are not renamed to conceal
a collision.

Packages contain `bindings.go` and `go.mod`. Source is `gofmt` formatted and
passes compilation and `go vet` with the configured compiler. Package-scope
usage may use `var _ = package.Declaration(...)`; declarations may also appear
inside functions when the profiler can statically determine their arguments.

Public Go package names match the final component of the base public import
path, so callers do not need explicit aliases.

### 9.3 Python API

Owned kinds become functions returning inert declarations. Kind field
contracts use structural protocols. Objects become frozen, keyword-only
dataclasses; optional fields accept `None`; collections and maps use native
sequence and mapping forms. String value domains use scoped `StrEnum` members.

Classes and aliases use Pascal case; functions and fields use snake case;
constant members use upper snake case. Reserved words, leading digits, and
special-method spellings follow explicit Python escaping rules.

Python source lives under `src/<import-package>/`, includes typing metadata,
and is packaged through `pyproject.toml`. Verification uses the configured
interpreter, Ruff formatting, byte compilation, and strict mypy checking.

### 9.4 Package assembly

The orchestrator adds these fixed resources without rewriting emitter output:

| Resource | Purpose |
| --- | --- |
| `runtimeconditions.bindings.yaml` | Structural relationships between native symbols and model coordinates; emitted with the source. |
| `runtimeconditions.binding-model.yaml` | Exact normalized model consumed by the emitter. |
| `runtimeconditions.extension.yaml` | Exact validated root definition bytes. |
| `runtimeconditions.binding-release.yaml` | Native package identity, model identity, dependency lock, tested native dependencies, and tool provenance. |

Go places all four beside `bindings.go` in the package directory returned by
`go list`. Python includes them as package data under `src/<import-package>/`.
Dependency definitions are supplied through their own installed packages.

The package-tree root also contains `runtimeconditions.file-manifest.yaml`,
which hashes every declared package file except itself. Delivered source trees
contain production source, native metadata, the four resources, and this file
manifest. Conformance source and expected profiles belong to shared tooling
fixtures and temporary consumers.

Generated headers identify non-editable output, model digest, and emitter
version. They contain no timestamp or host path. Source-byte digests and
resolution locators remain release provenance.

## 10. Structural manifest and profiler integration

The structural manifest envelope is:

```yaml
apiVersion: runtimeconditions.io/bindings/v1alpha2
kind: RuntimeConditionsBindingManifest
```

`model/runtimeconditions.binding-manifest.schema.yaml` defines its declarations,
imported marker contracts, root bindings, and named types. References identify
both native structure and exact model coordinates or JSON Pointers.

The manifest records native package identity, model API and digest, root
extension ID and semantic digest, and emitter identity. Its extension identity
is independent of the optional definition version annotation.

The independently installed profiler begins from imported symbols, asks the
native package manager for their resolved locations, and reads the fixed
package resources there. An application author needs installed binding modules
and the profiler, without an extensions or generator source checkout.

Profilers MUST:

1. Type-check or parse source with the language's native analysis tools without
   executing the application or declaration functions.
2. Verify native package identity against installed package metadata.
3. Validate all packaged resource schemas and recompute model and root
   definition digests.
4. Verify dependency-lock coverage, provider identities, package versions,
   compatible intervals, and dependency archive content.
5. Check manifest-to-model references and vocabulary ownership.
6. Reconstruct Conditions only from supported static expressions.
7. Identify extensions that directly contribute vocabulary and traverse their
   complete installed dependency closure.
8. Validate core profile structure and every applicable extension schema.
9. Write a profile only after all checks succeed.

Current binding profiles list complete extension ID URIs directly. URI
references in dependency locks and package-dependency records are resolved
against the verified model closure; optional annotations are not inferred by
parsing URI segments.

The Go profiler supports the exact approved core `0.2.0` input identity used by
these bindings while validating generated output with core `0.4.0`. This
compatibility requires the approved IDs, versions, and semantic digests.
Other core identities must satisfy the profiler's installed-schema checks.

Go module ZIP verification accepts the recorded publisher archive bytes or
reconstructs the publisher's deterministic ZIP from the downloaded module
files. The reconstructed SHA-256 must match the recorded value exactly. Proxy
ZIP encoding differences therefore do not remove content verification.

Static pointer literals can express optional scalar values, for example:

```go
common.KeyValue{
    Engine: &[]common.KeyValueEngine{common.KeyValueEngineRedis}[0],
}
```

A variable, function call, or other expression outside the profiler's supported
static subset fails with a diagnostic rather than producing a partial profile.

## 11. Verification and shared conformance

### 11.1 Shared tooling coverage

The shared suites exercise the generation mechanism using language-neutral
fixtures and temporary native consumers. The fixture set covers:

1. Owned kind and interface.
2. Additive fields targeting provider-owned vocabulary.
3. Transitive dependency closure.
4. Dependency cycles.
5. Vocabulary ownership conflicts.
6. Recursive local references.
7. Object alternatives with branch-dependent required fields.
8. Heterogeneous unions.
9. Collections and maps.
10. Scoped domains and native naming collisions.
11. Source-name preservation.
12. Unsupported structural keywords.
13. Dependencies that contribute validation schemas without direct declarations.

Positive fixtures retain expected normalized YAML; negative fixtures retain
deterministic diagnostics. Native API exercises are generated or materialized
in temporary consumers, without adding test trees to delivered packages.

Tests cover repeated normalization and emission, set-order permutations,
source-order preservation, archive inventories, native API extraction, package
composition, resolver backends, release classification, workflow helpers, and
repository synchronization. Production algorithms remain independent of
fixture identifiers.

Shared tooling tests require no profiler checkout, binary, or wheel.
Profiler-dependent integration and cross-repository compatibility suites belong
in a separate integration repository. The presence of profiler identity in
package provenance is distinct from running a profiler integration suite.

### 11.2 Per-package verification

`verify`, `check`, `package`, and `update` enforce package structure through:

- Model and resource-schema validation, including recomputed semantic digests.
- Catalog, native metadata, root definition, manifest, and release identity
  consistency.
- Dependency installation and exact provider relationships.
- Actual tool and profiler artifact identities recorded in provenance.
- Native formatting, compilation, and static analysis.
- AST-derived native API equality with the normalized model projection.
- Re-emission and assembly equality with the candidate package tree.
- Complete archive inventory and file-byte equality.
- Complete file-manifest coverage and digests.

Reports identify `scope: package-structure`. Gate entries 7 through 11 are
`not-applicable` for individual delivered packages. Generated API unit exercises,
conformance profile comparisons, and negative semantic declarations are not
represented as per-package checks that ran.

A failed applicable check stops update, packaging, or publication. All selected
candidates are verified before `update` synchronizes repository source.

## 12. Local orchestration

### 12.1 Commands

The local entry point is:

```text
rc bindings resolve
rc bindings normalize
rc bindings generate
rc bindings verify
rc bindings package
rc bindings plan-release
rc bindings check
rc bindings update
```

The executable is built from `orchestrator/cmd/rc`. The reusable command
boundary is `orchestrator.Run(context.Context, []string, io.Writer, io.Writer)`;
it accepts the `bindings` command group and returns errors to its caller.
The executable supplies process arguments and streams and chooses the exit code.

| Command | Behavior and output |
| --- | --- |
| `resolve` | Prints semantic closure and dependency lock as YAML; writes only explicitly requested closure/lock files. |
| `normalize` | Resolves and validates inputs, then prints the normalized model; optional model and lock output files. |
| `generate` | Writes selected generated package trees beneath a required new or empty output directory. |
| `verify` | Verifies supplied package trees or selected committed trees; prints YAML and optionally writes a report. |
| `package` | Regenerates for comparison, requires equality with committed source, verifies it, and archives the committed trees. |
| `plan-release` | Compares committed targets with published target artifacts and reports compatibility and version requirements. |
| `check` | Regenerates and verifies, then compares selected committed trees without modifying them. |
| `update` | Generates and verifies all candidates, then synchronizes selected committed trees and removes stale generated files. |

All commands share target selection, configuration discovery, resolution,
normalization, and native tooling behavior. `update` is the sole binding command
that synchronizes committed generated source.

### 12.2 Inputs and filesystem behavior

Common configuration flags include `--packages`, `--toolchain-lock`,
`--tooling-dir`, `--cache`, and `--work-dir`. Target selection uses repeatable
`--target <package-key>:<language>` flags; omission selects all configured targets.

Configuration discovery walks ancestors for the nearest directory containing
both catalog and toolchain configuration. An explicit configuration path sets
the sibling default for the other configuration file. Supplied relative paths
resolve against the caller's working directory.

Resolution commands accept explicit extension roots, local overrides, catalog
roots, a dependency lock, and a core-schema file where applicable. Output,
input, and report flags belong to the commands that consume them.

Default invocations create no persistent cache or fixed work tree. Required
subprocess files use an invocation-specific temporary workspace removed on
return. Explicit `--work-dir` retains required intermediates; explicit `--cache`
enables verified content-addressed reuse.

Explicit file outputs must be new files, and directory outputs must be new or
empty directories. Explicit outputs cannot be placed inside committed
`bindings/`; callers use `update` for that operation. Symlink and path-escape
checks protect source and output boundaries.

Stdout remains machine-readable where the command promises YAML. Human progress
and error diagnostics use stderr. Errors produce a nonzero process result.

## 13. Integration with the common `rc` CLI

### 13.1 Command ownership

`rc-cli` will supply the user-facing Go executable and Cobra command tree. It
will expose the eight `rc bindings` operations through a thin adapter to the
binding tooling maintained in this repository.

The adapter MUST preserve target and configuration defaults, argument meaning,
working-directory behavior, output formats, filesystem effects, cancellation,
and nonzero failure behavior. Binding flags stay scoped to `rc bindings` and
its subcommands. Cobra commands delegate semantic interpretation and generation
to the tooling in `extensions`.

The binding tooling owns:

- Definition resolution and dependency locks.
- Semantic normalization and model schemas.
- Native emission and package resource assembly.
- Verification, deterministic regeneration, and repository synchronization.
- Compatibility classification and release planning.

The common CLI owns command discovery, help, shared configuration and
diagnostics, version reporting, tool discovery, and process dispatch. It MUST
NOT maintain a second binding generator or duplicate compatibility rules.

### 13.2 Binding adapter and distribution

The reusable Go `orchestrator.Run` boundary and standalone command interface
provide integration boundaries. An adapter may invoke a versioned Go API or an
explicitly selected standalone tooling artifact, while preserving the command
contract defined here.

For an in-process adapter, the orchestrator, normalizer, and Go emitter modules
must be available as a resolvable, versioned dependency set. Relative `replace`
directives used for development inside `extensions` do not supply dependencies
to a downstream module. The schema bundle and required emitter resources must
also be located through an explicit installed tooling path.

For a subprocess adapter, invoke the selected binding tool with an argument
vector, preserve the caller's directory and streams, and propagate cancellation
and failure. Select its executable by an explicit managed path; dispatch MUST
NOT recursively resolve the common `rc` command as its own backend.

The CLI integration must retain actual executing-tool provenance and all lock
checks. A separately installed CLI version is not a substitute for an emitter,
normalizer, orchestrator, or profiler artifact identity. Workspace operation
remains explicit; released operation verifies selected artifacts and digests.

The common CLI and binding tooling are independently versioned. Their supported
interface and artifact selection must be declared as part of CLI packaging.
System packages distribute the CLI and developer tools; applications continue
to install generated bindings through Go modules or their language equivalent.

### 13.3 Profiler routing

Profiling is a separate command family:

```text
rc profile generate <Go-profiler arguments>
rc profile go generate <Go-profiler arguments>
rc profile python <Python-profiler arguments>
```

The common CLI's default installation includes the independently packaged Go
profiler. Other languages are optional profiler add-ons. Each profiler owns its
source parser, language runtime requirements, flags, and semantic validation.

After selecting the profiler, the CLI forwards its argument vector without
translating language-specific options. Backend help and output remain owned by
the profiler. Launcher diagnostics must not contaminate profile data on stdout.

Interactive discovery may use managed installations, explicit configuration,
and `PATH`, subject to protocol compatibility checks. Binding verification and
release operations must continue to honor explicitly selected or locked tools;
interactive discovery must not replace them silently.

### 13.4 CI integration

The GitHub workflows call the same binding interface used locally. Adoption of
the common CLI must retain the shared prerequisite setup, exact native compiler,
resource discovery, package verification, source equality checks, and actual
tool identities.

The common CLI does not replace `generate.py`'s controlled bot commit behavior
or `publish.py`'s GitHub and discovery preflight. It supplies the binding command
backend used by those helpers. Generation and publication remain separate
operations with the permissions and artifact boundaries specified below.

## 14. Package versions and compatibility

Each language package has an independent SemVer version declared in the catalog.
Extension annotations and native package versions do not have to match.

Release planning automatically locates the previous published target artifacts.
It compares:

1. Normalized extension closures and applicable schemas.
2. Native AST-derived exported APIs.
3. Structural binding manifests and declaration behavior.
4. Direct native package dependencies.
5. Minimum language versions and package coordinates.

Removal, rename, incompatible type change, optional-to-required change, value
removal, validation tightening, or an unprovable schema-compatibility change is
breaking. Compatible public additions and validation relaxations are additions.
Compatible implementation, packaging, or metadata corrections require an
appropriate correction release.

For packages at or above `1.0.0`, breaking changes require a major bump,
compatible additions a minor bump, and compatible corrections a patch bump.
For `0.y.z` packages, breaking changes require a minor bump and compatible
additions or corrections require a patch bump. The declared version must meet
or exceed the mechanically required bump. Unchanged package content does not
require a new release.

A package version names immutable content. Different generated or packaged
bytes cannot reuse a published version. A package-major change must update the
native coordinate when required by the package manager and regenerate affected
dependents.

## 15. Committed source and retained artifacts

The repository commits tooling, schemas, package configuration, conformance
fixtures, expected normalized models and diagnostics, and generated source for
enabled targets under `bindings/<package-key>/<language>`.

Each generated package tree includes its readable source, native package
metadata, four package resources, and file manifest. Tool identities,
dependency locks, native dependency artifact digests, and package versions are
retained in the applicable generated metadata. Regeneration is the mechanism
for updating these files.

Compiled binaries, bytecode, wheels, source distributions, ZIP archives, native
consumer caches, temporary environments, workflow logs, release plans, and
publication receipts remain outside committed generated source. Workflow
artifacts carry verified release outputs between jobs.

Generation may commit updated package source to `main` after all selected
candidates pass verification. Publication independently requires a clean
checkout and byte equality between fresh generation and the selected committed
trees. Packaging archives the committed trees.

## 16. Automatic Go generation

`.github/workflows/binding-generate.yml`, named **Generate and commit Go
bindings**, runs on relevant changes to `main` and supports manual dispatch on
`main`.

Selection precedence is:

1. A non-empty manual `targets` input.
2. The repository variable `BINDING_GENERATION_TARGETS`.
3. `common-integrations:go,env-configuration:go`.

The input is a comma-separated list of `package-key:go` targets. `all` selects
every configured Go target; it does not skip a target lacking valid inputs.
One run requires one exact Go compiler. Python targets are not accepted by
these workflows.

The generation job:

1. Checks out current `main` and records its exact source commit.
2. Runs the shared `binding-tools` action.
3. Runs CI-helper and shared Go tooling suites.
4. Invokes `generate.py update`, which runs `rc bindings update` for the
   selected targets with the verified core schema and profiler artifact.
5. Invokes `generate.py commit` to stage only selected generated directories.
6. Creates a `github-actions[bot]` commit when package files changed.
7. Pushes through an ordinary fast-forward update to `main`.
8. Dispatches the existing documentation deployment through
   `DOCS_REPO_DISPATCH_TOKEN`, including when generation required no new commit.

The commit helper rejects unexpected modifications outside selected directories,
a non-empty preexisting index, movement of the checked-out input commit, or a
remote `main` that advanced during generation. It never rebases or force-pushes
candidates over newer inputs. Unchanged output creates no commit.

Generation and publication share concurrency group `binding-generation-main`
with cancellation disabled. The generation job has `contents: write`; branch
rules must permit its bot commit. Bot pushes made with `GITHUB_TOKEN` do not
supply a recursive generation mechanism, so documentation dispatch is explicit.
Generation does not create module tags or releases.

## 17. Public Go module discovery

### 17.1 Import coordinates

Go bindings are public modules under:

```text
runtimeconditions.io/x/<provider>/<extension>
```

Their source remains in this repository. The package catalog keeps public
coordinates separate from source directories:

| Target | Public module | Package | Source directory |
| --- | --- | --- | --- |
| `common-integrations:go` | `runtimeconditions.io/x/rc/common` | `common` | `bindings/common-integrations/go` |
| `env-configuration:go` | `runtimeconditions.io/x/rc/env` | `env` | `bindings/env-configuration/go` |
| `aws-s3:go` | `runtimeconditions.io/x/aws/s3` | `s3` | `bindings/aws-s3/go` |

Configured coordinates do not imply that a target has generated source or a
published version. Additional targets become discoverable when their valid
source trees exist.

Module names, package names, versions, source directories, repository URL, and
major-version suffixes are validated centrally by `go_bindings.py`. Duplicate
public prefixes, stale module declarations, and mismatched package clauses fail.

The package name equals the public path's final base component. An alias is
optional:

```go
import "runtimeconditions.io/x/aws/s3"
```

### 17.2 Static discovery pages

`tooling/common/build_extensions_site.py` builds extension definition artifacts
and Go discovery pages into the same static site output. Extension YAML is
published at the path of each definition's `metadata.id`.

For each generated Go module, the builder writes
`/x/<provider>/<extension>/index.html` with an early metadata tag such as:

```html
<meta name="go-import" content="runtimeconditions.io/x/rc/common git https://github.com/runtimeconditions/extensions bindings/common-integrations/go">
```

The four fields identify the public import prefix, Git transport, repository,
and module subdirectory. This subdirectory discovery form requires Go 1.25 or
later. For major versions `v2` and above, the module coordinate has its required
`/vN` suffix, and the builder publishes both the base discovery page and the
versioned page.

A `/x/` index links generated modules. Pages include installation commands,
unaliased imports, source links, and Go documentation links. The builder emits
no page for a target without generated Go source.

The domain `runtimeconditions.io` is served through the existing
`runtimeconditions.github.io` deployment. That deployment already invokes the
extensions site builder. Discovery changes are implemented in the extensions
repository and delivered through that build.

`.github/workflows/notify-docs-site.yml` dispatches `extensions-updated` for
relevant catalog, site-builder, configuration, and binding changes. The
generation workflow also dispatches after its bot commit. Publication requires
the live discovery pages to be deployed before module tags are created.

## 18. Manual Go publication

### 18.1 Workflow inputs and jobs

`.github/workflows/binding-promote.yml`, named **Publish Go bindings**, uses
manual dispatch on `main` with:

- `targets`: comma-separated `package-key:go` targets or `all`; empty uses
  `BINDING_GENERATION_TARGETS` and then the common/env default.
- `dry_run`: boolean, default `true`.

Publication expands the requested set to include native package providers and
orders them before dependents. Every selected provider must have valid committed
source and a catalog version consistent with dependency metadata.

A read-only build job uses the shared prerequisites, runs helper tests, and
invokes `publish.py build`. That helper calls `rc bindings package` and
`rc bindings plan-release`, writes checksums and publication metadata, and
uploads `go-binding-assets` with seven-day workflow retention.

A separate job with `contents: write` checks out that exact source commit and
downloads those exact artifacts. It performs promotion without invoking an
emitter or rebuilding archives.

### 18.2 Complete preflight

Before creating any remote tag or release, `publish.py promote` checks:

1. The checkout is clean and matches the packaged source commit and target set.
2. Current remote `main` still equals that source commit.
3. Release-plan target identities and versions match the catalog.
4. Every packaged artifact matches the output file manifest and `SHA256SUMS`.
5. Source and module archives contain exactly the committed file inventory and
   file bytes at their expected prefixes.
6. Live `?go-get=1` metadata matches the expected public prefix, repository,
   and source subdirectory, including base-prefix checks for major versions.
7. Existing module tags identify the same complete module tree.
8. Existing releases have the expected tag and asset names, and every existing
   asset has exactly the verified bytes.

An existing tag may point to an earlier repository commit when its module tree
is identical. An unrelated change elsewhere in the repository does not require
moving that tag. A different module tree or asset under the same version stops
publication and requires a new package version.

A dry run performs this preflight, including live discovery and collision
checks, then stops without publishing. A missing discovery page is an error even
in a dry run.

### 18.3 Tags, releases, and assets

The immutable module tag is:

```text
bindings/<package-key>/go/v<package-version>
```

For example:

```text
bindings/common-integrations/go/v0.1.0
```

All new selected module tags are pushed atomically after preflight. Tags are
never moved or force-updated.

Each module tag has its own GitHub Release. For asset stem
`<package-key>-go-<version>`, that release contains:

- `<stem>.source.zip`.
- `<stem>.module.zip`.
- `<stem>.runtimeconditions.binding-model.yaml`.
- `<stem>.runtimeconditions.binding-release.yaml`.
- `<stem>.runtimeconditions.bindings.yaml`.
- `<stem>.runtimeconditions.file-manifest.yaml`.
- `SHA256SUMS` covering the six named artifacts.

Source archives contain the committed package tree under its repository
subdirectory prefix. Module archives contain it under the native
`<module>@v<version>/` prefix. The root extension resource remains inside the
package archives.

Releases are created as drafts, populated with verified assets, then made
public. Retries reuse identical tags and assets and upload only missing assets.
A byte mismatch or unexpected asset fails rather than replacing published data.
Publication rechecks `main` before its first remote mutation.

### 18.4 Public installation checks

After publication, fresh consumers install each module through both direct
retrieval and `https://proxy.golang.org,direct`. These checks use isolated module
caches, public checksum verification, empty private-module settings, and no
publishing tokens. They run `go get` for the released version and compile an
import that uses the generated package name without an alias.

Successful installation requires no GitHub credentials, private-module
configuration, local replacement, or source checkout. The public module tag
supplies Go installation; release ZIPs additionally provide downloadable,
checksummed artifacts.

### 18.5 Operational sequence

1. Update extension inputs or delivery configuration on `main`.
2. Let automatic generation verify and commit selected Go package trees.
3. Let the documentation build deploy the discovery pages.
4. Dispatch publication with the desired targets and `dry_run: true`.
5. Dispatch with `dry_run: false` after preflight succeeds.
6. Confirm the workflow's fresh public consumer installation checks succeed.

A failed target is corrected through its inputs and regeneration. Publication
never repairs source or rewrites an existing module version.

## 19. Consumer example

Install the published common and environment bindings:

```sh
go get runtimeconditions.io/x/rc/common@v0.1.0 runtimeconditions.io/x/rc/env@v0.1.0
```

A Go project can declare a Redis cache and environment configuration without
import aliases:

```go
package main

import (
    "runtimeconditions.io/x/rc/common"
    "runtimeconditions.io/x/rc/env"
)

func init() {
    _ = common.Cache(
        common.KeyValue{
            Engine: &[]common.KeyValueEngine{common.KeyValueEngineRedis}[0],
        },
        env.KeyValueConfiguration{
            Env: env.KeyValueConfigurationEnv{
                {Name: "REDIS_URL", Property: env.KeyValueConfigurationEnvPropertyUrl},
            },
        },
    )
}

func main() {}
```

An independently installed compatible Go profiler generates the profile from
the project root:

```sh
go-rc-profiler generate -dir . -out ./profile.yaml
```

The common CLI will expose this profiler operation as `rc profile go generate`
and its Go-default form `rc profile generate`. Both routes use the same
installed profiler and binding resources.

The resulting profile identifies the complete extension URIs and includes the
cache interface and configuration. Generated declarations do not require the
application to execute in order to extract this information.

## 20. Safety, determinism, and delivery acceptance

YAML parsing rejects duplicate keys, non-string mapping keys, custom tags, and
resource-limit violations. Inputs are bounded to 64 MiB, 1,000,000 decoded nodes,
256 nesting levels, and 100 alias references. Normalized outputs contain no
aliases or presentation-dependent identity.

HTTPS resolution uses certificate validation, a 10-second connection timeout,
a 60-second total timeout, bounded response data, and no redirects. Downloads,
cache entries, package resources, and release assets are verified against the
applicable identities and digests. Credentials are not persisted in artifacts
or included in diagnostics.

Generation writes only selected generated package directories. Build jobs have
read permissions; the controlled generation commit and publication jobs receive
their required write permissions. Public consumers do not inherit publishing
credentials.

The implementation is accepted when:

1. Semantic fixtures and native emitter suites establish deterministic,
   extension-independent behavior.
2. Package verification checks schemas, native APIs, provider relationships,
   installed tool identities, archives, and regeneration equality.
3. Generation commits only complete verified target updates and fails safely
   when `main` advances.
4. Documentation deployment serves definition resources and exact Go discovery
   metadata for generated modules.
5. Publication promotes the packaged committed trees, enforces compatible
   versions, and preserves immutable module tags and release assets.
6. Fresh public Go consumers retrieve released modules and compile unaliased
   imports without private settings or local replacements.
7. The common CLI can expose the binding interface through a thin adapter while
   retaining these inputs, outputs, provenance, and failure boundaries.

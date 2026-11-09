# Extension release and compatibility contract

## Purpose

This contract governs extensions published by Runtime Conditions and the
first-party tools that produce and consume them. It does not add requirements
to the core profile specification or restrict third-party extension identifiers.

An extension release is an immutable semantic vocabulary artifact. Its Runtime Conditions `apiVersion` identifies the document schema understood by validators; it does not identify the extension's semantic release.

The canonical identity rules below are the agreed target for an incremental
tooling migration. Existing definitions and released binding packages still use
artifact URLs as identifiers. Recording this contract does not migrate those
artifacts; the rollout gates below apply before new identities are published.

## Identity and versioning

- A first-party extension release MUST use a complete, explicitly versioned identifier of the form `https://runtimeconditions.io/extensions/<name>:<version>` or `https://runtimeconditions.io/extensions/<provider>/<name>:<version>`.
- The complete identifier MUST appear unchanged in the definition's `metadata.id`, profile extension declarations and selectors, dependency references, normalized model identity and ownership fields, and binding or SDK manifest identity fields.
- A generator MUST copy that identifier verbatim. It MUST NOT reconstruct it from a retrieval URL, a native package version, or a separate version annotation.
- `metadata.version` is optional descriptive metadata. When present, it MUST exactly equal the version in the canonical identifier. Tools MUST NOT append it to `metadata.id`.
- A published extension identifier MUST resolve permanently to the same semantic definition.
- A semantic change MUST produce a new extension identifier. Existing identifiers are never repointed or overwritten.
- Provider extensions SHOULD use a Semantic Versioning 2.0.0 release. Existing labels such as `v1alpha1` remain valid first-party release versions.
- An additive vocabulary or validation change increments the minor version, a meaning-changing removal or incompatible reclassification increments the major version, and a correction that does not change accepted vocabulary or profile meaning increments the patch version.
- During pre-adoption development, `0.x.y` releases may introduce incompatible conventions through new identifiers and package versions. Published identifiers, tags, and assets remain immutable.

Canonical reference examples:

```yaml
extensions:
  - https://runtimeconditions.io/extensions/common-integrations:v1alpha1
  - https://runtimeconditions.io/extensions/env-configuration:v1alpha1
  - https://runtimeconditions.io/extensions/aws/s3:0.2.0
```

A definition for the first reference declares:

```yaml
metadata:
  id: https://runtimeconditions.io/extensions/common-integrations:v1alpha1
  version: v1alpha1
```

The `version` annotation may be omitted when authoring a release; `metadata.id`
still supplies its complete identity. Optionality does not permit changing an
already published definition. Native binding package versions and the Runtime
Conditions document `apiVersion` are versioned independently.

## Authoritative provenance

Generated provider extensions record the authoritative model repository, the exact commit that last changed the selected service model, the model path, the model SHA-256 digest, the Smithy service shape, and the service version. Unrelated commits elsewhere in an upstream model repository do not create extension releases.

The upstream model revision is provenance, not the extension version. Many model revisions may produce no Runtime Conditions semantic change, while one extension release may support many SDK languages and versions.

## One extension to many SDK mappings

The dependency is directional: an SDK mapping names the exact extension release it targets, while the extension does not enumerate every language or SDK version that consumes it. A mapping records its owning distribution version, mapping-contract version, target extension identifier, target extension semantic digest, and authoritative service-mapping digest.

An SDK mapping can use a subset of operations defined by its target extension. This allows an immutable additive extension release to support SDKs that have not yet exposed every authoritative API operation. An SDK operation absent from the selected extension, after applying reviewed SDK compatibility aliases, is an extension-alignment review event.

Ordinary package dependency resolution selects compatible SDK packages. Each installed package supplies metadata for the behavior it owns, and recursive mapping validation verifies the selected graph. No handwritten Cartesian compatibility matrix is maintained.

## Maintenance classifications

- `automatic`: the authoritative model or fallback inventory, reviewed Service Operations Semantic Bridge, generated extension, service mapping, SDK surfaces, and package proof remain aligned.
- `extension-review-required`: authoritative API semantics cannot be represented safely by the selected extension release.
- `sdk-review-required`: the extension remains sufficient, but a language-specific SDK surface, wrapper, dependency, or package integration changed.
- `invalid`: the automation failed or received unsupported input before semantic ownership could be classified safely.

Extension and SDK review events are measured separately so extension-author burden is not attributed to SDK maintainers and automation defects are not attributed to either group.

## Human review surface

Humans review semantic bridge changes, added or removed operations, resource classifications, identity paths, roles, cross-service dependencies, representative profile changes, and adapter-facing impact. Generated extension YAML, language-neutral mappings, and language-specific SDK mappings are machine output and are not line-by-line review surfaces.

## HTTPS catalog lookup

The canonical identifier and the artifact retrieval URL are separate values.
A first-party catalog or configured resolver maps the complete identifier to
the location of its definition. The `rc` namespace used for providerless entries
inside this repository is not inserted into their canonical identifiers.

Resolvers MUST preserve the requested identifier for equality, dependency
deduplication, cache identity, cycle detection, and returned catalog keys. A
retrieval mapping MUST NOT replace that identifier with the artifact URL. The
retrieved first-party definition's `metadata.id` MUST match the requested
identifier exactly. Missing mappings, unavailable artifacts, identity mismatches,
and inconsistent version annotations MUST fail resolution.

The familiar artifact layout is
`https://runtimeconditions.io/extensions/<name>/<version>/runtimeconditions.extension.yaml`
or
`https://runtimeconditions.io/extensions/<provider>/<name>/<version>/runtimeconditions.extension.yaml`.
An existing URL that already identifies a published legacy definition MUST NOT
be overwritten with a definition declaring the new canonical identifier. The
migration must allocate a separate retrieval location in that case and record
its mapping explicitly.

Support for other retrieval backends remains an implementation capability. This
first-party identity convention does not impose a path rewrite on third-party
identifiers.

## Incremental migration gates

Each implementation increment must identify its files and validation before
editing. Consumer support must precede changes to published definition identities.

1. **Record the tooling contract.** Establish the complete canonical identifier,
   optional version annotation, retrieval mapping, and legacy-artifact rules in
   this document. This step changes documentation only.
2. **Prepare consumers with synthetic fixtures.** Audit the shared resolver,
   binding normalizer and emitters, site publishing, and language profilers.
   Verify that canonical identifiers survive resolution, ownership checks, and
   profile generation unchanged, including when a version annotation is present
   or absent. Existing released URL identifiers must continue to work. Keep
   cross-repository compatibility checks outside the shared binding-tooling suite.
3. **Migrate the common/env dependency pair.** Select retrieval locations that
   preserve published legacy artifacts. Update the definitions, dependency edge,
   catalog entries, generated metadata, and native package versions in bounded
   increments. Regenerate bindings through the tooling; do not hand-edit generated
   identities or digests. Verify installed consumers before publication.
4. **Update the CLI integration.** After compatible profiler and binding releases
   are available, update the required dependency pins and fixtures. Require the
   installed CLI to emit the canonical references exactly, while retaining
   coverage for workloads using the previous binding releases.
5. **Expand one dependency group at a time.** Apply the same checks to remaining
   extensions, SDK mappings, language bindings, profilers, demos, and adapters.
   Each group must resolve, generate, and validate before the next group moves.

For each migrated group, record the previous and canonical identifiers, retrieval
locations, affected dependency edges, artifact digests, package versions, and
consumer release requirements. A new definition identity changes its semantic
digest even when its vocabulary is unchanged; dependent models and bindings must
be regenerated. Publication continues through the existing release verification
and dry-run process.

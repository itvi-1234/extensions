# Runtime Conditions Extensions

Runtime Conditions is currently seeking adoption by an established parent project. The repositories in this organization are split for hands-on usability, review, demos, and implementation feedback. They are not intended to present Runtime Conditions as a standalone foundation or competing project.

Start here: https://runtimeconditions.github.io/

## Purpose

This repository contains Runtime Conditions extension definitions, declaration packages, semantic overlays, and extension-maintenance automation. Extension definitions own vocabulary and validation. Language declaration packages provide no-op source declarations that generators can read.

Extension release identity, immutability, provenance, and SDK compatibility are defined in [`EXTENSION_RELEASES.md`](EXTENSION_RELEASES.md).

Operation-oriented extensions use the authoring contract in [`SERVICE_OPERATIONS_SEMANTIC_BRIDGES.md`](SERVICE_OPERATIONS_SEMANTIC_BRIDGES.md). A semantic bridge references an authoritative Smithy, OpenAPI, protobuf, or comparable source when available and uses a separate Service Operations Inventory only as a fallback.

## Contents

- `vocabularies/` contains core, non-provider-specific vocabulary.
  - `common-integrations/` common API, datastore, and cache vocabulary plus Go, Java, and Python declaration packages.
  - `env-configuration/` workload configuration input vocabulary plus Go, Java, and Python declaration packages.
  - `source-control/` experimental Git provider and repository-operation vocabulary for development and CI workloads.
- `providers/` contains provider/service extension candidates, namespaced by vendor.
  - `aws/s3/` the Amazon S3 extension candidate, Smithy-referenced semantic bridge, generated semantic release, Python SDK mappings, and historical maintenance evidence.
  - `kubernetes/api/` the authoritative OpenAPI projection, accepted local Kubernetes API extension release, language-neutral service mapping, and maintenance inputs used by official client mappings.
  - `nats/service/` the NATS service extension candidate.
  - `google/analytics/` an experimental browser-side Google Analytics requirement and validation schema.
- `tooling/` contains automation shared across extensions, not extensions themselves.
  - `common/` the shared Python helpers (e.g. `serialization.py`) every extension's `tools/` imports from, so a fix only has to happen in one place.
  - `smithy-runtime-conditions/` the external compiler used to prove semantic-bridge generation against AWS's public Smithy models before proposing an internal AWS generator integration.

## Local validation

From a sibling `go-rc-profiler` checkout:

```sh
cd ../go-rc-profiler
go run . validate-extensions -root ../extensions
```

Published extension identifiers are immutable semantic releases. A new semantic definition receives a new exact identifier; Runtime Conditions document `apiVersion` changes are independent.

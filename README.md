# Runtime Conditions Extensions

Runtime Conditions is currently seeking adoption by an established parent project. The repositories in this organization are split for hands-on usability, review, demos, and implementation feedback. They are not intended to present Runtime Conditions as a standalone foundation or competing project.

Start here: https://runtimeconditions.github.io/

## Purpose

This repository contains Runtime Conditions extension definitions, declaration packages, semantic overlays, and extension-maintenance automation. Extension definitions own vocabulary and validation. Language declaration packages provide no-op source declarations that generators can read.

Extension release identity, immutability, provenance, and SDK compatibility are defined in [`EXTENSION_RELEASES.md`](EXTENSION_RELEASES.md).

Operation-oriented extensions use the authoring contract in [`SERVICE_OPERATIONS_SEMANTIC_BRIDGES.md`](SERVICE_OPERATIONS_SEMANTIC_BRIDGES.md). A semantic bridge references an authoritative Smithy, OpenAPI, protobuf, or comparable source when available and uses a separate Service Operations Inventory only as a fallback.

## Extensions

Per the [spec](https://github.com/runtimeconditions/spec/blob/main/docs/sixth-draft.md#5-extensions), first-party extensions are extensions like any other - there's no separate "core vocabulary" tier. Every extension in this repo, regardless of which folder it lives in, is declared and resolved the same way. This table is the single list of all of them:

| Extension | Identifier | Path |
| --- | --- | --- |
| Common Integrations | `https://runtimeconditions.io/extensions/common-integrations/v1alpha1/runtimeconditions.extension.yaml` | [`vocabularies/common-integrations/`](vocabularies/common-integrations/) |
| Env Configuration | `https://runtimeconditions.io/extensions/env-configuration/v1alpha1/runtimeconditions.extension.yaml` | [`vocabularies/env-configuration/`](vocabularies/env-configuration/) |
| Source Control | `https://runtimeconditions.io/extensions/source-control/0.1.0/runtimeconditions.extension.yaml` | [`vocabularies/source-control/`](vocabularies/source-control/) |
| Amazon S3 | `https://runtimeconditions.io/extensions/aws-s3/0.1.0/runtimeconditions.extension.yaml` | [`providers/aws/s3/`](providers/aws/s3/) |
| Kubernetes API | `https://runtimeconditions.io/extensions/kubernetes-api/0.1.0/runtimeconditions.extension.yaml` | [`providers/kubernetes/`](providers/kubernetes/) |
| NATS | `https://runtimeconditions.io/extensions/nats-service/0.1.0/runtimeconditions.extension.yaml` | [`providers/nats/`](providers/nats/) |
| Google Analytics | `https://runtimeconditions.io/extensions/google-analytics/0.1.0/runtimeconditions.extension.yaml` | [`providers/google/analytics/`](providers/google/analytics/) |

## Folder layout

The folders below exist for maintainer convenience only - to keep the repo browsable as the number of extensions grows - not because the spec distinguishes between them:

- `vocabularies/` - extensions that aren't tied to one external vendor or open-source project. `common-integrations/`, `env-configuration/`, and `source-control/` live here because they're broadly applicable rather than because they're more "core" than anything else.
- `providers/` - extensions tied to a specific external vendor or open-source project. Two shapes are both valid here:
  - `<vendor>/<service>/` when a vendor is expected to have more than one extension over time, e.g. `aws/s3/`, and later `aws/dynamodb/`, `google/analytics/`. This keeps a growing vendor's extensions grouped instead of cluttering the repo root.
  - `<project>/` flat, with no extra service-level folder, when the project only makes sense as a single extension, e.g. `kubernetes/` and `nats/`. Kubernetes and NATS aren't vendors selling multiple services - forcing a `kubernetes/api/`-style nesting for a folder that will only ever have one entry is unnecessary ceremony. Tooling that walks `providers/` should expect both shapes: a vendor directory containing one or more service directories, or a project directory that is itself the only extension.
- `tooling/` - automation shared across extensions, not extensions themselves.
  - `common/` the shared Python helpers (e.g. `serialization.py`) every extension's `tools/` imports from, so a fix only has to happen in one place.
  - `smithy-runtime-conditions/` the external compiler used to prove semantic-bridge generation against AWS's public Smithy models before proposing an internal AWS generator integration.

## Local validation

From a sibling `go-rc-profiler` checkout:

```sh
cd ../go-rc-profiler
go run . validate-extensions -root ../extensions
```

Published extension identifiers are immutable semantic releases. A new semantic definition receives a new exact identifier; Runtime Conditions document `apiVersion` changes are independent.

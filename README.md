# Runtime Conditions Extensions

Runtime Conditions is currently seeking adoption by an established parent project. The repositories in this organization are split for hands-on usability, review, demos, and implementation feedback. They are not intended to present Runtime Conditions as a standalone foundation or competing project.

Start here: https://runtimeconditions.github.io/

## Purpose

This repository contains Runtime Conditions extension definitions, declaration packages, semantic overlays, and extension-maintenance automation. Extension definitions own vocabulary and validation. Language declaration packages provide no-op source declarations that generators can read.

Extension release identity, immutability, provenance, and SDK compatibility are defined in [`EXTENSION_RELEASES.md`](EXTENSION_RELEASES.md).

## Contents

- `common-integrations/` contains common API, datastore, and cache vocabulary plus Go, Java, and Python declaration packages.
- `env-configuration/` contains workload configuration input vocabulary plus Go, Java, and Python declaration packages.
- `aws-s3/` contains the Amazon S3 extension candidate, authoritative Smithy overlay, generated semantic release, Python SDK mappings, and historical maintenance evidence.
- `smithy-runtime-conditions/` contains reusable Runtime Conditions Smithy traits and the external compiler used to prove the workflow against AWS's public models before proposing an internal AWS generator integration.

## Local validation

From a sibling `go-rc-profiler` checkout:

```sh
cd ../go-rc-profiler
go run . validate-extensions -root ../extensions
```

Published extension identifiers are immutable semantic releases. A new semantic definition receives a new exact identifier; Runtime Conditions document `apiVersion` changes are independent.

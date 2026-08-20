# Runtime Conditions Extensions

Runtime Conditions is currently seeking adoption by an established parent
project. The repositories in this organization are split for hands-on usability,
review, demos, and implementation feedback. They are not intended to present
Runtime Conditions as a standalone foundation or competing project.

Start here: https://runtimeconditions.github.io/

## Purpose

This repository contains first-party Runtime Conditions extension definitions
and declaration packages. Extension definitions own vocabulary and validation.
Language declaration packages provide no-op source declarations that generators
can read.

## Contents

- `common-integrations/` - common API, datastore, and cache vocabulary, plus
  Go, Java, and Python declaration packages.
- `env-configuration/` - workload configuration input vocabulary, plus Go,
  Java, and Python declaration packages.
- `aws-s3/` - design-checkpoint extension candidate for Amazon S3 resource and
  service demand. It is not yet a published or authoritative AWS extension.

## Local Validation

From a sibling `go-rc-profiler` checkout:

```sh
cd ../go-rc-profiler
go run . validate-extensions -root ../extensions
```

The extension IDs under `https://runtimeconditions.io/extensions/...` are kept
stable while packaging and distribution options are evaluated.

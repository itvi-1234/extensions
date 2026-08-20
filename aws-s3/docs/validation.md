# Validation record

## Extension definition

The AWS S3 candidate passed targeted extension validation with the locally
cloned Go tooling. Its embedded JSON Schemas were also checked independently,
including expected rejection cases. No profiler was changed.

The current Go validator still does not generically apply every extension's
arbitrary Condition schema, and the current Python profiler does not consume
SDK package mappings. Those are profiler capability decisions outside this
authorship proof.

## Language-neutral service mapping

The service generator validates the pinned botocore S3 model before emitting
metadata:

```text
service id: S3
API version: 2006-03-01
canonical operations: 116
Condition templates: 123
```

The accepted operation count and SHA-256 fingerprint make operation-set drift
a review event. Input identity paths are walked through the service shapes, so
a stale nested bucket path fails generation.

Every modeled S3 operation is represented: 112 primary bucket operations,
three service-level operations, and one Object Lambda response operation. Seven
additional templates describe secondary S3 buckets nested in request inputs.

## Owner-aligned mapping validation

[`../tools/validate_owner_mappings.py`](../tools/validate_owner_mappings.py)
loads all three generated mappings as static JSON and checks:

- unique distribution/mapping identities;
- every declared mapping dependency exists;
- every `operationRef`, `waiterRef`, and `callRef` resolves to the declared
  owner and member;
- cross-mapping references are declared dependencies;
- botocore client methods exactly cover canonical operations;
- waiter and paginator operations exist;
- extension Condition templates retain their canonical operation;
- recursive dependencies contain no cycle.

Result:

```text
recursive SDK mapping validation passed
dependency order:
  botocore: botocore.aws.s3
  s3transfer: s3transfer.aws.s3
  boto3: boto3.aws.s3
```

## Pinned SDK source validation

[`../tools/validate_sdk_sources.py`](../tools/validate_sdk_sources.py) reads the
official tagged source trees without importing or executing the SDK packages.
It checks exact distribution versions, the complete operation and resource
inventories, generated Python spellings, factory and wrapper signatures,
positional/keyword bindings, handwritten load delegates, s3transfer public
entrypoints, and the service operations actually used by the transfer
implementation modules.

Result:

```text
pinned SDK source validation passed
  botocore operations: 116
  boto3 handwritten wrapper surfaces: 17
  boto3 modeled resources: 18
  s3transfer public entrypoints: 9
  s3transfer distinct canonical operations: 19
```

The gate caught an off-by-one `extra_args` binding in the initial
`S3Transfer.download_file` annotation. The corrected overlay now passes and a
future signature change will fail in the same focused way.

## Installed artifact proof

Official boto3 1.43.70, botocore 1.43.70, and s3transfer 0.19.2 source checkouts
were rebuilt with their owner mapping and index. All three wheels were installed
from local paths; no registry was used.

[`../../../sdk/authorship/aws-python/tools/discover_mappings.py`](../../../sdk/authorship/aws-python/tools/discover_mappings.py)
used only Python distribution metadata and JSON reads. It verified index and
mapping digests, required each mapping version to equal its installed owner,
loaded recursive dependencies, and revalidated all references. It reported
that boto3, botocore, and s3transfer were not imported.

`pip check` reported no broken dependencies. All six original S3 application
tests passed unchanged against the rebuilt packages, and the added
managed-transfer application passed through the real boto3-to-s3transfer
small-file path. The complete evidence and package
measurements are in
[`../../../sdk/authorship/aws-python/results/2026-08-14-owner-aligned-packaging-rehearsal.md`](../../../sdk/authorship/aws-python/results/2026-08-14-owner-aligned-packaging-rehearsal.md).

The post-install runtime surface test also checked 116 client methods, eight
paginators, four waiters, 19 resource classes, and 148 resource members. Six
s3transfer entrypoints were runtime-checked; the three CRT entrypoints remained
source-validated because the optional `awscrt` extra was not installed.

## Representative nested resolution

The static resolver proves these chains:

- direct `put_object` → botocore `PutObject` → `aws.s3` bucket Condition;
- `Bucket.put_object` → botocore `PutObject` → the same Condition shape;
- `Bucket.wait_until_exists` → botocore `bucket_exists` → `HeadBucket` →
  Condition;
- `Bucket.upload_file` → s3transfer managed upload → classic/CRT execution
  path → botocore operations → Conditions.

The multipart branches remain separate. The metadata does not claim that both
single-part and multipart operations occur, and it does not turn branch
ambiguity into a mapping-layer coverage or unresolved field.

## Remaining limitations

- The candidate reference and execution-path vocabulary is not yet an accepted
  cross-language specification.
- Source validation currently contains S3-specific checks for s3transfer's
  implementation modules. Generalizing that check belongs in the postponed
  all-services generator workflow.
- The application corpus contains the public boto3 managed-upload path but not
  direct s3transfer calls, multipart/CRT execution, waiter, paginator, or every
  resource-relation pattern. The mapping artifacts and static resolver cover
  those surfaces, but profiler acceptance fixtures should be expanded before
  profiler implementation.

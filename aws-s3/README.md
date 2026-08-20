# AWS S3 Extension Candidate

## Status

**Design checkpoint — not yet a published or authoritative AWS extension.**

This directory contains a reviewable Runtime Conditions extension candidate for
the Amazon S3 API. It replaces the assumptions in the older
`spec/examples/extensions/aws-object-store` example for this investigation; it
does not modify or endorse that example.

The candidate is deliberately AWS-specific. A downstream adapter can decide
that a compatible implementation satisfies the contract, but the extension
does not generalize or rename the S3 interface for another provider.

## Condition shape

The extension owns one vendor-specific integration kind and three S3 resource
surfaces:

```yaml
kind: aws.s3
interface:
  type: bucket
  operations:
    - name: PutObject
```

This says that the workload needs an S3 bucket and invokes the canonical S3
`PutObject` operation against it. It does not name the bucket, select an AWS
account or Region, prescribe credentials, or declare environment-variable
names.

```yaml
kind: aws.s3
interface:
  type: service
  operations:
    - name: CreateBucket
```

This says that the workload needs service-level S3 access. It does not claim
that a bucket already exists. `ListBuckets` and `ListDirectoryBuckets` have the
same interface type.

```yaml
kind: aws.s3
interface:
  type: object_lambda
  operations:
    - name: WriteGetObjectResponse
```

This represents the S3 Object Lambda invocation context required by
`WriteGetObjectResponse`, which is neither an ordinary bucket identifier nor
account-wide S3 access.

The operation entries identify canonical S3 API operations invoked by the
workload. They are not authorization declarations. Some operation names happen
to match IAM action suffixes, but the relationship is not one-to-one. An AWS
adapter may translate each operation and any proven request features into IAM
actions.

## Why canonical operations are the selected minimum

The alternatives considered were:

| Representation | Benefit | Why it is not sufficient as the minimum |
| --- | --- | --- |
| Broad capabilities such as `read`, `write`, `list`, `admin` | Small, approachable vocabulary | Loses distinctions needed for least-privilege fulfillment and requires a second hand-maintained taxonomy |
| IAM actions | Direct input to one AWS policy system | One API operation can require several conditional actions, and several operations map to differently named actions |
| HTTP methods and routes | Mechanically available from the service model | Does not express S3 semantics and is complicated by S3 endpoint and addressing variants |
| Desired features such as versioning or encryption | Describes resource state directly | Calling a read or update operation does not necessarily prove that the workload requires the feature to be preconfigured |
| Resource type without operations | Very simple adopter output | Says that a bucket exists but not what the workload must be able to do with it |

Canonical operation names preserve exactly what the SDK call proves and let an
adapter apply current AWS fulfillment knowledge. Each operation is an object
rather than a bare string so source/destination roles and future operation-level
requirements can be added without replacing the profile shape.

## Full service-operation mapping

The generated service and owner-aligned SDK mappings cover every operation in
the botocore 1.43.70 S3 model:

- 116 canonical low-level client operations;
- 123 S3 Condition templates, including seven secondary S3 bucket references;
- eight botocore paginators and four botocore waiters;
- boto3's 18 modeled resources, 71 resource actions, 37 relations, four
  collections, and six resource waiters;
- 17 handwritten boto3 managed-transfer wrapper surfaces;
- nine public s3transfer entrypoints over four logical transfer calls, with
  explicit classic, CRT, multipart-success, and multipart-abort paths.

`PutObject` is still the first end-to-end profiler acceptance case, but it is no
longer the limit of the mapping artifacts. See:

- [`model/generated/s3-service-mapping.json`](model/generated/s3-service-mapping.json)
  for the complete language-neutral mapping;
- [`mappings/botocore/runtimeconditions.sdk-mapping.json`](mappings/botocore/runtimeconditions.sdk-mapping.json)
  for the low-level client operation owner;
- [`mappings/s3transfer/runtimeconditions.sdk-mapping.json`](mappings/s3transfer/runtimeconditions.sdk-mapping.json)
  for managed-transfer behavior;
- [`mappings/boto3/runtimeconditions.sdk-mapping.json`](mappings/boto3/runtimeconditions.sdk-mapping.json)
  for boto3 factories, resource behavior, and handwritten wrappers;
- [`model/semantic-annotations.json`](model/semantic-annotations.json) for the
  reviewed service semantic layer;
- [`model/boto3-wrapper-annotations.json`](model/boto3-wrapper-annotations.json)
  and [`model/s3transfer-semantic-annotations.json`](model/s3transfer-semantic-annotations.json)
  for the reviewed handwritten layers.

Complete S3 operation coverage does not mean that every possible dependency
nested in every request is already expressible. Some request shapes can refer
to KMS keys, IAM roles, SNS topics, SQS queues, Lambda functions, or S3 Tables.
Those mappings must align with their own extensions. The S3 mapping does not
invent that missing vocabulary.

## Authentication and workload configuration

The S3 extension does not currently depend on the Environment Configuration
extension. AWS SDKs support explicit client settings, environment variables,
shared files, workload identity, instance/container providers, and other
credential mechanisms with defined precedence. An SDK call alone does not prove
that any particular environment variable is a workload requirement.

Optional environment-variable settings remain a possible additive extension,
but adding every supported AWS variable to every S3 Condition would create
noise and could incorrectly tell a platform to wire inputs the application does
not use. The deeper analysis is in [`docs/design.md`](docs/design.md).

## Files

- [`aws-s3-v1alpha1.yaml`](aws-s3-v1alpha1.yaml) is the machine-readable
  extension candidate.
- [`docs/api-analysis.md`](docs/api-analysis.md) records the S3 API inventory
  and resource-boundary findings.
- [`docs/design.md`](docs/design.md) explains the Condition shape, alternatives,
  configuration boundary, and deferred cross-service dependencies.
- [`docs/sdk-author-workflow.md`](docs/sdk-author-workflow.md) states exactly
  what an SDK maintainer would add and maintain.
- [`docs/validation.md`](docs/validation.md) records the performed checks and
  profiler limitations.
- [`examples/put-object-profile.yaml`](examples/put-object-profile.yaml) is the
  expected output for the first boto3 end-to-end acceptance test.

## Decisions at this checkpoint

- Accepted: `kind: aws.s3` identifies the AWS S3 integration.
- Accepted: `interface.type` distinguishes `bucket`, `service`, and
  `object_lambda` demand.
- Recommended: keep those resource surfaces separate; `CreateBucket` must not
  imply that a pre-existing bucket should be provisioned.
- Recommended: use canonical operation objects as the minimum adapter-facing
  detail.
- Deferred: add configuration only when application source or a separate
  additive extension proves a workload-facing input mechanism.
- Implemented in static metadata: the entire canonical S3 operation list and
  the recursively owned boto3/botocore/s3transfer dependency graph.

No SDK or profiler should treat the candidate format as stable until the
remaining recommendations have been reviewed.

# AWS S3 extension design checkpoint

## Design priority

The candidate is evaluated in this order:

1. An application using a mapped SDK should generate an understandable profile
   without changing its source.
2. The Condition must say enough for an adapter to make a useful fulfillment
   decision without claiming facts the source did not prove.
3. SDK maintainers should provide one service-level semantic input that can
   generate language-specific static metadata, not hand-maintain mappings for
   every language.
4. Manual declarations must remain possible and typed, but they are the
   fallback when the SDK mapping cannot supply the requirement.

## Layer responsibilities

| Layer | Owns | Does not own |
| --- | --- | --- |
| AWS S3 extension | S3 kind, resource-facing interface types, valid operation vocabulary, validation | boto3 symbols, detection policy, credentials, provisioning |
| Service mapping | Relationship from canonical S3 operations and inputs to extension-owned vocabulary | New Condition vocabulary, coverage reporting, adapter policy |
| Language SDK mapping | SDK construction patterns, language symbol names, wrapper aliases | Independent S3 semantics |
| Language profiler | Static discovery and profile generation | AWS semantics not supplied by mappings |
| Adapter | S3 fulfillment, policy translation, platform wiring | Reinterpreting invalid or unresolved vocabulary |

The extension must exist before an SDK mapping can be conforming because the
mapping is only allowed to emit vocabulary owned and validated by a resolved
extension.

## Candidate Condition shape

`kind` identifies the AWS S3 integration family. `interface.type` identifies
which S3 resource-facing surface the workload requires.

### Existing bucket demand

```yaml
kind: aws.s3
interface:
  type: bucket
  operations:
    - name: PutObject
```

- One Condition represents one distinguishable S3 bucket requirement.
- `operations[].name` contains canonical S3 API operations invoked against that
  bucket.
- The Condition does not carry the concrete runtime bucket name.

### Service-level demand

```yaml
kind: aws.s3
interface:
  type: service
  operations:
    - name: CreateBucket
```

This avoids claiming that an existing bucket should be provisioned for code
whose job is to create buckets. It also covers account-wide listing operations
without manufacturing a bucket Condition.

### Object Lambda response demand

```yaml
kind: aws.s3
interface:
  type: object_lambda
  operations:
    - name: WriteGetObjectResponse
```

`WriteGetObjectResponse` operates against request route/token context supplied
to an Object Lambda function. A separate interface type preserves the actual
runtime contract instead of treating that context as an ordinary bucket.

## Operation representation

Canonical S3 operation objects are the selected minimum:

```yaml
operations:
  - name: CopyObject
    role: source
```

The canonical name is the fact most directly proved by the SDK call. The
optional `role` distinguishes the source and destination bucket Conditions for
copy operations. The object shape leaves room for request features that later
prove necessary without changing `operations` from a string array to an object
array.

### Alternative: broad access capabilities

Values such as `read`, `write`, `list`, and `admin` would be easy to read, but
they create a new taxonomy that SDK or extension authors must maintain. They
also collapse materially different operations and make least-privilege
translation less reliable. They may be useful as adapter-derived summaries,
but they are not sufficient source facts.

### Alternative: IAM policy actions

IAM actions are fulfillment instructions, not a one-to-one description of SDK
behavior. For example, `HeadBucket` requires `s3:ListBucket`, while
`CompleteMultipartUpload` requires `s3:PutObject`. `PutObject` always requires
`s3:PutObject` and can require additional S3 or KMS actions depending on request
features. Recording API operations lets the adapter perform that translation
without confusing the two contracts.

### Alternative: HTTP routes

HTTP methods and request URIs are mechanically available, but S3 endpoint
variants, virtual hosting, access points, and request headers carry essential
semantics. A raw `PUT` route is both harder for adopters to read and less useful
to an adapter than `PutObject`.

### Alternative: desired resource features

Features such as versioning, lifecycle, encryption, or replication may become
useful extension fields. They do not replace operation names: calling
`GetBucketVersioning` does not prove that versioning must be enabled, and
calling `PutBucketVersioning` does not statically prove which state a dynamic
request selects. Add a feature only when source analysis proves the desired
state and an adapter can act on it.

## Authentication and configuration

### Why fixed environment variables remain absent

Creating an AWS SDK client does not prove `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, or any particular bucket variable. AWS
SDKs support explicit settings, JVM properties in relevant languages,
environment variables, shared files, web identity, container and instance
providers, and other credential sources with precedence rules.

Declaring every supported variable as optional would still have costs:

- application developers would see inputs their application may never read;
- adapters could interpret the list as wiring work they should perform;
- every S3 Condition would repeat configuration that actually belongs to a
  shared AWS SDK client or execution identity;
- static credentials would appear to be a normal portability mechanism despite
  workload identity commonly being preferable.

The current decision is therefore not “AWS settings can never be represented.”
It is “an S3 operation mapping does not prove a settings delivery mechanism.”

### Viable additive path

A later AWS SDK Configuration extension can describe source-proven SDK settings
and identity requirements at the client level. A separate application
declaration can describe a workload-specific input such as `UPLOAD_BUCKET` when
the application expects the platform to supply it. Both can compose with the
S3 Condition without making configuration mandatory for ordinary SDK mapping.

The current Environment Configuration extension cannot simply be referenced as
written because its `configuration` field is scoped to the common `api`,
`datastore`, and `cache` kinds. Adding S3 support requires an intentional
additive scope and validation design; copying its shape into this extension
would duplicate vocabulary ownership.

## Complete S3 operation mapping versus complete request semantics

The generated mapping contains all 116 canonical operations. Every operation
emits at least one S3 Condition template:

- 112 operations primarily target an existing bucket;
- `CreateBucket`, `ListBuckets`, and `ListDirectoryBuckets` require the service
  surface;
- `WriteGetObjectResponse` requires the Object Lambda surface.

Seven additional templates model S3 buckets referenced by copy, analytics,
inventory, logging, replication, and restore requests. They are conditional on
the referenced input being present and statically identifiable.

Some S3 request shapes also reference KMS, IAM, SNS, SQS, Lambda, or S3 Tables
resources. Those are real potential runtime dependencies, but an S3 extension
cannot own their vocabulary. Complete cross-service request semantics therefore
depends on those extensions existing and on the source making the nested value
statically identifiable.

This distinction prevents the phrase “complete S3 mapping” from becoming a
claim that every dynamic request value and every other AWS service has already
been inferred.

## Condition identity and aggregation

The extension validates one Condition; the mapping tells a profiler where a
resource identity originates; the profiler decides static grouping.

- Two configured clients should not automatically collapse into one Condition.
- One client can address more than one bucket.
- Several calls against the same statically identifiable bucket can share a
  Condition whose operation list is the union of those calls.
- A dynamic bucket expression may prevent reliable grouping.
- Concrete bucket names or ARNs remain outside the emitted portable profile.

The generated mapping's `identity` paths are analysis instructions and never
profile fields.

## Acceptance criteria

1. Every operation in the pinned S3 model appears exactly once in the
   language-neutral operation inventory.
2. Every low-level boto3 S3 client method maps to its canonical operation.
3. The boto3 resource aliases in the published resource model map to canonical
   operations without duplicating S3 semantics.
4. The unmodified direct-client fixture generates one `aws.s3` / `bucket`
   Condition containing `{name: PutObject}` after SDK extraction is implemented.
5. Generated profiles contain no invented environment variables, credentials,
   Region, endpoint, concrete bucket value, coverage field, or unresolved
   observation.
6. Invalid operation names or roles fail extension semantic validation.
7. A service-model operation-set change stops generation until a maintainer
   reviews and accepts the new fingerprint.
8. No Runtime Conditions runtime dependency is added to boto3 or applications.

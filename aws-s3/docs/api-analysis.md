# Amazon S3 API analysis

## Purpose and source material

This analysis asks one question: what Runtime Condition can an S3 SDK operation
truthfully imply before any language-specific mapping is written?

The executable corpus currently pins boto3 and botocore 1.43.70. The canonical
model inspected for this checkpoint is the following resource inside the
resolved botocore distribution:

```text
botocore/data/s3/2006-03-01/service-2.json.gz
```

That model identifies the service as S3, API version `2006-03-01`, using the
`rest-xml` protocol, and contains 116 operations. The operation set was checked
against the current AWS [Amazon S3 API operation index][s3-operations].

This is the S3 data-plane and bucket-control API model. It is not the separate
S3 Control service model.

## Mechanical inventory

The first pass grouped operations by members of their modeled input shape. This
is useful inventory, not sufficient semantic classification.

| Input surface | Count | Examples |
| --- | ---: | --- |
| `Bucket`, `Key`, and `UploadId` | 5 | `UploadPart`, `CompleteMultipartUpload` |
| `Bucket` and `Key` | 25 | `PutObject`, `GetObject`, `CopyObject` |
| `Bucket` without `Key` | 83 | `HeadBucket`, `ListObjectsV2`, `CreateBucket` |
| No `Bucket` member | 3 | `ListBuckets`, `ListDirectoryBuckets`, `WriteGetObjectResponse` |
| **Total** | **116** | |

All 116 operation names are represented by the three scoped operation enums in
[`../aws-s3-v1alpha1.yaml`](../aws-s3-v1alpha1.yaml).

## Semantic classification

The `Bucket` parameter alone does not tell us that an existing bucket is the
runtime dependency. `CreateBucket` accepts a bucket name, but the bucket does
not exist before the call. The workload needs service-level S3 access that
allows it to create the resource. `ListBuckets` and `ListDirectoryBuckets` are
also service-scoped.

The candidate therefore classifies the modeled operations as follows:

| Runtime demand | Count | Candidate Condition |
| --- | ---: | --- |
| Existing bucket is the primary operation target | 112 | `aws.s3` / `bucket` |
| Service-level S3 access | 3 | `aws.s3` / `service` |
| Object Lambda response context | 1 | `aws.s3` / `object_lambda` |

`WriteGetObjectResponse` is not forced into the bucket or service shape. AWS
defines it as passing a transformed object back to an active `GetObject` request
made through an Object Lambda access point. Its required route and request token
are invocation context, not a normal bucket identifier. The `object_lambda`
interface type records that distinct contract. See the AWS
[`WriteGetObjectResponse` API reference][write-response].

This is an explicit vocabulary boundary. It is not a mapping coverage field,
profile diagnostic, or unresolved-observation mechanism.

## Why operation names are necessary but insufficient

For the basic case, `PutObject` proves two stable facts: the workload needs an
S3 bucket, and it invokes the canonical `PutObject` operation. AWS describes
that operation as adding an object to a bucket. The candidate records those
facts and no more.

The operation name is useful to an adapter, but it is not itself an IAM policy.
AWS documents `s3:PutObject` as always required and additional permissions for
request features such as object ACLs, object tags, and KMS encryption. Therefore
an adapter can safely derive the baseline action from `PutObject`, but tooling
must not invent the conditional actions unless the source proves the relevant
request features. See the AWS [`PutObject` permissions section][put-object].

Several other operations demonstrate why the generated mapping needs a semantic
overlay rather than a model-name conversion:

- `CopyObject` and `UploadPartCopy` have a primary destination bucket in the
  `Bucket` member and a source object encoded separately in `CopySource`. The
  complete mapping emits conditional source and destination bucket templates
  with explicit operation roles.
- Bucket configuration calls can contain references to other buckets, KMS keys,
  IAM roles, SNS topics, SQS queues, or Lambda functions. Those secondary
  resources are nested request semantics, not discoverable from the operation
  name alone.
- `PutObject` can target general-purpose buckets, directory buckets, access
  points, and other S3 endpoint forms. The SDK method alone does not prove which
  form the application requires.

Incomplete detection remains a concern for the application developer,
platform, and downstream tooling. The mapping does not publish a percentage or
an unresolved-observation list.

## Consequences for the extension and mapping architecture

1. The extension needs resource scope (`bucket`, `service`, or `object_lambda`),
   not just an `aws.s3` label.
2. Canonical API operation names are appropriate portable input to an S3-aware
   adapter; the operation entries are not authorization declarations, even when
   an operation name happens to match an IAM action suffix.
3. The SDK model can generate the operation inventory, but a small reviewed
   semantic overlay must classify resource scope and secondary dependencies.
4. The complete static mapping can cover the entire service operation list even
   though `PutObject` remains the first end-to-end profiler fixture.
5. New S3 operations must trigger review of the generated diff and acceptance
   of a new operation-set fingerprint. They must not silently enter published
   metadata solely because their input has a field named `Bucket`.

## Secondary S3 buckets

The generated mapping contains seven additional conditional bucket templates
for S3 references nested outside the primary `Bucket` input:

| Operation | Secondary bucket purpose |
| --- | --- |
| `CopyObject` | Copy source |
| `UploadPartCopy` | Copy source |
| `PutBucketAnalyticsConfiguration` | Analytics export destination |
| `PutBucketInventoryConfiguration` | Inventory destination |
| `PutBucketLogging` | Logging destination |
| `PutBucketReplication` | Replication destination |
| `RestoreObject` | Select restore output destination |

These templates are emitted only when the nested input is present and can be
statically identified. Other nested request members can reference non-S3 AWS
resources; those require their own extension vocabulary.

[s3-operations]: https://docs.aws.amazon.com/AmazonS3/latest/API/API_Operations_Amazon_Simple_Storage_Service.html
[put-object]: https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html
[write-response]: https://docs.aws.amazon.com/AmazonS3/latest/API/API_WriteGetObjectResponse.html

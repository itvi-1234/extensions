# Generated boto3-owned S3 mapping

[`runtimeconditions.sdk-mapping.json`](runtimeconditions.sdk-mapping.json) is
generated static metadata for the public S3 behavior owned by boto3 1.43.70.

It contains:

- top-level and Session client/resource factories, including positional and
  keyword service selection and the public `boto3.Session` alias;
- the complete 18-resource S3 construction graph;
- 71 modeled resource actions, 37 relations, four collections, and six resource
  waiters;
- five injected client transfer helpers, ten Bucket/Object helpers, and two
  `boto3.s3.transfer.S3Transfer` methods;
- explicit references to botocore operations/waiters and s3transfer logical
  calls.

It deliberately does not contain botocore's canonical operation definitions or
s3transfer's implementation behavior. Those are independently versioned and
owned by their respective installed distributions. See the sibling
[`botocore`](../botocore/) and [`s3transfer`](../s3transfer/) artifacts.

The generated file is not intended for line-by-line review. Maintainers review
the boto3 resource-model diff, the compact
[`../../model/boto3-wrapper-annotations.json`](../../model/boto3-wrapper-annotations.json)
overlay, automated counts/digests, and representative resolutions.

The local wheel proof, exact package integration, and maintenance workflow are
under [`../../../../sdk/authorship/aws-python`](../../../../sdk/authorship/aws-python/).
No profiler consumes this candidate yet.

# Generated botocore-owned S3 mapping

[`runtimeconditions.sdk-mapping.json`](runtimeconditions.sdk-mapping.json) is
generated static metadata for the S3 operation surface owned by botocore
1.43.70.

It contains all 116 canonical operations, their generated Python client method
spellings, eight paginator bindings, four waiter bindings, and 123 Condition
templates aligned to the AWS S3 extension.

This is the canonical operation target for boto3 resource bindings and
s3transfer execution paths. botocore owns it because botocore owns the service
model and dynamically creates low-level clients; boto3's compatible dependency
range is not the correct version authority.

The mapping is generated from botocore's service, paginator, and waiter models
plus the compact extension-semantic overlay in
[`../../model/semantic-annotations.json`](../../model/semantic-annotations.json).
Maintainers review those inputs and generated summaries, not this JSON line by
line.

# Generated s3transfer-owned S3 mapping

[`runtimeconditions.sdk-mapping.json`](runtimeconditions.sdk-mapping.json) is
static metadata for managed-transfer behavior owned by s3transfer 0.19.2.

It groups nine public entrypoints into upload, download, copy, and delete calls.
Classic and CRT implementations remain distinct, as do single-part,
multipart-success, and multipart-abort paths. Conditional multipart-copy tag
and annotation operations retain the predicates present in implementation
behavior.

Every service operation is an owner-qualified reference to the botocore S3
mapping. The artifact therefore does not duplicate extension Condition
templates or claim botocore operation ownership.

Maintainers review
[`../../model/s3transfer-semantic-annotations.json`](../../model/s3transfer-semantic-annotations.json)
and source-validation output rather than this generated file. The source gate
checks public signatures and the actual operation set in the transfer modules.

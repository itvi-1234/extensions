# S3 semantic inputs and generated owner mappings

This directory separates reviewed service and wrapper semantics from mechanical
SDK output.

## Reviewed inputs

[`semantic-annotations.json`](semantic-annotations.json) supplies the
extension meaning that cannot be safely inferred from AWS's service model:

- ordinary bucket, service-level, and Object Lambda scope;
- source/destination roles;
- secondary S3 bucket identities nested in request shapes;
- the reviewed service identity, operation count, and operation-set digest.

[`boto3-wrapper-annotations.json`](boto3-wrapper-annotations.json) describes
only public boto3 surfaces absent from its resource model: factories, aliases,
handwritten managed-transfer wrappers, and handwritten resource loads.

[`s3transfer-semantic-annotations.json`](s3transfer-semantic-annotations.json)
describes public transfer entrypoints, argument bindings, classic/CRT
implementations, mutually exclusive execution paths, and conditional service
operations.

The annotations do not contain coverage percentages or unresolved profiler
observations. Runtime branch selectors and predicates describe SDK execution
semantics; consuming tools decide how to handle application ambiguity.

## Generated outputs

[`generated/s3-service-mapping.json`](generated/s3-service-mapping.json) is
language-neutral and contains all 116 canonical operations and 123 S3
Condition templates.

The owner generator then produces three independently versioned artifacts:

- botocore owns canonical client operations, paginators, and waiters;
- s3transfer owns managed-transfer calls and their execution paths;
- boto3 owns client/resource factories, the complete resource graph, and its
  handwritten wrappers.

References across those files identify the target distribution, mapping, and
operation/waiter/call. The generated files are review output, not handwritten
inputs.

## Regeneration

Use pinned official boto3, botocore, and s3transfer source trees. From the
`runtimeconditions` workspace root, generate the language-neutral service
mapping first:

```sh
python3 extensions/aws-s3/tools/generate_mappings.py \
  --service-model /absolute/path/to/botocore-1.43.70/botocore/data/s3/2006-03-01/service-2.json \
  --annotations extensions/aws-s3/model/semantic-annotations.json \
  --service-output extensions/aws-s3/model/generated/s3-service-mapping.json
```

Then generate all owner artifacts:

```sh
python3 extensions/aws-s3/tools/generate_owner_mappings.py \
  --service-mapping extensions/aws-s3/model/generated/s3-service-mapping.json \
  --paginator-model /absolute/path/to/botocore-1.43.70/botocore/data/s3/2006-03-01/paginators-1.json \
  --waiter-model /absolute/path/to/botocore-1.43.70/botocore/data/s3/2006-03-01/waiters-2.json \
  --resource-model /absolute/path/to/boto3-1.43.70/boto3/data/s3/2006-03-01/resources-1.json \
  --boto3-wrappers extensions/aws-s3/model/boto3-wrapper-annotations.json \
  --s3transfer-annotations extensions/aws-s3/model/s3transfer-semantic-annotations.json \
  --botocore-output extensions/aws-s3/mappings/botocore/runtimeconditions.sdk-mapping.json \
  --s3transfer-output extensions/aws-s3/mappings/s3transfer/runtimeconditions.sdk-mapping.json \
  --boto3-output extensions/aws-s3/mappings/boto3/runtimeconditions.sdk-mapping.json \
  --botocore-version 1.43.70 \
  --s3transfer-version 0.19.2 \
  --boto3-version 1.43.70
```

Both generators use only the Python standard library and read SDK files as
data. Run the recursive and pinned-source validation commands documented in
[`../docs/validation.md`](../docs/validation.md) before packaging.

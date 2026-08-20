# SDK author workflow for the S3 candidate

## Goal

An SDK maintainer should maintain semantics at the layer the repository owns,
reuse existing service/resource models, and review concise generated summaries.
They should never hand-maintain the full generated mapping or duplicate a
canonical operation table in every language.

The AWS SDK for Python proof uses three owner-aligned artifacts because boto3,
botocore, and s3transfer version and publish different public behavior. The
same principle applies when one SDK repository owns all layers: references can
remain internal to one generated artifact when the version owner is genuinely
the same.

## What is human-authored

### Extension-aligned service semantics

[`../model/semantic-annotations.json`](../model/semantic-annotations.json)
contains the decisions the botocore service model cannot safely infer:

- ordinary bucket, service-level, and Object Lambda scopes;
- primary source/destination roles;
- secondary bucket references in nested request shapes;
- the reviewed service identity and operation fingerprint.

It contains canonical S3 operation names, not Python method names. The complete
116-operation language-neutral mapping is generated from this small overlay and
the service model.

### boto3 handwritten surfaces

[`../model/boto3-wrapper-annotations.json`](../model/boto3-wrapper-annotations.json)
contains only behavior absent from boto3's resource model:

- top-level and Session factory spellings, positional/keyword selectors, and
  the public `boto3.Session` alias;
- five injected client transfer helpers;
- ten injected Bucket/Object transfer helpers;
- two `boto3.s3.transfer.S3Transfer` methods;
- the two handwritten resource-load operations.

The generator obtains the 18 resources, 71 actions, 37 relations, four
collections, and six resource waiters from boto3's existing resource model.

### s3transfer behavior

[`../model/s3transfer-semantic-annotations.json`](../model/s3transfer-semantic-annotations.json)
contains nine public entrypoints grouped into four logical calls: managed
upload, download, copy, and delete. It records their argument bindings and
owner-qualified botocore operations.

Runtime branches are represented honestly. A classic upload can use a
single-part path, a successful multipart path, or a multipart cleanup path; a
CRT upload uses `PutObject`. Multipart-copy tagging and annotation calls retain
their argument and derived-data predicates. The mapping does not flatten those
paths into a claim that every operation always occurs.

Transfer configuration sometimes arrives when a manager object is constructed
rather than when an upload/download/copy method is called. `receiverContext`
preserves that constructor binding so implementation and multipart selection do
not lose an input merely because it lives on receiver state.

These predicates describe SDK execution behavior. They do not declare mapping
coverage or an unresolved profiler observation. Consumers decide how to handle
source that cannot prove a branch.

## What is generated

[`../tools/generate_owner_mappings.py`](../tools/generate_owner_mappings.py)
reads SDK models and the reviewed overlays as static data. It emits:

1. `botocore.aws.s3`, which owns canonical operations, client spellings,
   paginators, waiters, and extension Condition templates;
2. `s3transfer.aws.s3`, which owns public transfer entrypoints and references
   botocore operations;
3. `boto3.aws.s3`, which owns factories, resources, and wrapper bindings and
   references botocore and s3transfer.

The dependency chain is explicit:

```text
boto3 factory/resource/wrapper
  -> botocore client operation or waiter
  -> AWS S3 extension Condition

boto3 managed-transfer wrapper
  -> s3transfer logical call and selected execution path
  -> botocore client operations
  -> AWS S3 extension Conditions
```

The runtime SDK does not import or execute Runtime Conditions code.

## First repository integration

For each owning Python distribution, a maintainer would:

1. Add or adopt the relevant reviewed semantic overlay.
2. Enable the mapping projection in the repository's existing model/code-
   generation workflow.
3. Add two static package-data patterns for
   `runtimeconditions/index.json` and `runtimeconditions/mappings/*.json`.
4. Run the source and recursive-reference validation gates.
5. Review the semantic-overlay diff, generated count/digest summary, and
   representative resolution fixtures.
6. Publish the static files inside the normal SDK artifact. An additional
   artifact may also be published, but is not required by this proof.

The exact Python packaging changes, staging commands, local-wheel installation,
and measured results are in
[`../../../sdk/authorship/aws-python`](../../../sdk/authorship/aws-python/).

## Normal maintenance

- An unchanged operation set regenerates without service-semantic work.
- An added or removed service operation stops at the fingerprint gate for a
  concise semantic review.
- A routine generated Python spelling or resource-model change updates
  mechanically and is checked against the pinned source.
- A handwritten boto3 wrapper signature or delegate change stops source
  validation until its small overlay entry is updated.
- An s3transfer implementation change stops if its public signature or actual
  service-operation set differs from the reviewed logical call.
- A new language consumes the canonical service mapping and its own generator
  model. It does not reproduce S3 semantics by hand.

The generated JSON is not a human review surface. Review is the authored
semantic diff, source-model diff, count/fingerprint change, and fixture output.

## Application developer experience

For SDK-owned metadata, the application developer:

1. Uses and versions the SDK normally.
2. Runs the language profiler locally or in CI.
3. Reviews the generated profile when desired.

There is no new application dependency, mapping file, evidence file,
compatibility lock, or source annotation for recognized SDK calls. If no
mapping exists or detection is incomplete, the extension's no-op binding and a
project-local override remain the escape hatches; the application developer is
not asked to author an SDK mapping.

## What the SDK author does not decide

The mapping does not decide:

- how incomplete detection is handled;
- whether CI accepts or rejects a profile;
- what an adapter provisions or how it renders IAM;
- credentials, accounts, Regions, endpoints, or fixed environment variables;
- which compatible implementation a downstream platform uses;
- project-local override precedence.

Those belong to profiler behavior, organizational policy, the extension, or a
downstream adapter.

## Current gate

Packaging, recursive discovery, version ownership, source validation, and
unchanged-application regression tests are proved. The remaining architecture
review is whether real maintainers accept the three authored overlays and the
execution-path representation as a sustainable burden.

The current language profilers still do not consume this candidate. Expanding a
profiler remains a separate decision, as requested for this investigation.

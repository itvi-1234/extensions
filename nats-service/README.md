# NATS service extension

## Status

**Initial semantic candidate for SDK-authorship and adapter review.**

This extension describes the smallest NATS distinctions that can change an adapter decision: connecting to a NATS service, publishing, subscribing or requesting on a subject, and managing or using JetStream streams, consumers, key/value buckets, and object stores. It deliberately does not copy the `nats.go` method inventory into extension vocabulary.

The reviewed source is [`model/runtimeconditions.yaml`](model/runtimeconditions.yaml). [`tools/compile_extension.py`](tools/compile_extension.py) deterministically emits the immutable release and language-neutral operation vocabulary. Go SDK metadata must target the exact extension ID, version, and semantic digest generated here.

## Adapter-actionable minimum

An operation is retained only when it can change service enablement, NATS subject authorization, JetStream API authorization, or resource provisioning and policy. Retry options, callback shapes, asynchronous return types, message encoding, client buffering, and other SDK behavior are not extension semantics unless a downstream adapter would act differently because of them.

The vocabulary uses one `kind: nats` condition and `interface.type: service`. Each item in `interface.operations` is a distinct requirement, not one operation with combinatorial parameters. JSON Schema uses separate operation forms for connection, subjects, streams, consumers, key/value buckets, and object stores.

## Build

From the extensions repository root:

```sh
python3 nats-service/tools/compile_extension.py --model nats-service/model/runtimeconditions.yaml --extension-output nats-service/releases/0.1.0/runtimeconditions.extension.yaml --vocabulary-output nats-service/model/generated/nats-operation-vocabulary.yaml
```

## Current review boundary

The action groupings are intentionally smaller than the public Go SDK surface and larger than individual server protocol subjects. They must be reviewed with NATS maintainers and adapter authors before public release. The first Go applications are expected to reveal whether any grouping is too broad to produce correct authorization or provisioning decisions.

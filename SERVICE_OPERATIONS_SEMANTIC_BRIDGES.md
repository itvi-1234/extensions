# Service Operations Semantic Bridges

For the complete source-selection tutorial, last-resort inventory guidance, end-to-end example, ownership model, and change-propagation rules, see the [Service Operation Authoring Guide](https://github.com/runtimeconditions/spec/blob/main/docs/guides/service-operation-authoring.md).

## Purpose

A Service Operations Semantic Bridge is the reviewed authoring artifact that answers one question: **What adapter demand does a particular service operation prove?**

It separates facts owned by a service from semantics owned by a Runtime Conditions extension. It is not a published profile contract, an SDK mapping, an evidence report, or runtime input to a platform Adapter.

## Standard filename

Each operation-oriented extension uses `model/service-operations-semantic-bridge.yaml`.

## Source selection

The bridge's `operationSource` MUST select the best available language-neutral operation authority in this order:

1. A provider-maintained machine-readable service model such as Smithy, OpenAPI, protobuf, or an equivalent authoritative protocol definition.
2. A `service-operations-inventory.yaml` maintained outside the extensions repository when no adequate authoritative model exists.

The fallback inventory MUST contain service facts only. It does not contain Runtime Conditions extension coordinates, Condition fields, Adapter policy, SDK symbols, or profile emission rules.

Current examples intentionally use different source kinds:

- Amazon S3 references AWS's public Smithy model directly.
- Kubernetes references the authoritative Kubernetes OpenAPI document directly.
- NATS references a Service Operations Inventory because this experiment has not identified an adequate single upstream machine-readable operation model.

## Common contract

Every bridge has the same top-level envelope:

```yaml
apiVersion: runtimeconditions.io/service-operations-semantic-bridge/v1alpha1
kind: RuntimeConditionsServiceOperationsSemanticBridge
metadata:
  name: example.service
  service: example
operationSource:
  kind: OpenAPIDocument
  repository: https://example.com/provider/service.git
  path: api/openapi.yaml
extension:
  id: https://runtimeconditions.io/extensions/example/0.1.0/runtimeconditions.extension.yaml
  version: 0.1.0
  conditionKind: example
  interfaceType: service
```

The section after `extension` is source- and extension-specific because Smithy operations, HTTP paths, RPC methods, and protocol operations do not expose identical evidence. Each compiler validates its bridge dialect and every referenced operation or input against the selected source. The bridge must define only the translation that cannot be derived safely from that source.

## Generated outputs

A deterministic compiler can generate an extension definition and language-neutral service mapping when the bridge contains every adapter-facing semantic decision required for those outputs. This is real automatic generation of expansion, validation, identity paths, and operation-to-Condition mappings; it is not automatic invention of semantics.

The generated extension remains a standalone vocabulary and validation contract. It does not retain the bridge, source inventory, or authoring provenance because profile generators and platform Adapters do not need that paper trail at runtime.

The generated service mapping retains source and bridge digests because SDK mapping generators need a reproducible operation-to-Condition boundary. Language-specific SDK mappings then add only SDK-owned public symbols, parameters, state flow, delegation, and release identity.

## Change propagation

The compiler classifies source changes by their semantic result:

| Change | Bridge | Extension | Service mapping | Affected SDK mappings |
| --- | --- | --- | --- | --- |
| Source-only metadata or formatting change | No semantic edit | Unchanged | Regenerated provenance may change | Regenerate only if SDK inputs changed |
| New source operation maps to existing Condition vocabulary | Add or approve its translation | Unchanged when generated vocabulary is unchanged | Regenerate | Regenerate every SDK mapping whose release exposes the operation |
| Existing source operation changes how it proves a Condition | Review translation | Revise only if vocabulary or validation changes | Regenerate | Regenerate and validate affected SDK mappings |
| New adapter-facing distinction is required | Add semantic decision | Revise and version | Regenerate against new extension | Regenerate affected SDK mappings against the compatible extension release |
| SDK public surface changes without service semantic change | Unchanged | Unchanged | Unchanged | Regenerate that SDK mapping |

“Extension unchanged” never means “SDK mappings unchanged.” A language mapping must still know which SDK method, command, wrapper, or delegate reaches the newly available service operation. SDKs that do not expose that operation do not fabricate a mapping for it.

## Review surface

Maintainers review bridge changes, focused semantic summaries, representative profiles, and Adapter impact. They are not expected to review generated extension expansions, generated service mappings, or complete SDK symbol mappings line by line.

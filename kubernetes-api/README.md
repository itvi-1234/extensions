# Kubernetes API extension

## Status

**Accepted local semantic release — ready for maintainer review before public publication.**

This directory defines the semantic ground truth that an official Kubernetes client mapping targets. It begins with Kubernetes v1.36.2 and the official Python client 36.0.3, while representing Kubernetes API requirements independently of a particular client language or generated release.

[`releases/0.1.0/runtimeconditions.extension.yaml`](releases/0.1.0/runtimeconditions.extension.yaml) is the immutable local release produced from the approved [`model/runtimeconditions.yaml`](model/runtimeconditions.yaml) semantic contract. [`model/generated/extension-review.md`](model/generated/extension-review.md) is its human review surface; the 1,123-operation service mapping is deterministic machine output.

## Why this case matters

Kubernetes provides an authoritative OpenAPI model and official generated clients, making it a strong test of whether the AWS/Smithy workflow generalizes. It also prevents an easy but incorrect generalization: Kubernetes clusters may install CustomResourceDefinitions, so a conforming extension cannot treat the built-in OpenAPI resource inventory as a closed list of every valid Kubernetes API requirement.

The initial unchanged application is [`../../sdk/kubernetes/python/configmap-reader`](../../sdk/kubernetes/python/configmap-reader/). It calls `CoreV1Api.read_namespaced_config_map`, which the Kubernetes v1.36 OpenAPI document identifies as `readCoreV1NamespacedConfigMap` with action `get`, group `""`, version `v1`, kind `ConfigMap`, and a namespaced resource path.

## Authoritative inputs

- Kubernetes built-in API semantics: `https://github.com/kubernetes/kubernetes/blob/v1.36.2/api/openapi-spec/swagger.json`
- Official Python SDK surface: `https://github.com/kubernetes-client/python/tree/v36.0.3`
- Python distribution: `kubernetes==36.0.3`

[`maintenance/openapi.yaml`](maintenance/openapi.yaml) records the exact upstream revisions plus byte and semantic digests. The Python release retains the upstream model before and after its generator transforms it, which lets extension automation validate authoritative API meaning independently from SDK automation that validates the published Python surface. [`docs/provenance-and-generation.md`](docs/provenance-and-generation.md) explains that relationship.

## Deterministic projection

[`tools/project_openapi.py`](tools/project_openapi.py) validates and projects the complete authoritative model into [`model/generated/kubernetes-v1.36-operation-inventory.yaml`](model/generated/kubernetes-v1.36-operation-inventory.yaml). Humans review [`model/generated/openapi-review.md`](model/generated/openapi-review.md), not the 1,123-entry generated inventory.

[`tools/compile_extension.py`](tools/compile_extension.py) then validates every projected operation against the approved open CRD-compatible schema and emits the immutable extension plus [`model/generated/kubernetes-service-mapping.yaml`](model/generated/kubernetes-service-mapping.yaml). Resource, connect, and non-resource operations remain distinct validated forms; connect operations preserve HTTP method.

Install the authoring-only dependency with `python3 -m pip install -r kubernetes-api/requirements.txt`, then run the projection from the extension repository root with an immutable local copy of the source model:

```sh
python kubernetes-api/tools/project_openapi.py \
  --model /absolute/path/to/kubernetes-v1.36.2-swagger.json \
  --source-repository https://github.com/kubernetes/kubernetes.git \
  --source-revision 24e2b02af5543d7910c2bb074c7264df5a8f0467 \
  --source-ref v1.36.2 \
  --source-path api/openapi-spec/swagger.json \
  --inventory-output kubernetes-api/model/generated/kubernetes-v1.36-operation-inventory.yaml \
  --review-output kubernetes-api/model/generated/openapi-review.md
```

## Current boundary

[`docs/design.md`](docs/design.md) records the accepted vocabulary, derivation rules, CRD requirement, authoring burden, and acceptance gates. [`../../sdk/authorship/kubernetes-python`](../../sdk/authorship/kubernetes-python/) packages the conforming Python mapping against the release's exact semantic digest. Public publication and upstream maintainer integration remain separate from this accepted local proof.

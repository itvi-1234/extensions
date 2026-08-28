# Kubernetes OpenAPI semantic review

**Classification: `investigation`**

The authoritative Kubernetes operation inventory projected deterministically. The extension vocabulary remains unreleased while the structured resource, non-resource, connect, watch, and dynamic-resource semantics are reviewed.

## Authoritative input

- Repository: `https://github.com/kubernetes/kubernetes.git`
- Revision: `24e2b02af5543d7910c2bb074c7264df5a8f0467`
- Release ref: `v1.36.2`
- Path: `api/openapi-spec/swagger.json`
- Source SHA-256: `dcede2063da1d7ad62ecb5af8adb6d7fabd0b52385a7fa0048afb491dac90450`
- Source semantic SHA-256: `ca58855c8fe1774f8859e957ec94ebb41b016ea726e986f166460eefce488cfd`
- Operation IDs: 1123
- Operation-ID SHA-256: `f32fcf3c6d90729c067ef7df8b7ece4e9c9cc52a7a29958d1df6519e0471e15d`
- Inventory semantic SHA-256: `0ea1345e622231970d47bd80a0babc84a7425edf17596673e9112882b0b2a701`

## Inventory

- Resource operations: 1058
- Non-resource operations: 65
- Resource families: 95 (43 namespaced, 52 cluster-scoped)
- Access scopes: `all_namespaces` 82, `cluster` 489, `namespaced` 487
- Connect operations requiring a vocabulary decision: 48
- Endpoint/GVK group-version differences requiring the endpoint coordinates to remain authoritative: 14

| Normalized verb | Operations |
| --- | ---: |
| `connect` | 48 |
| `create` | 97 |
| `delete` | 87 |
| `deletecollection` | 86 |
| `get` | 133 |
| `list` | 129 |
| `patch` | 131 |
| `update` | 132 |
| `watch` | 215 |

## Representative operation

`readCoreV1NamespacedConfigMap` projects to `get` on `core/v1` resource `configmaps` with `namespaced` access.

## Findings that affect extension design

- A namespaced resource can be accessed within one namespace or across all namespaces. The operation needs `namespaced`, `all_namespaces`, and `cluster` access scopes rather than a single resource-scope flag.
- The endpoint group and version identify the accessed API resource. GVK identifies the request or response representation and differs for eviction, scale, and token subresources, so it cannot replace endpoint coordinates.
- Dedicated watch and watch-list endpoints normalize to the same logical `watch` verb in the language-neutral inventory, but an SDK generator may transform or remove those endpoints and must own the resulting language behavior.
- Non-resource endpoints need a separately validated operation form instead of being forced into resource coordinates.
- Connect operations preserve the authoritative Kubernetes action and HTTP method until maintainers approve adopter-facing semantics for attach, exec, port-forward, and proxy access.

## Human review surface

Review the structured operation forms, access-scope distinctions, connect semantics, non-resource representation, CRD compatibility, and representative adapter impact. The complete generated YAML inventory is machine output and is not a line-by-line review surface.

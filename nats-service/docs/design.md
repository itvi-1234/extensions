# NATS extension design

## Dependency boundary

A NATS client call proves a dependency on a NATS service and may additionally prove subject authorization or a JetStream resource action. The extension records those environment-facing facts without recording Go package names, receiver types, callback signatures, internal `$JS.API` subjects, connection environment variables, authentication mechanisms, or server topology.

The `nats` kind identifies the provider and protocol family. The `service` interface reflects that Core NATS and JetStream capabilities are enabled and authorized through one NATS account even when the application addresses several subjects or resources.

## Operation forms

- A connection operation proves only that the workload needs a reachable NATS service.
- A subject operation distinguishes publish, subscribe, and request because they require different authorization. Request is not collapsed into publish because it also requires a reply inbox.
- Stream actions distinguish management and inspection from publishing. Stream publishing can be proven from a subject even when the application does not know the owning stream name.
- Consumer actions retain the stream and, when source proves it, the consumer name.
- Key/value and object-store actions retain bucket identity and distinguish management, inspection, reading, writing, and watching.

These are separate array items validated by separate JSON Schema branches. An SDK mapping binds a concrete call to exactly one branch; it does not select a resource/action combination from arbitrary values at profiling time.

## Deliberate omissions

The extension does not declare credentials, environment-variable names, URLs, accounts, clusters, replicas, storage classes, retention policy, maximum sizes, or timeouts unless application source and future adapter review establish that they belong in a portable demand. Creating a resource through the SDK proves a management authorization requirement; it does not tell an adapter to create a duplicate resource.

SDK methods that merely configure local client behavior emit no condition. Calls whose resource or subject cannot be statically resolved emit no inferred operation; application developers can use extension-provided no-op bindings when their organization requires an explicit declaration.

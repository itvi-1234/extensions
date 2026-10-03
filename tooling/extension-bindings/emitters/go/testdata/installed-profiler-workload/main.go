package workload

import bindings "example.com/runtimeconditions/conformance/owned-kind-interface"

var _ = bindings.Service(
	bindings.Http{Endpoint: "https://example.invalid"},
	bindings.Region("eu"),
)

package orchestrator

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func testProfilerIdentities(t *testing.T) (ProfilerIdentity, ProfilerIdentity) {
	t.Helper()
	standalone, err := NewStandaloneProfilerIdentity(Tool{Name: "go-rc-profiler", Version: "v0.6.0", SHA256: strings.Repeat("0", 64)})
	if err != nil {
		t.Fatal(err)
	}
	linked, err := NewLinkedGoProfilerIdentity("v0.6.0", "h1:"+strings.Repeat("A", 43)+"=")
	if err != nil {
		t.Fatal(err)
	}
	return standalone, linked
}

func changedProfiler(identity ProfilerIdentity, change func(*ProfilerIdentity)) ProfilerIdentity {
	change(&identity)
	return identity
}

func profilerIdentityMapping(t *testing.T, identity ProfilerIdentity) map[string]any {
	t.Helper()
	data, err := json.Marshal(identity)
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func testProfilerSchemas(t *testing.T) map[string]map[string]any {
	t.Helper()
	schemas := map[string]map[string]any{}
	for name, path := range map[string]string{
		"release":     filepath.Join("..", "model", "runtimeconditions.binding-release.schema.yaml"),
		"lock":        filepath.Join("..", "model", "runtimeconditions.toolchain-lock.schema.yaml"),
		"Go profiler": filepath.Join("..", "..", "..", "..", "go-rc-profiler", "extensioncheck", "schema", "runtimeconditions.binding-release.schema.yaml"),
	} {
		schema, err := readMapping(path)
		if name == "Go profiler" && os.IsNotExist(err) {
			t.Log("sibling Go profiler checkout absent; embedded schema comparison omitted")
			continue
		}
		if err != nil {
			t.Fatal(err)
		}
		schemas[name] = schema
	}
	return schemas
}

func TestStandaloneProfilerIdentityPreservesLegacyEncoding(t *testing.T) {
	tool := Tool{Name: "go-rc-profiler", Version: "v0.6.0", SHA256: strings.Repeat("a", 64), ArtifactURL: "https://example.test/profiler.tar.gz"}
	identity, err := NewStandaloneProfilerIdentity(tool)
	if err != nil {
		t.Fatal(err)
	}
	for _, marshal := range []func(any) ([]byte, error){json.Marshal, yaml.Marshal} {
		before, err := marshal(tool)
		if err != nil {
			t.Fatal(err)
		}
		after, err := marshal(identity)
		if err != nil || !bytes.Equal(before, after) {
			t.Fatalf("legacy identity encoding changed: %s -> %s (%v)", before, after, err)
		}
	}
	if _, err := NewStandaloneProfilerIdentity(Tool{}); err == nil {
		t.Fatal("empty standalone identity accepted")
	}
	if _, err := NewLinkedGoProfilerIdentity("unknown", ""); err == nil {
		t.Fatal("unknown linked identity accepted")
	}
}

func TestProfilerIdentityValidationAndSchemaAgreement(t *testing.T) {
	standalone, linked := testProfilerIdentities(t)
	schemas := testProfilerSchemas(t)
	for name, schema := range schemas {
		for _, definition := range []string{"profilerIdentity", "linkedGoProfilerIdentity"} {
			if !reflect.DeepEqual(mapValue(schema["$defs"])[definition], mapValue(schemas["release"]["$defs"])[definition]) {
				t.Fatalf("%s disagrees on %s", name, definition)
			}
		}
	}
	for _, tc := range []struct {
		name     string
		identity ProfilerIdentity
		valid    bool
	}{
		{"standalone", standalone, true}, {"linked", linked, true},
		{"prerelease", changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6.1-rc.1" }), true},
		{"pseudo version", changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6.1-0.20261109120000-0123456789ab" }), true},
		{"empty", ProfilerIdentity{}, false},
		{"missing name", changedProfiler(standalone, func(p *ProfilerIdentity) { p.Name = "" }), false},
		{"missing version", changedProfiler(standalone, func(p *ProfilerIdentity) { p.Version = "" }), false},
		{"uppercase digest", changedProfiler(standalone, func(p *ProfilerIdentity) { p.SHA256 = strings.Repeat("A", 64) }), false},
		{"short digest", changedProfiler(standalone, func(p *ProfilerIdentity) { p.SHA256 = "1234" }), false},
		{"invalid retrieval URL", changedProfiler(standalone, func(p *ProfilerIdentity) { p.ArtifactURL = "http://example.test/profiler" }), false},
		{"artifact with module", changedProfiler(standalone, func(p *ProfilerIdentity) { p.Module = linked.Module }), false},
		{"artifact with module sum", changedProfiler(standalone, func(p *ProfilerIdentity) { p.ModuleSum = linked.ModuleSum }), false},
		{"unknown kind", changedProfiler(linked, func(p *ProfilerIdentity) { p.Kind = "other" }), false},
		{"wrong profiler", changedProfiler(linked, func(p *ProfilerIdentity) { p.Name = "python-rc-profiler" }), false},
		{"wrong module", changedProfiler(linked, func(p *ProfilerIdentity) { p.Module = "example.test/profiler" }), false},
		{"linked with artifact", changedProfiler(linked, func(p *ProfilerIdentity) { p.SHA256 = standalone.SHA256 }), false},
		{"linked with URL", changedProfiler(linked, func(p *ProfilerIdentity) { p.ArtifactURL = "https://example.test/profiler" }), false},
		{"unknown version", changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "unknown" }), false},
		{"short version", changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6" }), false},
		{"leading zero", changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6.0-rc.01" }), false},
		{"noncanonical version", changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6.0+local" }), false},
		{"hex module sum", changedProfiler(linked, func(p *ProfilerIdentity) { p.ModuleSum = standalone.SHA256 }), false},
		{"noncanonical padding", changedProfiler(linked, func(p *ProfilerIdentity) { p.ModuleSum = "h1:" + strings.Repeat("A", 42) + "B=" }), false},
		{"checksum newline", changedProfiler(linked, func(p *ProfilerIdentity) { p.ModuleSum += "\n" }), false},
		{"missing checksum", changedProfiler(linked, func(p *ProfilerIdentity) { p.ModuleSum = "" }), false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if err := tc.identity.Validate(); (err == nil) != tc.valid {
				t.Fatalf("identity validity: %v; want %t", err, tc.valid)
			}
			for name, schema := range schemas {
				identitySchema := map[string]any{"$ref": "#/$defs/profilerIdentity", "$defs": schema["$defs"]}
				if err := validateSchema(identitySchema, profilerIdentityMapping(t, tc.identity)); (err == nil) != tc.valid {
					t.Errorf("%s schema validity: %v; want %t", name, err, tc.valid)
				}
			}
		})
	}
	for name, schema := range schemas {
		value := profilerIdentityMapping(t, linked)
		value["unknown"] = "must reject"
		if err := validateSchema(map[string]any{"$ref": "#/$defs/profilerIdentity", "$defs": schema["$defs"]}, value); err == nil {
			t.Errorf("%s accepted an unknown identity field", name)
		}
	}
}

func TestProfilerIdentityMatchRequiresExactKindVersionAndChecksum(t *testing.T) {
	standalone, linked := testProfilerIdentities(t)
	for _, tc := range []struct {
		name               string
		expected, selected ProfilerIdentity
		match              bool
	}{
		{"artifact", standalone, standalone, true}, {"module", linked, linked, true},
		{"retrieval URL", standalone, changedProfiler(standalone, func(p *ProfilerIdentity) { p.ArtifactURL = "https://example.test/mirror" }), true},
		{"name", standalone, changedProfiler(standalone, func(p *ProfilerIdentity) { p.Name = "other" }), false},
		{"artifact version", standalone, changedProfiler(standalone, func(p *ProfilerIdentity) { p.Version = "v0.6.1" }), false},
		{"module version", linked, changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6.1" }), false},
		{"digest", standalone, changedProfiler(standalone, func(p *ProfilerIdentity) { p.SHA256 = strings.Repeat("1", 64) }), false},
		{"module sum", linked, changedProfiler(linked, func(p *ProfilerIdentity) { p.ModuleSum = "h1:" + strings.Repeat("B", 42) + "A=" }), false},
		{"module for executable lock", standalone, linked, false}, {"executable for module lock", linked, standalone, false},
		{"incomplete lock", ProfilerIdentity{}, linked, false}, {"incomplete selection", linked, ProfilerIdentity{}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if err := tc.expected.Match(tc.selected); (err == nil) != tc.match {
				t.Fatalf("match: %v; want %t", err, tc.match)
			}
		})
	}
}

func TestProfilerIdentityInReleaseAndLockDocuments(t *testing.T) {
	standalone, linked := testProfilerIdentities(t)
	schemas := testProfilerSchemas(t)
	for name, schema := range schemas {
		if name == "lock" {
			continue
		}
		doc, err := readMapping(filepath.Join("..", "..", "..", "bindings", "env-configuration", "go", releaseName))
		if err != nil {
			t.Fatal(err)
		}
		if err := validateSchema(schema, doc); err != nil {
			t.Fatalf("%s rejected legacy release: %v", name, err)
		}
		mapValue(doc["provenance"])["profiler"] = profilerIdentityMapping(t, linked)
		if err := validateSchema(schema, doc); err != nil {
			t.Fatalf("%s rejected linked release: %v", name, err)
		}
		pkg := mapValue(doc["package"])
		pkg["language"], pkg["minimumPythonVersion"] = "python", "3.11"
		delete(pkg, "minimumGoVersion")
		for _, dependency := range sequence(doc["packageDependencies"]) {
			mapValue(mapValue(dependency)["artifact"])["kind"] = "python-wheel"
		}
		mapValue(doc["provenance"])["profiler"] = profilerIdentityMapping(t, changedProfiler(standalone, func(p *ProfilerIdentity) { p.Name = "python-rc-profiler" }))
		if err := validateSchema(schema, doc); err != nil {
			t.Fatalf("%s rejected Python release: %v", name, err)
		}
		mapValue(doc["provenance"])["profiler"] = profilerIdentityMapping(t, linked)
		if err := validateSchema(schema, doc); err == nil {
			t.Fatalf("%s accepted linked Go profiler for Python", name)
		}
	}
	artifact := profilerIdentityMapping(t, standalone)
	profilers := map[string]any{"go": artifact}
	doc := map[string]any{
		"apiVersion": "runtimeconditions.io/toolchain-lock/v1alpha1", "kind": "RuntimeConditionsToolchainLock", "status": "released",
		"tools":     map[string]any{"normalizer": artifact, "orchestrator": artifact, "emitters": map[string]any{"go": artifact}, "profilers": profilers},
		"languages": map[string]any{"go": map[string]any{"languageVersion": "1.25.0", "packageManager": "go", "tools": map[string]any{"go": "1.25.0"}}},
	}
	if err := validateSchema(schemas["lock"], doc); err != nil {
		t.Fatal("legacy lock rejected", err)
	}
	profilers["go"] = profilerIdentityMapping(t, linked)
	if err := validateSchema(schemas["lock"], doc); err != nil {
		t.Fatal("linked Go lock rejected", err)
	}
	profilers["python"] = profilerIdentityMapping(t, linked)
	if err := validateSchema(schemas["lock"], doc); err == nil {
		t.Fatal("linked Go identity accepted for Python lock")
	}
}

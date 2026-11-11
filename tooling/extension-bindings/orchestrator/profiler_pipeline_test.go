package orchestrator

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func writeProfilerFixture(t *testing.T, path string, value any) {
	t.Helper()
	data, err := yaml.Marshal(value)
	if err == nil {
		err = os.WriteFile(path, data, 0644)
	}
	if err != nil {
		t.Fatal(err)
	}
}

func profilerPipelineProject(t *testing.T) (*Project, Options) {
	t.Helper()
	p, o := testProject(t, "go")
	o.CoreSchema = filepath.Join(p.Root, "core.yaml")
	writeProfilerFixture(t, o.CoreSchema, map[string]any{"$id": "https://runtimeconditions.io/schemas/profile/0.2.0/runtimeconditions.profile.schema.yaml", "type": "object"})
	return p, o
}

func standaloneProfilerFixture(t *testing.T) (string, ProfilerIdentity) {
	t.Helper()
	directory := t.TempDir()
	for name, content := range map[string]string{
		"go.mod":  "module example.test/standalone-profiler\n\ngo 1.22\n",
		"main.go": "package main\nfunc main() { panic(\"profiler identity inspection must not execute the binary\") }\n",
	} {
		if err := os.WriteFile(filepath.Join(directory, name), []byte(content), 0644); err != nil {
			t.Fatal(err)
		}
	}
	path := filepath.Join(directory, "profiler")
	command := exec.Command(envOr("RC_BINDINGS_GO", "go"), "build", "-trimpath", "-buildvcs=false", "-o", path, ".")
	command.Dir = directory
	if data, err := command.CombinedOutput(); err != nil {
		t.Fatalf("build standalone identity fixture: %v\n%s", err, data)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	identity, err := NewStandaloneProfilerIdentity(Tool{Name: "go-rc-profiler", Version: "v0.6.0", SHA256: fmt.Sprintf("%x", sha256.Sum256(data))})
	if err != nil {
		t.Fatal(err)
	}
	return path, identity
}

func TestProfilerPipelineGeneratesVerifiesAndRejectsTampering(t *testing.T) {
	path, standalone := standaloneProfilerFixture(t)
	_, linked := testProfilerIdentities(t)
	for _, expected := range []ProfilerIdentity{standalone, linked} {
		name := "standalone"
		if expected.Kind != "" {
			name = "linked"
		}
		t.Run(name, func(t *testing.T) {
			p, o := profilerPipelineProject(t)
			p.Toolchain.Tools.Profilers = map[string]ProfilerIdentity{"go": expected}
			selected := expected
			if expected.Kind == "" {
				t.Setenv("RC_GO_PROFILER_BIN", path)
				o.GoProfiler = DefaultOptions().GoProfiler
			} else {
				t.Setenv("RC_GO_PROFILER_BIN", filepath.Join(p.Root, "absent-profiler"))
				o.LinkedGoProfiler = &selected
			}
			pipeline, err := NewPipeline(context.Background(), p, o)
			if err != nil {
				t.Fatal(err)
			}
			defer pipeline.Close()
			selected.ModuleSum = "caller changed its identity after construction"
			plan, err := p.SelectTargets(nil)
			if err != nil {
				t.Fatal(err)
			}
			build, err := pipeline.Generate(plan)
			if err != nil {
				t.Fatal(err)
			}
			if summary, err := pipeline.Verify(build); err != nil || summary.Status != "passed" {
				t.Fatalf("verify generated %s bindings: %v %+v", name, err, summary)
			}
			releasePath := filepath.Join(build.Targets[0].Directory, releaseName)
			document, err := readMapping(releasePath)
			if err != nil {
				t.Fatal(err)
			}
			data, err := json.Marshal(mapValue(document["provenance"])["profiler"])
			if err != nil {
				t.Fatal(err)
			}
			var recorded ProfilerIdentity
			if err := json.Unmarshal(data, &recorded); err != nil {
				t.Fatal(err)
			}
			if err := expected.Match(recorded); err != nil {
				t.Fatal("generated profiler identity", err)
			}
			mutations := []ProfilerIdentity{changedProfiler(expected, func(p *ProfilerIdentity) { p.Version = "v0.6.1" })}
			if expected.Kind == "" {
				mutations = append(mutations, linked, changedProfiler(expected, func(p *ProfilerIdentity) { p.SHA256 = strings.Repeat("f", 64) }))
			} else {
				mutations = append(mutations, standalone, changedProfiler(expected, func(p *ProfilerIdentity) { p.ModuleSum = "h1:" + strings.Repeat("B", 42) + "A=" }))
			}
			for _, tampered := range mutations {
				copy := mapValue(jsonCopy(document))
				mapValue(copy["provenance"])["profiler"] = tampered
				writeProfilerFixture(t, releasePath, copy)
				if _, err := pipeline.Verify(build); err == nil || !strings.Contains(err.Error(), "profiler provenance") {
					t.Fatalf("tampered profiler metadata accepted or wrong failure: %+v, %v", tampered, err)
				}
			}
		})
	}
}

func TestProfilerPipelineReadsReleasedModuleLockAndProtectsCommittedSource(t *testing.T) {
	p, o := profilerPipelineProject(t)
	standalone, linked := testProfilerIdentities(t)
	artifact := Tool{Name: "fixture-tool", Version: "0.1.0", SHA256: strings.Repeat("0", 64)}
	lock := map[string]any{
		"apiVersion": "runtimeconditions.io/toolchain-lock/v1alpha1", "kind": "RuntimeConditionsToolchainLock", "status": "released",
		"tools":     map[string]any{"normalizer": artifact, "orchestrator": artifact, "emitters": map[string]any{"go": artifact}, "profilers": map[string]any{"go": linked}},
		"languages": map[string]any{"go": map[string]any{"languageVersion": p.Catalog.Packages["new-channel"].Languages["go"].LanguageVersion, "packageManager": "go", "tools": map[string]any{"go": "fixture"}}},
	}
	writeProfilerFixture(t, p.ToolchainPath, lock)
	found, err := DiscoverProject(p.Root, "", "", p.ToolingDirectory)
	if err != nil {
		t.Fatal(err)
	}
	if err := linked.Match(found.Toolchain.Tools.Profilers["go"]); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name          string
		selected, pin ProfilerIdentity
		path, want    string
	}{
		{"conflict", linked, linked, "explicit-standalone-profiler", "select either"},
		{"wrong option kind", standalone, linked, "", "linked Go module identity"},
		{"unknown identity", changedProfiler(linked, func(p *ProfilerIdentity) { p.ModuleSum = "unknown" }), linked, "", "checksum"},
		{"version mismatch", changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6.1" }), linked, "", "version differs"},
		{"checksum mismatch", changedProfiler(linked, func(p *ProfilerIdentity) { p.ModuleSum = "h1:" + strings.Repeat("B", 42) + "A=" }), linked, "", "module identity differs"},
		{"artifact lock", linked, standalone, "", "identity kind differs"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			found.Toolchain.Tools.Profilers["go"] = tc.pin
			options := o
			options.LinkedGoProfiler, options.GoProfiler = &tc.selected, tc.path
			if pipeline, err := NewPipeline(context.Background(), found, options); err == nil || !strings.Contains(err.Error(), tc.want) {
				if pipeline != nil {
					pipeline.Close()
				}
				t.Fatalf("invalid selection: %v; want %s", err, tc.want)
			}
		})
	}
	directory := filepath.Join(p.Root, "bindings", "new-channel", "go")
	if err := os.MkdirAll(directory, 0755); err != nil {
		t.Fatal(err)
	}
	sentinel := filepath.Join(directory, "keep.go")
	if err := os.WriteFile(sentinel, []byte("preserve committed bytes\n"), 0644); err != nil {
		t.Fatal(err)
	}
	wrong := changedProfiler(linked, func(p *ProfilerIdentity) { p.Version = "v0.6.1" })
	o.LinkedGoProfiler = &wrong
	o.WorkDir = filepath.Join(p.Root, "must-not-create")
	var stdout bytes.Buffer
	if err := Execute(context.Background(), p.Root, "update", o, &stdout, io.Discard); err == nil || !strings.Contains(err.Error(), "version differs") {
		t.Fatalf("update ignored profiler lock: %v", err)
	}
	if data, err := os.ReadFile(sentinel); err != nil || string(data) != "preserve committed bytes\n" || stdout.Len() != 0 {
		t.Fatalf("rejected update affected committed output: %s %v", data, err)
	}
	if _, err := os.Stat(o.WorkDir); !os.IsNotExist(err) {
		t.Fatal("rejected update created work directory")
	}
}

func TestProfilerPipelineNeverFallsBackFromStandaloneSelection(t *testing.T) {
	p, o := profilerPipelineProject(t)
	_, linked := testProfilerIdentities(t)
	for _, pin := range []ProfilerIdentity{{}, linked} {
		p.Toolchain.Tools.Profilers = nil
		if pin.Kind != "" {
			p.Toolchain.Tools.Profilers = map[string]ProfilerIdentity{"go": pin}
		}
		for _, path := range []string{"", filepath.Join(p.Root, "missing-profiler")} {
			o.GoProfiler = path
			pipeline, err := NewPipeline(context.Background(), p, o)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := pipeline.profiler("go"); err == nil {
				t.Fatal("standalone selection silently used another profiler")
			}
			if pipeline.work != "" {
				t.Fatal("missing standalone profiler triggered workspace build")
			}
			pipeline.Close()
		}
	}
}

func TestProfilerPipelineChecksCachedPythonArtifactAgainstLock(t *testing.T) {
	p, o := testProject(t, "python")
	identity, _ := testProfilerIdentities(t)
	identity.Name = "python-rc-profiler"
	p.Toolchain.Tools.Profilers = map[string]ProfilerIdentity{"python": identity}
	pipeline, err := NewPipeline(context.Background(), p, o)
	if err != nil {
		t.Fatal(err)
	}
	defer pipeline.Close()
	pipeline.identities["python-profiler"] = Tool{Name: identity.Name, Version: identity.Version, SHA256: identity.SHA256}
	if selected, err := pipeline.profiler("python"); err != nil || selected != identity {
		t.Fatalf("cached standalone Python identity: %+v %v", selected, err)
	}
	p.Toolchain.Tools.Profilers["python"] = changedProfiler(identity, func(p *ProfilerIdentity) { p.SHA256 = strings.Repeat("f", 64) })
	if _, err := pipeline.profiler("python"); err == nil {
		t.Fatal("cached Python profiler bypassed a mismatched lock")
	}
}

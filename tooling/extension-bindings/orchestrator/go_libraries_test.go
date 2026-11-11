package orchestrator

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/runtimeconditions/extensions/tooling/extension-bindings/normalizer"
)

func goLibraryProject(t *testing.T) (*Project, Options) {
	t.Helper()
	p, o := profilerPipelineProject(t)
	o.ToolingDir = t.TempDir()
	if err := copyTree(filepath.Join(p.ToolingDirectory, "model"), filepath.Join(o.ToolingDir, "model")); err != nil {
		t.Fatal(err)
	}
	p, err := DiscoverProject(p.Root, "", "", o.ToolingDir)
	if err != nil {
		t.Fatal(err)
	}
	_, linked := testProfilerIdentities(t)
	o.UseGoLibraries, o.LinkedGoProfiler = true, &linked
	return p, o
}

func TestGoLibrariesGenerateAndVerifyWithoutToolExecutables(t *testing.T) {
	standalonePath, standaloneIdentity := standaloneProfilerFixture(t)
	for _, mode := range []string{"linked", "standalone"} {
		t.Run(mode, func(t *testing.T) {
			p, o := goLibraryProject(t)
			if mode == "standalone" {
				o.GoProfiler, o.LinkedGoProfiler = standalonePath, nil
				p.Toolchain.Tools.Profilers = map[string]ProfilerIdentity{"go": standaloneIdentity}
			}
			goCommand := o.Go
			o.Go = filepath.Join(p.Root, "no-build-command")
			pipeline, err := NewPipeline(context.Background(), p, o)
			if err != nil {
				t.Fatal(err)
			}
			defer pipeline.Close()
			plan, err := p.SelectTargets(nil)
			if err != nil {
				t.Fatal(err)
			}
			build, err := pipeline.Generate(plan)
			if err != nil {
				t.Fatal(err)
			}
			host, err := os.Executable()
			if err != nil {
				t.Fatal(err)
			}
			data, err := os.ReadFile(host)
			if err != nil {
				t.Fatal(err)
			}
			digest := normalizer.SHA256Hex(data)
			bt := build.Targets[0]
			if bt.Document.Model.Metadata.Normalizer.SHA256 != digest || bt.PackageConfig["emitterSha256"] != digest {
				t.Fatal("library provenance does not identify the executing host")
			}
			for _, directory := range []string{"tools", "normalizer-inputs"} {
				if _, err := os.Stat(filepath.Join(pipeline.work, directory)); !os.IsNotExist(err) {
					t.Fatalf("library mode created %s: %v", directory, err)
				}
			}
			pipeline.Options.Go = goCommand // Native verification still requires Go.
			loaded, err := pipeline.LoadBuild(plan, bt.Directory)
			if err != nil {
				t.Fatal(err)
			}
			if summary, err := pipeline.Verify(loaded); err != nil || summary.Status != "passed" {
				t.Fatalf("verify library-generated bindings: %v %+v", err, summary)
			}
		})
	}
}

func TestGoLibrariesMatchStandaloneGeneration(t *testing.T) {
	p, o := profilerPipelineProject(t)
	_, linked := testProfilerIdentities(t)
	o.LinkedGoProfiler = &linked
	var builds []*Build
	for _, library := range []bool{false, true} {
		o.UseGoLibraries = library
		pipeline, err := NewPipeline(context.Background(), p, o)
		if err != nil {
			t.Fatal(err)
		}
		defer pipeline.Close()
		plan, err := p.SelectTargets(nil)
		if err != nil {
			t.Fatal(err)
		}
		build, err := pipeline.Generate(plan)
		if err != nil {
			t.Fatal(err)
		}
		builds = append(builds, build)
	}
	standalone, library := builds[0].Targets[0], builds[1].Targets[0]
	model := library.Document.Model
	model.Metadata.Normalizer = standalone.Document.Model.Metadata.Normalizer
	var err error
	model.Metadata.SemanticSHA256, err = normalizer.ModelSemanticSHA256(model)
	if err != nil {
		t.Fatal(err)
	}
	left, err := normalizer.CanonicalModelYAML(model)
	if err != nil {
		t.Fatal(err)
	}
	right, err := standalone.Document.ModelYAML()
	if err != nil || !bytes.Equal(left, right) {
		t.Fatalf("normalization differs beyond executing-artifact provenance: %v", err)
	}
	leftTree, err := readTree(library.Directory)
	if err != nil {
		t.Fatal(err)
	}
	rightTree, err := readTree(standalone.Directory)
	if err != nil {
		t.Fatal(err)
	}
	for name, data := range leftTree {
		if strings.HasSuffix(name, ".go") || name == "go.mod" {
			data = bytes.ReplaceAll(data, []byte(library.Document.Model.Metadata.SemanticSHA256), []byte(model.Metadata.SemanticSHA256))
			if !bytes.Equal(data, rightTree[name]) {
				t.Fatalf("native source differs: %s", name)
			}
		}
	}
}

func TestGoLibrariesRejectConflictsAndMismatchedLocksBeforeWork(t *testing.T) {
	p, o := goLibraryProject(t)
	pipeline, err := NewPipeline(context.Background(), p, o)
	if err != nil {
		t.Fatal(err)
	}
	defer pipeline.Close()
	pins := pipeline.identities
	o.WorkDir = filepath.Join(p.Root, "must-not-create")
	for _, component := range []string{"normalizer", "go-emitter"} {
		for _, field := range []string{"executable", "name", "version", "digest", "missing released pin"} {
			t.Run(component+"/"+field, func(t *testing.T) {
				project, options := *p, o
				project.Toolchain = Toolchain{Status: "development"}
				pin := pins[component]
				switch field {
				case "executable":
					if component == "normalizer" {
						options.Normalizer = "missing-normalizer"
					} else {
						options.GoEmitter = "missing-emitter"
					}
				case "name":
					pin.Name = "different-component"
				case "version":
					pin.Version = "99.0.0"
				case "digest":
					pin.SHA256 = strings.Repeat("f", 64)
				case "missing released pin":
					project.Toolchain.Status, pin = "released", Tool{}
				}
				project.Toolchain.Tools.Normalizer = pins["normalizer"]
				project.Toolchain.Tools.Emitters = map[string]Tool{"go": pins["go-emitter"]}
				if component == "normalizer" {
					project.Toolchain.Tools.Normalizer = pin
				} else {
					project.Toolchain.Tools.Emitters["go"] = pin
				}
				if got, err := NewPipeline(context.Background(), &project, options); err == nil {
					got.Close()
					t.Fatal("invalid library selection accepted")
				}
				if _, err := os.Stat(options.WorkDir); !os.IsNotExist(err) {
					t.Fatal("rejected selection created work files")
				}
			})
		}
	}
	p.Toolchain.Status = "released"
	p.Toolchain.Tools.Normalizer, p.Toolchain.Tools.Emitters = pins["normalizer"], map[string]Tool{"go": pins["go-emitter"]}
	if accepted, err := NewPipeline(context.Background(), p, o); err != nil {
		t.Fatalf("matching host pins rejected: %v", err)
	} else {
		accepted.Close()
	}
}

func TestGoLibrariesHonorCancellation(t *testing.T) {
	p, o := goLibraryProject(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	pipeline, err := NewPipeline(ctx, p, o)
	if err != nil {
		t.Fatal(err)
	}
	defer pipeline.Close()
	cancel()
	doc := &Document{}
	if err := pipeline.Normalize(doc); !errors.Is(err, context.Canceled) || doc.Model.APIVersion != "" {
		t.Fatalf("canceled normalization changed the model: %v", err)
	}
	if err := pipeline.emit(&BuiltTarget{Target: Target{Language: "go"}}); !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled emission: %v", err)
	}
	if pipeline.work != "" {
		t.Fatal("canceled operation created work files")
	}
}

func TestGoLibrariesPythonOnlyCatalogDoesNotRequireGoEmitter(t *testing.T) {
	p, o := testProject(t, "python")
	o.UseGoLibraries = true
	pipeline, err := NewPipeline(context.Background(), p, o)
	if err != nil {
		t.Fatal(err)
	}
	defer pipeline.Close()
	p.Toolchain.Status = "released"
	p.Toolchain.Tools.Normalizer = pipeline.identities["normalizer"]
	selected, err := NewPipeline(context.Background(), p, o)
	if err != nil {
		t.Fatalf("Python-only catalog required a Go emitter pin: %v", err)
	}
	defer selected.Close()
	if _, selectedGo := selected.tools["go-emitter"]; selectedGo {
		t.Fatal("Python-only catalog selected a Go emitter")
	}
}

package orchestrator

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestDefaultOptionsRetainStandaloneToolSelection(t *testing.T) {
	for key, value := range map[string]string{
		"RC_BINDINGS_GO": "/tools/go", "RC_BINDINGS_PYTHON": "/tools/python",
		"RC_BINDINGS_NORMALIZER": "/tools/normalizer", "RC_BINDINGS_GO_EMITTER": "/tools/emitter",
		"RC_GO_PROFILER_BIN": "/tools/go-profiler", "RC_PYTHON_PROFILER_BIN": "/tools/python-profiler",
		"RC_PYTHON_PROFILER_ARTIFACT": "/tools/profiler.whl",
	} {
		t.Setenv(key, value)
	}
	o := DefaultOptions()
	if o.Go != "/tools/go" || o.Python != "/tools/python" || o.Normalizer != "/tools/normalizer" ||
		o.GoEmitter != "/tools/emitter" || o.GoProfiler != "/tools/go-profiler" ||
		o.PythonProfiler != "/tools/python-profiler" || o.PythonProfilerArtifact != "/tools/profiler.whl" {
		t.Fatalf("standalone defaults: %+v", o)
	}
	t.Setenv("RC_BINDINGS_GO", "")
	t.Setenv("RC_BINDINGS_PYTHON", "")
	t.Setenv("RC_GO_PROFILER_BIN", "")
	t.Setenv("RC_PYTHON_PROFILER_BIN", "")
	o = DefaultOptions()
	if o.Go != "go" || o.Python != "python3" || o.GoProfiler != "go-rc-profiler" || o.PythonProfiler != "runtimeconditions-python-profiler" {
		t.Fatalf("native command defaults: %+v", o)
	}
}

func TestExecuteResolveAndNormalizeMatchStandalone(t *testing.T) {
	p, defaults := testProject(t, "go")
	nested := filepath.Join(p.Root, "nested working directory")
	if err := os.Mkdir(nested, 0755); err != nil {
		t.Fatal(err)
	}
	core := filepath.Join(p.Root, "core.yaml")
	if err := os.WriteFile(core, []byte("$id: https://runtimeconditions.io/schemas/profile/0.2.0/runtimeconditions.profile.schema.yaml\ntype: object\n"), 0644); err != nil {
		t.Fatal(err)
	}
	normalizer := filepath.Join(t.TempDir(), "normalizer")
	command := exec.Command(defaults.Go, "build", "-trimpath", "-buildvcs=false", "-o", normalizer, "./cmd/rc-binding-model")
	command.Dir = filepath.Join(p.ToolingDirectory, "normalizer")
	if data, err := command.CombinedOutput(); err != nil {
		t.Fatalf("build normalizer: %v\n%s", err, data)
	}
	relativeNormalizer, err := filepath.Rel(nested, normalizer)
	if err != nil {
		t.Fatal(err)
	}
	processCWD, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"resolve", "normalize"} {
		t.Run(name, func(t *testing.T) {
			o := defaults
			o.Packages, o.ToolchainLock = "../packages.yaml", "../toolchain.lock.yaml"
			o.CoreSchema, o.Normalizer = "../core.yaml", relativeNormalizer
			o.CatalogRoots = []string{"../catalog"}
			o.Overrides = []string{p.Catalog.Packages["new-channel"].RootExtension + "=../catalog/" + extensionName}
			o.Targets = []string{"new-channel:go"}
			o.DependencyLockOutput = "../" + name + " API lock.yaml"
			apiFile, cliFile := filepath.Join(p.Root, name+" API.yaml"), filepath.Join(p.Root, name+" CLI.yaml")
			cliLock := filepath.Join(p.Root, name+" CLI lock.yaml")
			args := []string{"bindings", name, "--packages", p.PackagesPath, "--toolchain-lock", p.ToolchainPath,
				"--tooling-dir", p.ToolingDirectory, "--catalog-root", filepath.Join(p.Root, "catalog"),
				"--target", "new-channel:go", "--go", o.Go,
				"--normalizer", normalizer, "--core-schema", core, "--dependency-lock-output", cliLock}
			args = append(args, "--extension-override", p.Catalog.Packages["new-channel"].RootExtension+"="+filepath.Join(p.Root, "catalog", extensionName))
			if name == "resolve" {
				o.ClosureOutput = "../" + name + " API.yaml"
				args = append(args, "--closure-output", cliFile)
			} else {
				o.Output = "../" + name + " API.yaml"
				args = append(args, "--output", cliFile)
			}
			var apiOut, apiErr, cliOut, cliErr bytes.Buffer
			if err := Execute(context.Background(), nested, name, o, &apiOut, &apiErr); err != nil {
				t.Fatal(err)
			}
			if err := Run(context.Background(), args, &cliOut, &cliErr); err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(apiOut.Bytes(), cliOut.Bytes()) || !bytes.Equal(apiErr.Bytes(), cliErr.Bytes()) {
				t.Fatalf("API and standalone streams differ\nAPI: %s\nCLI: %s", apiOut.Bytes(), cliOut.Bytes())
			}
			if !strings.Contains(apiOut.String(), "future.channel") {
				t.Fatal("resolved vocabulary missing from YAML")
			}
			for _, pair := range [][2]string{{apiFile, cliFile}, {filepath.Join(nested, o.DependencyLockOutput), cliLock}} {
				first, err := os.ReadFile(pair[0])
				if err != nil {
					t.Fatal(err)
				}
				second, err := os.ReadFile(pair[1])
				if err != nil || !bytes.Equal(first, second) {
					t.Fatalf("API and standalone files differ: %v", err)
				}
			}
			if o.CatalogRoots[0] != "../catalog" || o.CoreSchema != "../core.yaml" || o.Packages != "../packages.yaml" {
				t.Fatalf("Execute mutated caller options: %+v", o)
			}
			if !strings.Contains(o.Overrides[0], "=../catalog/") || o.Normalizer != relativeNormalizer {
				t.Fatalf("Execute mutated caller tool/override paths: %+v", o)
			}
		})
	}
	if current, err := os.Getwd(); err != nil || current != processCWD {
		t.Fatalf("process directory changed: %s %v", current, err)
	}
	if _, err := os.Stat(filepath.Join(p.Root, "bindings")); !os.IsNotExist(err) {
		t.Fatal("resolve/normalize created committed binding trees")
	}
}

func TestExecuteValidationMatchesStandalone(t *testing.T) {
	p, defaults := testProject(t, "go")
	directory := filepath.Join(p.Root, "keep")
	if err := os.Mkdir(directory, 0755); err != nil {
		t.Fatal(err)
	}
	sentinel := filepath.Join(directory, "existing.yaml")
	if err := os.WriteFile(sentinel, []byte("preserve existing bytes\n"), 0644); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ name, operation, flag, path, want string }{
		{"existing file", "resolve", "--closure-output", sentinel, "output must be a new file"},
		{"nonempty directory", "generate", "--output", directory, "output must be new or empty"},
		{"committed source", "resolve", "--closure-output", filepath.Join(p.Root, "bindings", "forbidden.yaml"), "explicit outputs must be outside committed bindings"},
		{"duplicate targets", "resolve", "--target", "new-channel:go", "duplicate target new-channel:go"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			o := defaults
			o.Packages, o.ToolchainLock = p.PackagesPath, p.ToolchainPath
			if tc.flag == "--output" {
				o.Output = tc.path
			} else if tc.flag == "--target" {
				o.Targets = []string{tc.path, tc.path}
			} else {
				o.ClosureOutput = tc.path
			}
			var apiOut, apiErr, cliOut, cliErr bytes.Buffer
			apiResult := Execute(context.Background(), p.Root, tc.operation, o, &apiOut, &apiErr)
			args := []string{"bindings", tc.operation, "--packages", p.PackagesPath,
				"--toolchain-lock", p.ToolchainPath, "--tooling-dir", p.ToolingDirectory, tc.flag, tc.path}
			if tc.flag == "--target" {
				args = append(args, tc.flag, tc.path)
			}
			cliResult := Run(context.Background(), args, &cliOut, &cliErr)
			if apiResult == nil || cliResult == nil || apiResult.Error() != cliResult.Error() || !strings.Contains(apiResult.Error(), tc.want) {
				t.Fatalf("API error %v; standalone error %v; want %s", apiResult, cliResult, tc.want)
			}
			if apiOut.Len() != 0 || cliOut.Len() != 0 || !bytes.Equal(apiErr.Bytes(), cliErr.Bytes()) {
				t.Fatal("output validation changed streams")
			}
			if data, err := os.ReadFile(sentinel); err != nil || string(data) != "preserve existing bytes\n" {
				t.Fatalf("existing output changed: %s %v", data, err)
			}
		})
	}
}

func TestExecuteRejectsInvalidRequestsBeforeDiscovery(t *testing.T) {
	root := t.TempDir()
	for _, tc := range []struct{ cwd, operation, want string }{
		{root, "unknown", "unknown bindings command"},
		{"relative", "resolve", "working directory must be absolute"},
		{root, "generate", "generate requires --output"},
		{root, "package", "package requires --output"},
	} {
		err := Execute(context.Background(), tc.cwd, tc.operation, DefaultOptions(), io.Discard, io.Discard)
		if err == nil || !strings.Contains(err.Error(), tc.want) {
			t.Fatalf("%s: %v; want %s", tc.operation, err, tc.want)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := Execute(ctx, root, "resolve", DefaultOptions(), io.Discard, io.Discard); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation: %v", err)
	}
	if entries, err := os.ReadDir(root); err != nil || len(entries) != 0 {
		t.Fatalf("invalid requests created files: %v %v", entries, err)
	}
}

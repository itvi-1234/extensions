package orchestrator

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

type repeated []string

func (r *repeated) String() string         { return strings.Join(*r, ",") }
func (r *repeated) Set(value string) error { *r = append(*r, value); return nil }

// Options contains operation inputs. Use DefaultOptions for native tool defaults.
type Options struct {
	Packages, ToolchainLock, Cache, WorkDir, ToolingDir                                               string
	Output, Input, Report, ClosureOutput, DependencyLockOutput, DependencyLock                        string
	CoreSchema, Go, Python, GoEmitter, Normalizer, GoProfiler, PythonProfiler, PythonProfilerArtifact string
	Targets, ExtensionRoots, Overrides, CatalogRoots                                                  repeated
}

var supportedOperations = map[string]bool{"resolve": true, "normalize": true, "generate": true, "verify": true, "package": true, "plan-release": true, "check": true, "update": true}

// DefaultOptions returns standalone tool defaults from the current environment.
// Explicit overrides, including empty values, may be applied before Execute.
func DefaultOptions() Options {
	return Options{
		Go: envOr("RC_BINDINGS_GO", "go"), Python: envOr("RC_BINDINGS_PYTHON", "python3"),
		Normalizer: os.Getenv("RC_BINDINGS_NORMALIZER"), GoEmitter: os.Getenv("RC_BINDINGS_GO_EMITTER"),
		GoProfiler:             envOr("RC_GO_PROFILER_BIN", "go-rc-profiler"),
		PythonProfiler:         envOr("RC_PYTHON_PROFILER_BIN", "runtimeconditions-python-profiler"),
		PythonProfilerArtifact: os.Getenv("RC_PYTHON_PROFILER_ARTIFACT"),
	}
}

// Run parses standalone command arguments and delegates execution to Execute.
func Run(ctx context.Context, args []string, stdout, stderr io.Writer) error {
	if len(args) == 0 || args[0] == "--help" || args[0] == "-h" {
		fmt.Fprintln(stdout, "Usage: rc bindings <resolve|normalize|generate|verify|package|plan-release|check|update> [flags]")
		return nil
	}
	if args[0] == "--version" {
		fmt.Fprintln(stdout, "rc", Version)
		return nil
	}
	if args[0] != "bindings" || len(args) < 2 {
		return fmt.Errorf("usage: rc bindings <command> [flags]")
	}
	name := args[1]
	if name == "--help" || name == "-h" {
		fmt.Fprintln(stdout, "Commands: resolve normalize generate verify package plan-release check update")
		return nil
	}
	if !supportedOperations[name] {
		return fmt.Errorf("unknown bindings command %q", name)
	}
	o := DefaultOptions()
	f := flag.NewFlagSet("rc bindings "+name, flag.ContinueOnError)
	f.SetOutput(stderr)
	f.StringVar(&o.Packages, "packages", "", "package catalog path")
	f.StringVar(&o.ToolchainLock, "toolchain-lock", "", "toolchain lock path")
	f.StringVar(&o.Cache, "cache", "", "explicit persistent content-addressed extension cache")
	f.StringVar(&o.WorkDir, "work-dir", "", "retain required intermediates in this directory")
	f.StringVar(&o.ToolingDir, "tooling-dir", "", "tool installation containing schemas and development tools")
	f.Var(&o.Targets, "target", "package-key:language; repeatable, defaults to all targets")
	resolution := name == "resolve" || name == "normalize" || name == "generate" || name == "package" || name == "check" || name == "update"
	if resolution {
		f.Var(&o.ExtensionRoots, "extension-root", "exact root extension identifier; repeatable, replaces configured roots")
		f.Var(&o.Overrides, "extension-override", "exact identifier=local-path; repeatable, development only")
		f.Var(&o.CatalogRoots, "catalog-root", "explicit local definition catalog; repeatable")
		f.StringVar(&o.DependencyLock, "dependency-lock", "", "existing exact dependency lock")
	}
	if name == "resolve" {
		f.StringVar(&o.ClosureOutput, "closure-output", "", "write semantic closure here")
	}
	if name == "resolve" || name == "normalize" {
		f.StringVar(&o.DependencyLockOutput, "dependency-lock-output", "", "write resolved dependency lock here")
	}
	if name == "normalize" || name == "generate" || name == "package" || name == "plan-release" {
		f.StringVar(&o.Output, "output", "", "requested final output file or directory")
	}
	if name == "verify" {
		f.StringVar(&o.Input, "input", "", "generated tree root; defaults to committed targets")
	}
	if name == "verify" || name == "check" {
		f.StringVar(&o.Report, "report", "", "write the YAML verification summary here")
	}
	f.StringVar(&o.CoreSchema, "core-schema", "", "explicit core schema file for local development")
	f.StringVar(&o.Go, "go", o.Go, "native Go command")
	f.StringVar(&o.Python, "python", o.Python, "native Python interpreter")
	f.StringVar(&o.Normalizer, "normalizer", o.Normalizer, "installed locked normalizer; development defaults to workspace build")
	f.StringVar(&o.GoEmitter, "go-emitter", o.GoEmitter, "installed locked Go emitter; development defaults to workspace build")
	f.StringVar(&o.GoProfiler, "go-profiler", o.GoProfiler, "independently installed Go profiler CLI")
	f.StringVar(&o.PythonProfiler, "python-profiler", o.PythonProfiler, "independently installed Python profiler CLI")
	f.StringVar(&o.PythonProfilerArtifact, "python-profiler-artifact", o.PythonProfilerArtifact, "installed Python profiler wheel for artifact identity verification")
	if err := f.Parse(args[2:]); err != nil {
		if err == flag.ErrHelp {
			return nil
		}
		return err
	}
	if f.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments: %s", strings.Join(f.Args(), " "))
	}
	cwd, err := os.Getwd()
	if err != nil {
		return err
	}
	return Execute(ctx, cwd, name, o, stdout, stderr)
}

func writeSummary(name string, o Options, summary VerificationSummary, result error, stdout, stderr io.Writer) error {
	data, marshalErr := yaml.Marshal(summary)
	if marshalErr != nil {
		return marshalErr
	}
	if _, writeErr := stdout.Write(data); writeErr != nil {
		return writeErr
	}
	if o.Report != "" {
		if writeErr := writeNewFile(o.Report, data); writeErr != nil {
			return writeErr
		}
	}
	fmt.Fprintf(stderr, "bindings %s: %s (%d targets)\n", name, summary.Status, len(summary.Targets))
	return result
}
func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
func writeNewFile(path string, data []byte) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return err
	}
	_, err = file.Write(data)
	closeErr := file.Close()
	if err != nil {
		return err
	}
	return closeErr
}
func prepareEmptyDirectory(path string) error {
	if err := validateEmptyDirectory(path); err != nil {
		return err
	}
	return os.MkdirAll(path, 0755)
}
func validateEmptyDirectory(path string) error {
	if err := rejectSymlinkPath(path); err != nil {
		return err
	}
	if info, err := os.Stat(path); err == nil {
		if !info.IsDir() {
			return fmt.Errorf("output is not a directory: %s", path)
		}
		entries, err := os.ReadDir(path)
		if err != nil {
			return err
		}
		if len(entries) > 0 {
			return fmt.Errorf("output must be new or empty: %s", path)
		}
		return nil
	} else if !os.IsNotExist(err) {
		return err
	}
	return nil
}
func rejectSymlinkPath(path string) error {
	for current := filepath.Clean(path); ; current = filepath.Dir(current) {
		info, err := os.Lstat(current)
		if err == nil && info.Mode()&os.ModeSymlink != 0 && current != "/var" && current != "/tmp" {
			return fmt.Errorf("symbolic-link path rejected: %s", current)
		}
		if err != nil && !os.IsNotExist(err) {
			return err
		}
		if filepath.Dir(current) == current {
			return nil
		}
	}
}

package orchestrator

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// Execute runs one binding operation without parsing arguments or changing the
// process working directory. cwd must be absolute; relative option paths resolve
// against it. Initialize options with DefaultOptions to use standalone tooling
// defaults, then apply caller overrides. Writers must be non-nil.
func Execute(ctx context.Context, cwd, name string, o Options, stdout, stderr io.Writer) error {
	if !supportedOperations[name] {
		return fmt.Errorf("unknown bindings command %q", name)
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if !filepath.IsAbs(cwd) {
		return fmt.Errorf("working directory must be absolute")
	}
	if (name == "generate" || name == "package") && o.Output == "" {
		return fmt.Errorf("%s requires --output", name)
	}
	// Options is passed by value; copy the slice before resolving its paths.
	o.CatalogRoots = append(repeated(nil), o.CatalogRoots...)
	o.Overrides = append(repeated(nil), o.Overrides...)
	for i, entry := range o.Overrides {
		if key, path, ok := strings.Cut(entry, "="); ok && path != "" {
			o.Overrides[i] = key + "=" + absolute(cwd, path)
		}
	}
	for _, ptr := range []*string{&o.Go, &o.Python, &o.Normalizer, &o.GoEmitter, &o.GoProfiler, &o.PythonProfiler} {
		if strings.ContainsAny(*ptr, "/\\") {
			*ptr = absolute(cwd, *ptr)
		}
	}
	for _, ptr := range []*string{&o.Cache, &o.WorkDir, &o.Output, &o.Input, &o.Report, &o.ClosureOutput, &o.DependencyLockOutput, &o.DependencyLock, &o.CoreSchema, &o.PythonProfilerArtifact} {
		if *ptr != "" {
			*ptr = absolute(cwd, *ptr)
		}
	}
	for i, dir := range o.CatalogRoots {
		o.CatalogRoots[i] = absolute(cwd, dir)
	}
	project, err := DiscoverProject(cwd, o.Packages, o.ToolchainLock, o.ToolingDir)
	if err != nil {
		return err
	}
	pipeline, err := NewPipeline(ctx, project, o)
	if err != nil {
		return err
	}
	defer pipeline.Close()
	outputs := []string{o.Output, o.Report, o.ClosureOutput, o.DependencyLockOutput}
	seenOutputs := map[string]bool{}
	for _, path := range outputs {
		if path == "" {
			continue
		}
		if err = rejectSymlinkPath(path); err != nil {
			return err
		}
		if within(filepath.Join(project.RepositoryRoot, "bindings"), path) {
			return fmt.Errorf("explicit outputs must be outside committed bindings; use update to synchronize package source")
		}
		if seenOutputs[path] {
			return fmt.Errorf("output paths must be different: %s", path)
		}
		seenOutputs[path] = true
		if name != "generate" && name != "package" {
			if _, statErr := os.Lstat(path); !os.IsNotExist(statErr) {
				return fmt.Errorf("output must be a new file: %s", path)
			}
		}
	}
	plan, err := project.SelectTargets(o.Targets)
	if err != nil {
		return err
	}
	if len(o.ExtensionRoots) > 0 && name != "resolve" && name != "normalize" {
		roots := map[string]bool{}
		for _, root := range o.ExtensionRoots {
			roots[root] = true
		}
		filtered := BuildPlan{Targets: []Target{}}
		foundRoots := map[string]bool{}
		for _, target := range plan.Targets {
			if roots[target.Set.RootExtension] {
				filtered.Targets = append(filtered.Targets, target)
				foundRoots[target.Set.RootExtension] = true
			}
		}
		for root := range foundRoots {
			delete(roots, root)
		}
		if len(roots) != 0 {
			return fmt.Errorf("extension roots require package delivery metadata in the selected catalog targets: %s", strings.Join(sortedKeys(roots), ", "))
		}
		plan = filtered
	}
	switch name {
	case "resolve", "normalize":
		documents, err := pipeline.Resolve(plan)
		if err != nil {
			return err
		}
		for i, doc := range documents {
			if i > 0 {
				fmt.Fprintln(stdout, "---")
			}
			var data []byte
			if name == "resolve" {
				data, err = yaml.Marshal(doc.SemanticClosure())
			} else {
				if err = pipeline.Normalize(doc); err == nil {
					data, err = doc.ModelYAML()
				}
			}
			if err != nil {
				return err
			}
			if _, err = stdout.Write(data); err != nil {
				return err
			}
			if name == "resolve" {
				lock, err := doc.LockYAML()
				if err != nil {
					return err
				}
				fmt.Fprintln(stdout, "---")
				if _, err = stdout.Write(lock); err != nil {
					return err
				}
			}
		}
		if o.ClosureOutput != "" || o.DependencyLockOutput != "" || o.Output != "" {
			if len(documents) != 1 {
				return fmt.Errorf("file outputs require one extension root; use --extension-root or --target")
			}
			doc := documents[0]
			if o.ClosureOutput != "" {
				data, _ := yaml.Marshal(doc.SemanticClosure())
				if err = writeNewFile(o.ClosureOutput, data); err != nil {
					return err
				}
			}
			if o.Output != "" {
				data, err := doc.ModelYAML()
				if err != nil {
					return err
				}
				if err = writeNewFile(o.Output, data); err != nil {
					return err
				}
			}
			if o.DependencyLockOutput != "" {
				data, err := doc.LockYAML()
				if err != nil {
					return err
				}
				if err = writeNewFile(o.DependencyLockOutput, data); err != nil {
					return err
				}
			}
		}
		return nil
	case "generate":
		if err = validateEmptyDirectory(o.Output); err != nil {
			return err
		}
		build, err := pipeline.Generate(plan)
		if err != nil {
			return err
		}
		if err = prepareEmptyDirectory(o.Output); err != nil {
			return err
		}
		return build.CopySelected(o.Output)
	case "plan-release":
		release, err := pipeline.PlanRelease(plan)
		if err != nil {
			return err
		}
		data, err := yaml.Marshal(release)
		if err != nil {
			return err
		}
		if _, err = stdout.Write(data); err != nil {
			return err
		}
		if o.Output != "" {
			return writeNewFile(o.Output, data)
		}
		return nil
	case "verify", "check", "package", "update":
		var build *Build
		if name == "verify" {
			build, err = pipeline.LoadBuild(plan, o.Input)
		} else {
			build, err = pipeline.Generate(plan)
		}
		if err != nil {
			failure := VerificationSummary{Status: "failed", Targets: []TargetResult{}}
			failure.Fail("build", err)
			return writeSummary(name, o, failure, err, stdout, stderr)
		}
		summary, err := pipeline.Verify(build)
		if err == nil && (name == "check" || name == "package") {
			err = build.CompareCommitted()
			if err != nil {
				summary.Fail("committed-source", err)
			}
		}
		if err == nil && name == "update" {
			err = build.Update()
			if err != nil {
				summary.Fail("update", err)
			}
		}
		if err == nil && name == "package" {
			committed, loadErr := pipeline.LoadBuild(plan, "")
			if loadErr != nil {
				err = loadErr
			} else {
				_, err = pipeline.Verify(committed)
				if err == nil {
					err = pipeline.Package(committed, o.Output)
				}
			}
			if err != nil {
				summary.Fail("package", err)
			}
		}
		return writeSummary(name, o, summary, err, stdout, stderr)
	}
	return fmt.Errorf("unhandled bindings command %s", name)
}

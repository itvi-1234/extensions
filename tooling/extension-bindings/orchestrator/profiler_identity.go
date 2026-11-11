package orchestrator

import (
	"fmt"
	"regexp"
)

const linkedGoProfilerModule = "github.com/runtimeconditions/go-rc-profiler"
const linkedGoProfilerKind = "go-module"

var profilerArtifactDigest = regexp.MustCompile(`^[0-9a-f]{64}$`)
var profilerArtifactURL = regexp.MustCompile(`^https://[^\s]+$`)
var profilerModuleSum = regexp.MustCompile(`^h1:[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$`)
var profilerModuleVersion = regexp.MustCompile(`^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(\+incompatible)?$`)

// ProfilerIdentity describes either a standalone artifact or the linked Go
// profiler module. Standalone identities omit Kind and retain the legacy
// name/version/sha256 representation. Linked identities require kind: go-module
// and module/moduleSum, and cannot contain sha256 or artifactUrl.
// These helpers define the contract; pipeline selection is integrated separately.
type ProfilerIdentity struct {
	Name        string `json:"name" yaml:"name"`
	Version     string `json:"version" yaml:"version"`
	SHA256      string `json:"sha256,omitempty" yaml:"sha256,omitempty"`
	ArtifactURL string `json:"artifactUrl,omitempty" yaml:"artifactUrl,omitempty"`
	Kind        string `json:"kind,omitempty" yaml:"kind,omitempty"`
	Module      string `json:"module,omitempty" yaml:"module,omitempty"`
	ModuleSum   string `json:"moduleSum,omitempty" yaml:"moduleSum,omitempty"`
}

// NewStandaloneProfilerIdentity validates the existing artifact identity without
// changing its version or digest. ArtifactURL is optional lock retrieval data.
func NewStandaloneProfilerIdentity(tool Tool) (ProfilerIdentity, error) {
	identity := ProfilerIdentity{Name: tool.Name, Version: tool.Version, SHA256: tool.SHA256, ArtifactURL: tool.ArtifactURL}
	return identity, identity.Validate()
}

// NewLinkedGoProfilerIdentity validates an exact module version and Go h1
// dependency checksum supplied by the host's verified build metadata. It does
// not inspect an executable, resolve a module, or install any tooling.
func NewLinkedGoProfilerIdentity(version, moduleSum string) (ProfilerIdentity, error) {
	identity := ProfilerIdentity{
		Name: "go-rc-profiler", Version: version, Kind: linkedGoProfilerKind,
		Module: linkedGoProfilerModule, ModuleSum: moduleSum,
	}
	return identity, identity.Validate()
}

// Validate checks a complete identity, rejecting mixed artifact/module fields.
// Validate document schemas before decoding to reject unknown input fields too.
func (identity ProfilerIdentity) Validate() error {
	if identity.Name == "" || identity.Version == "" {
		return fmt.Errorf("profiler identity requires name and version")
	}
	switch identity.Kind {
	case "":
		if identity.Module != "" || identity.ModuleSum != "" {
			return fmt.Errorf("standalone profiler identity cannot contain module fields")
		}
		if !profilerArtifactDigest.MatchString(identity.SHA256) {
			return fmt.Errorf("standalone profiler identity requires a lowercase artifact SHA-256")
		}
		if identity.ArtifactURL != "" && !profilerArtifactURL.MatchString(identity.ArtifactURL) {
			return fmt.Errorf("profiler artifactUrl must be an HTTPS URL without whitespace")
		}
	case linkedGoProfilerKind:
		if identity.SHA256 != "" || identity.ArtifactURL != "" {
			return fmt.Errorf("linked profiler identity cannot contain artifact fields")
		}
		if identity.Name != "go-rc-profiler" || identity.Module != linkedGoProfilerModule {
			return fmt.Errorf("linked profiler identity requires the Go profiler name and module path")
		}
		if !profilerModuleVersion.MatchString(identity.Version) {
			return fmt.Errorf("linked profiler identity requires an exact Go module version")
		}
		if !profilerModuleSum.MatchString(identity.ModuleSum) {
			return fmt.Errorf("linked profiler identity requires a canonical Go h1 dependency checksum")
		}
	default:
		return fmt.Errorf("unknown profiler identity kind %q", identity.Kind)
	}
	return nil
}

// Match requires the selected profiler to have exactly the identity pinned by
// the receiver. Retrieval URLs do not identify artifact contents. Neither an
// incomplete lock nor a different identity kind can satisfy this comparison.
func (expected ProfilerIdentity) Match(selected ProfilerIdentity) error {
	if err := expected.Validate(); err != nil {
		return fmt.Errorf("invalid locked profiler identity: %w", err)
	}
	if err := selected.Validate(); err != nil {
		return fmt.Errorf("invalid selected profiler identity: %w", err)
	}
	if expected.Kind != selected.Kind {
		return fmt.Errorf("profiler identity kind differs from lock")
	}
	if expected.Name != selected.Name {
		return fmt.Errorf("profiler name differs from lock")
	}
	if expected.Version != selected.Version {
		return fmt.Errorf("profiler version differs from lock")
	}
	if expected.SHA256 != selected.SHA256 {
		return fmt.Errorf("profiler artifact digest differs from lock")
	}
	if expected.Module != selected.Module || expected.ModuleSum != selected.ModuleSum {
		return fmt.Errorf("profiler module identity differs from lock")
	}
	return nil
}

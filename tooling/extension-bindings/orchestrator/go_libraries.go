package orchestrator

import (
	"crypto/sha256"
	"fmt"
	"io"
	"os"

	goemitter "github.com/runtimeconditions/extensions/tooling/extension-bindings/emitters/go"
	"github.com/runtimeconditions/extensions/tooling/extension-bindings/normalizer"
)

// goLibraryTool identifies the artifact executing a linked component, rather
// than a separately built tool or a module checksum. Its path is never executed.
func (p *Pipeline) goLibraryTool(key string) (string, Tool, error) {
	if err := p.Context.Err(); err != nil {
		return "", Tool{}, err
	}
	var identity, expected Tool
	switch key {
	case "normalizer":
		identity = Tool{Name: normalizer.NormalizerName, Version: normalizer.NormalizerVersion}
		expected = p.Project.Toolchain.Tools.Normalizer
	case "go-emitter":
		identity = Tool{Name: goemitter.EmitterName, Version: goemitter.EmitterVersion}
		expected = p.Project.Toolchain.Tools.Emitters["go"]
	default:
		return "", Tool{}, fmt.Errorf("unknown Go library component %s", key)
	}
	path, cached := p.tools[key]
	if cached {
		identity.SHA256 = p.identities[key].SHA256
	} else {
		var err error
		path, err = os.Executable()
		if err != nil {
			return "", Tool{}, err
		}
		artifact, err := os.Open(path)
		if err != nil {
			return "", Tool{}, err
		}
		digest := sha256.New()
		_, err = io.Copy(digest, artifact)
		closeErr := artifact.Close()
		if err != nil {
			return "", Tool{}, err
		}
		if closeErr != nil {
			return "", Tool{}, closeErr
		}
		identity.SHA256 = fmt.Sprintf("%x", digest.Sum(nil))
	}
	if p.Project.Toolchain.Status == "released" && expected.SHA256 == "" {
		return "", Tool{}, fmt.Errorf("%s: released lock lacks host executable identity", key)
	}
	if expected.SHA256 != "" && (expected.Name != identity.Name || expected.Version != identity.Version || expected.SHA256 != identity.SHA256) {
		return "", Tool{}, fmt.Errorf("%s host executable identity differs from toolchain lock", key)
	}
	if err := p.Context.Err(); err != nil {
		return "", Tool{}, err
	}
	p.tools[key], p.identities[key] = path, identity
	return path, identity, nil
}

func (p *Pipeline) normalizeGoLibrary(doc *Document) error {
	_, identity, err := p.tool("normalizer")
	if err != nil {
		return err
	}
	_, core, err := p.core(doc.CoreVersion)
	if err != nil {
		return err
	}
	if err := p.Context.Err(); err != nil {
		return err
	}
	model, err := normalizer.Normalize(doc.Closure, doc.Lock, p.Project.Schemas, normalizer.NormalizeConfig{
		CoreProfileSchema: core,
		Normalizer:        normalizer.ToolIdentity{Name: identity.Name, Version: identity.Version, SHA256: identity.SHA256},
	})
	if err != nil {
		return err
	}
	if err := p.Context.Err(); err != nil {
		return err
	}
	doc.Model = model
	return nil
}

func (p *Pipeline) emitGoLibrary(bt *BuiltTarget) error {
	if _, _, err := p.tool("go-emitter"); err != nil {
		return err
	}
	modelPath, targetPath, err := p.emitterInputs(bt)
	if err != nil {
		return err
	}
	// Use the emitter's own strict loaders, matching its standalone entry point.
	model, err := goemitter.LoadModel(modelPath)
	if err != nil {
		return err
	}
	target, err := goemitter.LoadPackageTarget(targetPath)
	if err != nil {
		return err
	}
	if err := p.Context.Err(); err != nil {
		return err
	}
	if err := goemitter.Emit(model, target, bt.Directory); err != nil {
		return err
	}
	return p.Context.Err()
}

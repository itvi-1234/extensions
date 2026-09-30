package goemitter

import (
	"context"
	"encoding/json"
	"errors"
	"go/ast"
	"go/parser"
	"go/token"
	"go/types"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/runtimeconditions/extensions/tooling/extension-bindings/normalizer"
	"gopkg.in/yaml.v3"
)

func TestGoNamingRules(t *testing.T) {
	tests := map[string]struct {
		source string
		want   string
	}{
		"ordinary Pascal case": {"HTTPServer2URL", "HttpServer2Url"},
		"leading digit":        {"9patch", "9Patch"},
		"unicode letters":      {"café", "Café"},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			if actual := pascal(goTokens(test.source)); actual != test.want {
				t.Fatalf("pascal(goTokens(%q)) = %q, want %q", test.source, actual, test.want)
			}
		})
	}
}

func TestGoRejectsLeadingDigitIdentifiers(t *testing.T) {
	if name := pascal(goTokens("9patch")); name != "9Patch" {
		t.Fatalf("pascal(goTokens(%q)) = %q, want 9Patch", "9patch", name)
	}
	if token.IsIdentifier("9Patch") {
		t.Fatal("Go accepted an identifier beginning with a digit")
	}
	err := validateGoIdentifier("9Patch", &symbolRequest{coordinate: "condition-field:9patch", category: "field"})
	if err == nil || !strings.Contains(err.Error(), "RCG2011") {
		t.Fatalf("leading-digit identifier error = %v, want RCG2011", err)
	}
}

func TestOptionalEnumFieldsUsePointers(t *testing.T) {
	fixture := filepath.Join("testdata", "optional-enum-fields")
	model := normalizeFixture(t, fixture, "urn:runtimeconditions:go-fixture:optional-enum-fields")
	target, err := LoadPackageTarget(filepath.Join(fixture, "package-target.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(t.TempDir(), "generated")
	if err := Emit(model, target, output); err != nil {
		t.Fatal(err)
	}

	file, err := parser.ParseFile(token.NewFileSet(), filepath.Join(output, generatedGoFile), nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	settings := findStructType(t, file, "Settings")
	fields := map[string]ast.Expr{}
	for _, field := range settings.Fields.List {
		for _, name := range field.Names {
			fields[name.Name] = field.Type
		}
	}
	if _, ok := fields["Mode"].(*ast.StarExpr); !ok {
		t.Errorf("optional enum field Mode has type %T; want a pointer", fields["Mode"])
	}
	if _, ok := fields["RequiredMode"].(*ast.StarExpr); ok {
		t.Errorf("required enum field RequiredMode has pointer type %T", fields["RequiredMode"])
	}
}

func TestMarkerMethodsUseOwnerCoordinate(t *testing.T) {
	fixture := filepath.Join("testdata", "marker-owner-coordinate")
	const ownerA = "urn:runtimeconditions:go-fixture:marker-owner-a"
	const ownerB = "urn:runtimeconditions:go-fixture:marker-owner-b"
	modelA := normalizeFixture(t, fixture, ownerA)
	modelB := normalizeFixture(t, fixture, ownerB)
	targetA, err := LoadPackageTarget(filepath.Join(fixture, "package-target-owner-a.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	targetB, err := LoadPackageTarget(filepath.Join(fixture, "package-target-owner-b.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	targetACopy := targetA
	targetACopy.PackageKey = "marker-owner-a-copy"
	targetACopy.ModulePath = "example.com/runtimeconditions/marker-owner-a-copy"
	targetACopy.PackageName = "markerownercopy"

	outputA := filepath.Join(t.TempDir(), "owner-a")
	outputB := filepath.Join(t.TempDir(), "owner-b")
	outputACopy := filepath.Join(t.TempDir(), "owner-a-copy")
	for _, item := range []struct {
		model  normalizer.BindingModel
		target PackageTarget
		output string
	}{
		{modelA, targetA, outputA},
		{modelB, targetB, outputB},
		{modelA, targetACopy, outputACopy},
	} {
		if err := Emit(item.model, item.target, item.output); err != nil {
			t.Fatal(err)
		}
	}

	packageA := typeCheckGeneratedPackage(t, outputA, targetA.ModulePath)
	packageB := typeCheckGeneratedPackage(t, outputB, targetB.ModulePath)
	packageACopy := typeCheckGeneratedPackage(t, outputACopy, targetACopy.ModulePath)
	fieldA := packageType(t, packageA, "Zone")
	fieldInterfaceA := packageType(t, packageA, "ServiceField").Underlying().(*types.Interface)
	fieldInterfaceB := packageType(t, packageB, "ServiceField").Underlying().(*types.Interface)
	fieldInterfaceACopy := packageType(t, packageACopy, "ServiceField").Underlying().(*types.Interface)
	if !types.Implements(fieldA, fieldInterfaceA) {
		t.Fatal("owner A field does not implement its own declaration marker")
	}
	if types.Implements(fieldA, fieldInterfaceB) {
		t.Fatal("owner A field unexpectedly implements the distinct owner B marker")
	}
	if !types.Implements(fieldA, fieldInterfaceACopy) {
		t.Fatal("owner A field does not implement the same declaration marker in a second package")
	}
}

func TestLeadingDigitEmissionHasExactDiagnostic(t *testing.T) {
	fixture := filepath.Join("testdata", "negative", "leading-digit")
	model := normalizeFixture(t, fixture, "urn:runtimeconditions:go-fixture:leading-digit")
	target, err := LoadPackageTarget(filepath.Join(fixture, "package-target.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	err = Emit(model, target, filepath.Join(t.TempDir(), "generated"))
	assertExactDiagnostic(t, err, filepath.Join(fixture, "diagnostic.yaml"))
}

func TestEmitterRejectsInvalidInputs(t *testing.T) {
	model := loadExpectedModel(t, "01-owned-kind-interface")
	target := loadTestTarget(t, "01-owned-kind-interface.yaml")
	tests := map[string]func() error{
		"missing model field": func() error {
			changed := model
			changed.RootExtension.ID = ""
			return Emit(changed, target, filepath.Join(t.TempDir(), "output"))
		},
		"unsupported model API": func() error {
			changed := model
			changed.APIVersion = "runtimeconditions.io/binding-model/v2"
			return Emit(changed, target, filepath.Join(t.TempDir(), "output"))
		},
		"unknown structural node": func() error {
			changed := model
			changed.Scopes = append([]normalizer.ScopeModel(nil), model.Scopes...)
			projection := *changed.Scopes[0].Projection
			projection.Kind = "mystery"
			changed.Scopes[0].Projection = &projection
			return Emit(changed, target, filepath.Join(t.TempDir(), "output"))
		},
		"mismatched target": func() error {
			changed := target
			changed.RootExtension = "urn:runtimeconditions:other"
			return Emit(model, changed, filepath.Join(t.TempDir(), "output"))
		},
		"unsupported Go version": func() error {
			changed := target
			changed.MinimumGoVersion = "1.21"
			return Emit(model, changed, filepath.Join(t.TempDir(), "output"))
		},
	}
	for name, run := range tests {
		t.Run(name, func(t *testing.T) {
			if err := run(); err == nil {
				t.Fatal("expected deterministic rejection")
			}
		})
	}

	output := t.TempDir()
	if err := os.WriteFile(filepath.Join(output, "existing"), []byte("occupied"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := Emit(model, target, output); err == nil || !strings.Contains(err.Error(), "output directory must be empty") {
		t.Fatalf("non-empty output error = %v", err)
	}
}

func TestLoadersRejectUnknownFields(t *testing.T) {
	modelData, err := os.ReadFile(expectedModelPath("01-owned-kind-interface"))
	if err != nil {
		t.Fatal(err)
	}
	modelPath := filepath.Join(t.TempDir(), "model.yaml")
	if err := os.WriteFile(modelPath, append(modelData, []byte("unknownField: true\n")...), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadModel(modelPath); err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("unknown model field error = %v", err)
	}

	targetData, err := os.ReadFile(testTargetPath("01-owned-kind-interface.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	targetPath := filepath.Join(t.TempDir(), "target.yaml")
	if err := os.WriteFile(targetPath, append(targetData, []byte("unknownField: true\n")...), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadPackageTarget(targetPath); err == nil || !strings.Contains(err.Error(), "unknown package target field") {
		t.Fatalf("unknown package-target field error = %v", err)
	}
}

func TestLoadModelRejectsMissingRequiredFields(t *testing.T) {
	modelData, err := os.ReadFile(expectedModelPath("01-owned-kind-interface"))
	if err != nil {
		t.Fatal(err)
	}
	base, err := normalizer.ParseYAMLData(modelData)
	if err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name    string
		pointer string
		remove  func(map[string]any)
	}{
		{
			name:    "top-level object",
			pointer: "/vocabulary",
			remove: func(model map[string]any) {
				delete(model, "vocabulary")
			},
		},
		{
			name:    "nested object",
			pointer: "/metadata/normalizer",
			remove: func(model map[string]any) {
				delete(model["metadata"].(map[string]any), "normalizer")
			},
		},
		{
			name:    "nested scalar",
			pointer: "/metadata/normalizer/version",
			remove: func(model map[string]any) {
				normalizerData := model["metadata"].(map[string]any)["normalizer"].(map[string]any)
				delete(normalizerData, "version")
			},
		},
		{
			name:    "array member field",
			pointer: "/extensions/0/semanticSha256",
			remove: func(model map[string]any) {
				extension := model["extensions"].([]any)[0].(map[string]any)
				delete(extension, "semanticSha256")
			},
		},
		{
			name:    "declaration provenance field",
			pointer: "/vocabulary/ownedDeclarations/0/provenance/coordinate",
			remove: func(model map[string]any) {
				vocabulary := model["vocabulary"].(map[string]any)
				declaration := vocabulary["ownedDeclarations"].([]any)[0].(map[string]any)
				provenance := declaration["provenance"].(map[string]any)
				delete(provenance, "coordinate")
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			model := cloneDocument(t, base)
			test.remove(model)
			data, err := yaml.Marshal(model)
			if err != nil {
				t.Fatal(err)
			}
			modelPath := filepath.Join(t.TempDir(), "model.yaml")
			if err := os.WriteFile(modelPath, data, 0o600); err != nil {
				t.Fatal(err)
			}
			_, err = LoadModel(modelPath)
			if err == nil || !strings.Contains(err.Error(), "RCG1021") || !strings.Contains(err.Error(), test.pointer) {
				t.Fatalf("missing model field error = %v, want RCG1021 at %s", err, test.pointer)
			}
		})
	}
}

func TestEmitRejectsMissingNestedModelField(t *testing.T) {
	model := loadExpectedModel(t, "01-owned-kind-interface")
	model.Metadata.Normalizer.Version = ""
	err := Emit(model, loadTestTarget(t, "01-owned-kind-interface.yaml"), filepath.Join(t.TempDir(), "output"))
	if err == nil || !strings.Contains(err.Error(), "RCG1021") || !strings.Contains(err.Error(), "/metadata/normalizer/version") {
		t.Fatalf("missing model field error = %v", err)
	}
}

func cloneDocument(t *testing.T, value map[string]any) map[string]any {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func TestFixedSymbolCollisionHasExactDiagnostic(t *testing.T) {
	fixture := filepath.Join("testdata", "negative", "fixed-symbol-collision")
	model := normalizeFixture(t, fixture, "urn:runtimeconditions:conformance:go-fixed-symbol-collision")
	target, err := LoadPackageTarget(filepath.Join(fixture, "package-target.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	err = Emit(model, target, filepath.Join(t.TempDir(), "output"))
	assertExactDiagnostic(t, err, filepath.Join(fixture, "diagnostic.yaml"))
}

func TestSameDomainMemberCollisionHasExactDiagnostic(t *testing.T) {
	fixture := filepath.Join("testdata", "negative", "value-member-collision")
	model := normalizeFixture(t, fixture, "urn:runtimeconditions:go-fixture:value-member-collision")
	target, err := LoadPackageTarget(filepath.Join(fixture, "package-target.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	err = Emit(model, target, filepath.Join(t.TempDir(), "generated"))
	assertExactDiagnostic(t, err, filepath.Join(fixture, "diagnostic.yaml"))
}

func assertExactDiagnostic(t *testing.T, actualError error, expectedPath string) {
	t.Helper()
	var diagnosticError *DiagnosticError
	if !errors.As(actualError, &diagnosticError) {
		t.Fatalf("error = %T %v, want DiagnosticError", actualError, actualError)
	}
	actual, err := yaml.Marshal(diagnosticError.Diagnostic)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := os.ReadFile(expectedPath)
	if err != nil {
		t.Fatal(err)
	}
	if string(actual) != string(expected) {
		t.Fatalf("diagnostic:\n%s\nwant:\n%s", actual, expected)
	}
}

func findStructType(t *testing.T, file *ast.File, name string) *ast.StructType {
	t.Helper()
	for _, declaration := range file.Decls {
		group, ok := declaration.(*ast.GenDecl)
		if !ok {
			continue
		}
		for _, spec := range group.Specs {
			typeSpec, ok := spec.(*ast.TypeSpec)
			if !ok || typeSpec.Name.Name != name {
				continue
			}
			structure, ok := typeSpec.Type.(*ast.StructType)
			if !ok {
				t.Fatalf("generated type %s has type %T, want struct", name, typeSpec.Type)
			}
			return structure
		}
	}
	t.Fatalf("generated source has no type %s", name)
	return nil
}

func typeCheckGeneratedPackage(t *testing.T, directory, importPath string) *types.Package {
	t.Helper()
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, filepath.Join(directory, generatedGoFile), nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	packageValue, err := new(types.Config).Check(importPath, fset, []*ast.File{file}, nil)
	if err != nil {
		t.Fatalf("type-check generated package %s: %v", importPath, err)
	}
	return packageValue
}

func packageType(t *testing.T, packageValue *types.Package, name string) types.Type {
	t.Helper()
	object := packageValue.Scope().Lookup(name)
	if object == nil {
		t.Fatalf("package %s has no exported type %s", packageValue.Path(), name)
	}
	typeName, ok := object.(*types.TypeName)
	if !ok {
		t.Fatalf("package object %s has type %T, want type name", name, object)
	}
	return typeName.Type()
}

func normalizeFixture(t *testing.T, root, rootID string) normalizer.BindingModel {
	t.Helper()
	schemas, err := normalizer.LoadSchemas(
		filepath.Join("..", "..", "model", "runtimeconditions.extension-semantic.schema.yaml"),
		filepath.Join("..", "..", "model", "runtimeconditions.binding-model.schema.yaml"),
	)
	if err != nil {
		t.Fatal(err)
	}
	resolver, err := normalizer.NewResolver(normalizer.ResolverConfig{Schemas: schemas, CatalogRoots: []string{root}})
	if err != nil {
		t.Fatal(err)
	}
	closure, err := resolver.Resolve(context.Background(), rootID)
	if err != nil {
		t.Fatal(err)
	}
	model, err := normalizer.Normalize(closure, normalizer.BuildDependencyLock(closure), schemas, normalizer.NormalizeConfig{
		CoreProfileSchema: normalizer.CoreProfileIdentity{
			ID: "urn:runtimeconditions:test:core-profile-schema", Version: "0.0.0-test", SemanticSHA256: strings.Repeat("c", 64),
		},
		Normalizer: normalizer.ToolIdentity{
			Name: normalizer.NormalizerName, Version: normalizer.NormalizerVersion, SHA256: strings.Repeat("d", 64),
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	return model
}

func expectedModelPath(name string) string {
	return filepath.Join("..", "..", "model", "conformance", "expected", name, "runtimeconditions.binding-model.yaml")
}

func testTargetPath(name string) string {
	return filepath.Join("testdata", "package-targets", name)
}

func loadExpectedModel(t *testing.T, name string) normalizer.BindingModel {
	t.Helper()
	model, err := LoadModel(expectedModelPath(name))
	if err != nil {
		t.Fatal(err)
	}
	return model
}

func loadTestTarget(t *testing.T, name string) PackageTarget {
	t.Helper()
	target, err := LoadPackageTarget(testTargetPath(name))
	if err != nil {
		t.Fatal(err)
	}
	return target
}

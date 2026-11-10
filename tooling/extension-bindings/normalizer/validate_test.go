package normalizer

import (
	"bytes"
	"testing"
)

func TestExtensionReferenceValidation(t *testing.T) {
	const canonical = "https://runtimeconditions.io/extensions/example:1.0.0"
	const artifact = "https://runtimeconditions.io/extensions/example/1.0.0/runtimeconditions.extension.yaml"
	for _, test := range []struct {
		name, id, version, dependency, code, pointer string
	}{
		{"matching annotation", canonical, "1.0.0", "", "", ""},
		{"omitted annotation", canonical, "", "", "", ""},
		{"label version", "https://runtimeconditions.io/extensions/example:v1alpha1", "v1alpha1", "", "", ""},
		{"digest version", "https://runtimeconditions.io/extensions/example:sha256:abc", "sha256:abc", "", "", ""},
		{"unversioned id with annotation", "https://example.test/service", "1.0.0", "", "RCB1105", "/metadata/id"},
		{"artifact id", artifact, "1.0.0", "", "RCB1105", "/metadata/id"},
		{"artifact id with appended version", artifact + ":1.0.0", "1.0.0", "", "RCB1105", "/metadata/id"},
		{"empty version suffix", "https://example.test/service:", "1.0.0", "", "RCB1105", "/metadata/id"},
		{"mismatched annotation", canonical, "2.0.0", "", "RCB1106", "/metadata/version"},
		{"annotation spelling mismatch", "https://example.test/service:v1alpha1", "V1alpha1", "", "RCB1106", "/metadata/version"},
		{"canonical dependency", canonical, "1.0.0", "https://example.test/dependency:v1alpha1", "", ""},
		{"unversioned dependency", canonical, "1.0.0", "https://example.test/dependency", "RCB1110", "/spec/dependencies/0"},
		{"artifact dependency", canonical, "1.0.0", artifact, "RCB1110", "/spec/dependencies/0"},
		{"artifact dependency with appended version", canonical, "1.0.0", artifact + ":1.0.0", "RCB1110", "/spec/dependencies/0"},
	} {
		t.Run(test.name, func(t *testing.T) {
			var dependencies []string
			if test.dependency != "" {
				dependencies = []string{test.dependency}
			}
			data := bytes.Replace(fixtureExtension(test.id, dependencies, kindSpec("fixture.service")), []byte("  version: 1.0.0\n"), nil, 1)
			if test.version != "" {
				data = bytes.Replace(data, []byte("spec:\n"), []byte("  version: "+test.version+"\nspec:\n"), 1)
			}
			definition, mapping, err := DecodeExtension(data)
			if err != nil {
				t.Fatal(err)
			}
			err = testSchemas(t).ValidateExtension(mapping, definition)
			if test.code == "" {
				if err != nil {
					t.Fatal(err)
				}
				if definition.Metadata.ID != test.id || definition.Metadata.Version != test.version {
					t.Fatal("validation changed the identity or version annotation")
				}
			} else if err == nil || diagnosticCode(t, err) != test.code || err.(*DiagnosticError).Diagnostic.JSONPointer != test.pointer {
				t.Fatalf("expected %s at %s, got %v", test.code, test.pointer, err)
			}
		})
	}
}

func TestLanguageSpecificEmittersMayHandleHyphens(t *testing.T) {
	data := []byte("apiVersion: runtimeconditions.io/v1alpha1\nkind: RuntimeConditionsExtensionDefinition\nmetadata:\n  id: https://runtimeconditions.io/test/hyphen-id:1.0.0\n  version: 1.0.0\nspec:\n  kinds:\n    - name: service\n  fieldValues:\n    - field: mode\n      targetKind: service\n      values: [direct-mode]\n")
	definition, mapping, err := DecodeExtension(data)
	if err != nil {
		t.Fatal(err)
	}
	if err := testSchemas(t).ValidateExtension(mapping, definition); err != nil {
		t.Fatal(err)
	}
}

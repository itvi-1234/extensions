# Java emitter contract

This records the Java target, layout, and naming decisions for the native Java
emitter. It is written in Java, as the implementation standard requires of every
emitter, and follows the Python emitter's structure.

The emitter consumes one validated binding model and one selected, resolved Java
target through the shared command contract:

```text
runtimeconditions-binding-emitter-java emit \
  --model runtimeconditions.binding-model.yaml \
  --package-config <target.yaml> --output <new empty directory>
```

`verify --model --package-config --input <package>` parses the generated source
with the JDK compiler's syntax tree API (never compiling or running it), checks
its public API against the model plan, and compares the structural manifest with
a fresh rendering. `api --input <package>` prints the structural signatures.

## Target configuration

The selected target uses `runtimeconditions.io/java-package-target/v1alpha1` and
`RuntimeConditionsJavaPackageTarget`. Its shape is defined by
`package-target.schema.yaml`; the emitter validates it field by field with the
same diagnostics as the schema.

- `packageKey`, `rootExtension`, `version`, `sourceDirectory`, and
  `publicationMode` correspond to the package set and language entry in the
  catalog. `sourceDirectory` is exactly `bindings/<packageKey>/java`.
- `groupId` and `artifactId` are the Maven coordinate. `javaPackage` is the Java
  package every generated type is declared in. None of them is inferred from
  extension vocabulary.
- `minimumJavaVersion` is a whole release number of at least `17`. It becomes
  `maven.compiler.release`.
- `repositoryUrl` supplies the package repository metadata and must use HTTPS.
  A registry target additionally requires `registryId`.
- `dependencies` contains only direct extension dependencies, with their Maven
  coordinates, Java packages, and exact tested versions, and equals the model's
  direct dependency set.
- `emitterSha256` is supplied by the caller and recorded in the manifest.

Package versions are SemVer without a leading `v` or build metadata and map
unchanged to Maven. Supported prerelease forms are `-alpha.N`, `-beta.N`, and
`-rc.N`. Direct dependency ranges use the Maven interval `[<tested>,<next-breaking>)`,
where `next-breaking` is `0.(y+1).0` below `1.0.0` and `(major+1).0.0` otherwise.

## Generated source tree

```text
<new output directory>/
  pom.xml
  src/main/java/<javaPackage as directories>/
    Declaration.java
    Bindings.java
    <Kind>Field.java
    <Type>.java
  src/main/resources/runtimeconditions/
    runtimeconditions.bindings.yaml
```

Every public type is declared in its own file, named after the type. The
remaining binding resources belong beside the manifest in
`src/main/resources/runtimeconditions/` so that they are packaged in the jar.
Only readable Java source and the project file are committed; the jar is a build
output.

Generated source starts with the non-editable header naming the model digest and
emitter version, and is rendered directly by the emitter, so its formatting does
not depend on an external formatter. `pom.xml` carries the same header in an XML
comment.

## API rules

1. Every owned kind becomes one static method `Bindings.kind(KindField... fields)`
   returning `Declaration`. `Declaration` is an inert final class with a
   package-private constructor; the method body only checks its argument.
2. `<Kind>Field` is an interface whose only member is a marker method named
   `rcMarker_<16 hex digits>`, derived from the owner and declaration
   coordinate. Every applicable object record declares that method and
   `implements` the interface, so a field belonging to another kind does not
   compile. Cross-package additive fields implement the provider's interface in
   the same way.
3. Objects become records whose components are the fields, required components
   first. A required component of a non-nullable type is checked with
   `Objects.requireNonNull`; an optional component is `null` when absent. Records
   are shallowly immutable. The emitter does not add factories or builders.
4. Scalars map to boxed types so that an absent optional value is `null`:
   `String`, `Boolean`, `Long` for integers, `Double` for numbers, `Void` for
   JSON null, and `Object` for any JSON value.
5. Arrays and maps become single-component wrapper records named after the
   shape, holding `List<T>` or `Map<String, T>`. Naming the wrapper keeps
   recursive shapes expressible.
6. Unions become a `sealed interface` with one nested record per variant,
   `Variant1`, `Variant2`, …, each holding its variant's value.
7. String value domains become `enum` types whose constants are upper snake case
   and whose `value()` returns the serialized string. Integer and number shapes
   remain distinct.
8. Imported declarations are not re-declared. A type implementing an imported
   marker imports that interface from its direct provider package.

Names derive only from exact source names. Types and marker interfaces use Pascal
case, fields and methods use camel case, and enum constants use upper snake case.
A leading digit gains `X` (types and constants) or `x`. A Java keyword, literal,
contextual type name, or an `Object` method name that cannot be a record component
gains one trailing underscore. A name that equals a `java.lang` or `java.util`
type the generated source uses (`Record`, `String`, `List`, …) or a generated
helper (`Declaration`, `Bindings`) stops emission instead of being renamed.
Collisions are resolved only by prepending parent path components, nearest first,
and otherwise stop emission.

## Diagnostics

Codes use the `RCJ` prefix and mirror the meanings of the Python `RCP` codes.

| Code | Meaning |
| --- | --- |
| `RCJ1001` | YAML input cannot be read or exceeds the size limit. |
| `RCJ1002` | YAML syntax, profile, structure, or resource-limit failure. |
| `RCJ1003` | Binding-model schema validation failure. |
| `RCJ1004` | Unsupported binding-model `apiVersion`. |
| `RCJ1005` | Unsupported binding-model `kind`. |
| `RCJ1006` | Invalid Java package-target field or dependency metadata. |
| `RCJ1007` | Target source directory does not match its package key. |
| `RCJ1008` | Unsupported minimum Java version. |
| `RCJ1009` | Target root extension or direct dependency set differs from the model. |
| `RCJ1010` | Unknown structural shape kind. |
| `RCJ1011` | Inconsistent extension closure or declaration ownership. |
| `RCJ1012` | Inconsistent shape details, value domain, or unresolved reference. |
| `RCJ2000` | A source name cannot be derived as a valid Java identifier. |
| `RCJ2001` | Symbol collision or reserved-name conflict. |
| `RCJ3001` | Output directory is not new or empty. |
| `RCJ3002` | Output directory cannot be inspected or written. |

## Input loading

The model is read with the Python emitter's restrictions: UTF-8 without BOM, LF
line endings, one trailing newline, no comments, anchors, aliases, or tags,
string mapping keys only, no duplicate keys, finite numbers, and the same size,
node, and depth limits. It is then validated against
`model/runtimeconditions.binding-model.schema.yaml`, which the build copies into
the emitter's resources. The schema can be overridden with
`RC_BINDING_MODEL_SCHEMA` when the emitter runs against a different checkout.

## Verification

The tests run the shared conformance models in `model/conformance/expected` and
the committed first-party models. For each, they check that three independent
emissions are byte-identical, that `verify` accepts the output, and that the
package compiles with `javac --release 17 -Xlint:all -Werror`. A generated
conformance source constructs every type, enum constant, collection, map, union
variant, and declaration. Imported markers are checked against type-only provider
stubs, and a stub with a different marker method must fail to compile. Negative
tests cover invalid inputs, tampered output, and values the model does not allow.

## Design notes

- **Language key and layout.** The catalog language key is `java`, and a package
  lives in `bindings/<key>/java`.
- **Functions.** Java has no free functions, so declaration functions are static
  methods of `Bindings`. The manifest names that class in `functionClass` and
  records the file that declares the method.
- **Unions.** Java has no union types. Each variant is wrapped in a nested
  record so that object, scalar, and collection variants are all expressed the
  same way and a record can belong to more than one union.
- **Build tooling.** The emitter is built with Gradle and its dependencies are
  locked in `gradle.lockfile`. The generated project is a Maven project; the
  emitter never runs Maven. JDK 21.0.12, Gradle 8.14.2, and the library versions
  are recorded under `languages.java` in `toolchain.lock.yaml`.

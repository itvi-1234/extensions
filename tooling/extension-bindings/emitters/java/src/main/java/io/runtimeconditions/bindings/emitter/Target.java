package io.runtimeconditions.bindings.emitter;

import static io.runtimeconditions.bindings.emitter.DiagnosticError.fail;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class Target {
    public static final String API = "runtimeconditions.io/java-package-target/v1alpha1";
    public static final String KIND = "RuntimeConditionsJavaPackageTarget";
    public static final Pattern VERSION =
            Pattern.compile(
                    "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)\\.(0|[1-9][0-9]*))?$");
    public static final Pattern KEY = Pattern.compile("^[a-z0-9]+(?:-[a-z0-9]+)*$");
    public static final Pattern GROUP_ID = Pattern.compile("^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$");
    public static final Pattern ARTIFACT_ID = Pattern.compile("^[a-z0-9]+(?:-[a-z0-9]+)*$");
    public static final Pattern JAVA_PACKAGE =
            Pattern.compile("^[a-z][a-z0-9_]*(?:\\.[a-z][a-z0-9_]*)*$");
    public static final Pattern SHA = Pattern.compile("^[0-9a-f]{64}$");
    private static final Pattern JAVA_VERSION = Pattern.compile("^(0|[1-9][0-9]*)$");
    private static final int MINIMUM_JAVA = 17;

    public record Dependency(
            String extension, String groupId, String artifactId, String javaPackage, String version) {
        public String coordinate() {
            return groupId + ":" + artifactId;
        }
    }

    public record PackageTarget(
            String packageKey,
            String rootExtension,
            String groupId,
            String artifactId,
            String javaPackage,
            String version,
            String sourceDirectory,
            String minimumJavaVersion,
            String publicationMode,
            String repositoryUrl,
            String registryId,
            List<Dependency> dependencies,
            String emitterSha256) {
        public String coordinate() {
            return groupId + ":" + artifactId;
        }

        public PackageTarget withEmitterSha256(String digest) {
            return new PackageTarget(
                    packageKey,
                    rootExtension,
                    groupId,
                    artifactId,
                    javaPackage,
                    version,
                    sourceDirectory,
                    minimumJavaVersion,
                    publicationMode,
                    repositoryUrl,
                    registryId,
                    dependencies,
                    digest);
        }
    }

    private static final List<String> ALLOWED =
            List.of(
                    "apiVersion",
                    "kind",
                    "packageKey",
                    "rootExtension",
                    "groupId",
                    "artifactId",
                    "javaPackage",
                    "version",
                    "sourceDirectory",
                    "minimumJavaVersion",
                    "publicationMode",
                    "registryId",
                    "repositoryUrl",
                    "dependencies",
                    "emitterSha256");
    private static final Set<String> OPTIONAL = Set.of("registryId", "dependencies", "emitterSha256");
    private static final List<String> DEPENDENCY_FIELDS =
            List.of("extension", "groupId", "artifactId", "javaPackage", "version");

    private Target() {}

    private static DiagnosticError configFail(String message, String pointer) {
        return fail("package-config", "RCJ1006", "package-target", message, pointer);
    }

    private static DiagnosticError configFail(String message, String pointer, String coordinate) {
        return fail("package-config", "RCJ1006", coordinate, message, pointer);
    }

    private static String text(JsonNode value, String name, String pointer, String coordinate) {
        JsonNode node = value.get(name);
        if (node == null || !node.isTextual() || node.asText().isEmpty()) {
            throw configFail("invalid " + name, pointer, coordinate);
        }
        return node.asText();
    }

    static boolean validJavaPackage(String value) {
        if (!JAVA_PACKAGE.matcher(value).matches()) {
            return false;
        }
        for (String part : value.split("\\.")) {
            if (Naming.isReservedWord(part)) {
                return false;
            }
        }
        return true;
    }

    public static PackageTarget load(Path path) {
        ObjectNode value = YamlIo.load(path, false);
        List<String> missing = new ArrayList<>();
        for (String name : ALLOWED) {
            if (!OPTIONAL.contains(name) && !value.has(name)) {
                missing.add(name);
            }
        }
        missing.sort(Comparator.naturalOrder());
        for (String name : missing) {
            throw configFail("missing required field '" + name + "'", "/" + name);
        }
        Set<String> unknown = new TreeSet<>();
        for (Iterator<String> names = value.fieldNames(); names.hasNext(); ) {
            String name = names.next();
            if (!ALLOWED.contains(name)) {
                unknown.add(name);
            }
        }
        for (String name : unknown) {
            throw configFail("unknown field '" + name + "'", "/" + name);
        }
        if (!API.equals(value.path("apiVersion").asText(null))
                || !KIND.equals(value.path("kind").asText(null))) {
            throw configFail("unsupported target apiVersion or kind", "");
        }
        String emitterSha256 = "";
        if (value.has("emitterSha256")) {
            JsonNode node = value.get("emitterSha256");
            if (!node.isTextual() || !SHA.matcher(node.asText()).matches()) {
                throw configFail(
                        "emitterSha256 must be a 64-character lowercase SHA-256 of the emitter tool",
                        "/emitterSha256");
            }
            emitterSha256 = node.asText();
        }
        for (String name : ALLOWED) {
            if (OPTIONAL.contains(name) || name.equals("apiVersion") || name.equals("kind")) {
                continue;
            }
            text(value, name, "/" + name, "package-target");
        }
        String packageKey = value.get("packageKey").asText();
        String groupId = value.get("groupId").asText();
        String artifactId = value.get("artifactId").asText();
        String javaPackage = value.get("javaPackage").asText();
        String version = value.get("version").asText();
        if (!KEY.matcher(packageKey).matches()) {
            throw configFail("invalid packageKey", "/packageKey");
        }
        if (!GROUP_ID.matcher(groupId).matches() || groupId.length() > 128) {
            throw configFail("invalid groupId", "/groupId");
        }
        if (!ARTIFACT_ID.matcher(artifactId).matches() || artifactId.length() > 128) {
            throw configFail("invalid artifactId", "/artifactId");
        }
        if (!validJavaPackage(javaPackage)) {
            throw configFail("invalid javaPackage", "/javaPackage");
        }
        if (!VERSION.matcher(version).matches()) {
            throw configFail("unsupported package version", "/version");
        }
        if (!value.get("sourceDirectory").asText().equals("bindings/" + packageKey + "/java")) {
            throw fail(
                    "package-config",
                    "RCJ1007",
                    packageKey,
                    "source directory does not match package key",
                    "/sourceDirectory");
        }
        String minimum = value.get("minimumJavaVersion").asText();
        Matcher parts = JAVA_VERSION.matcher(minimum);
        if (!parts.matches() || Integer.parseInt(minimum) < MINIMUM_JAVA) {
            throw fail(
                    "package-config",
                    "RCJ1008",
                    packageKey,
                    "unsupported minimum Java version",
                    "/minimumJavaVersion");
        }
        String mode = value.get("publicationMode").asText();
        if (!mode.equals("github-tag") && !mode.equals("registry")) {
            throw configFail("unsupported publication mode", "/publicationMode", packageKey);
        }
        String repositoryUrl = value.get("repositoryUrl").asText();
        if (!repositoryUrl.startsWith("https://") || repositoryUrl.chars().anyMatch(Character::isWhitespace)) {
            throw configFail("repositoryUrl must use https", "/repositoryUrl", packageKey);
        }
        String registry = value.has("registryId") ? text(value, "registryId", "/registryId", packageKey) : null;
        if (mode.equals("registry") != (registry != null)) {
            throw configFail(
                    "registryId is required exactly for registry publication",
                    "/registryId",
                    packageKey);
        }
        JsonNode entries = value.has("dependencies") ? value.get("dependencies") : Json.MAPPER.createArrayNode();
        if (!entries.isArray()) {
            throw configFail("dependencies must be a sequence", "/dependencies", packageKey);
        }
        List<Dependency> dependencies = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        int index = 0;
        for (JsonNode entry : entries) {
            String pointer = "/dependencies/" + index;
            index += 1;
            if (!entry.isObject()) {
                throw configFail("dependency must be a mapping", pointer, packageKey);
            }
            for (String name : DEPENDENCY_FIELDS.stream().sorted().toList()) {
                if (!entry.has(name)) {
                    throw configFail("missing dependency field '" + name + "'", pointer + "/" + name, packageKey);
                }
            }
            Set<String> extra = new TreeSet<>();
            for (Iterator<String> names = entry.fieldNames(); names.hasNext(); ) {
                String name = names.next();
                if (!DEPENDENCY_FIELDS.contains(name)) {
                    extra.add(name);
                }
            }
            for (String name : extra) {
                throw configFail("unknown dependency field '" + name + "'", pointer + "/" + name, packageKey);
            }
            String extension = text(entry, "extension", pointer + "/extension", packageKey);
            String dependencyGroup = text(entry, "groupId", pointer + "/groupId", packageKey);
            String dependencyArtifact = text(entry, "artifactId", pointer + "/artifactId", packageKey);
            String dependencyPackage = text(entry, "javaPackage", pointer + "/javaPackage", packageKey);
            String dependencyVersion = text(entry, "version", pointer + "/version", packageKey);
            if (!seen.add(extension)) {
                throw configFail("duplicate dependency '" + extension + "'", pointer, packageKey);
            }
            if (!GROUP_ID.matcher(dependencyGroup).matches()
                    || !ARTIFACT_ID.matcher(dependencyArtifact).matches()
                    || !validJavaPackage(dependencyPackage)
                    || !VERSION.matcher(dependencyVersion).matches()) {
                throw configFail("invalid dependency package metadata", pointer, packageKey);
            }
            dependencies.add(
                    new Dependency(extension, dependencyGroup, dependencyArtifact, dependencyPackage, dependencyVersion));
        }
        return new PackageTarget(
                packageKey,
                value.get("rootExtension").asText(),
                groupId,
                artifactId,
                javaPackage,
                version,
                value.get("sourceDirectory").asText(),
                minimum,
                mode,
                repositoryUrl,
                registry,
                List.copyOf(dependencies),
                emitterSha256);
    }
}

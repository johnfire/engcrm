import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Prefers Gradle's merged manifest (present after a build — includes
// components injected by libraries at merge time, e.g. androidx.startup's
// InitializationProvider, with their real exported flags) and falls back to
// the app's own source manifest when no build has happened yet (e.g. running
// this locally without building first). android-security.yml always builds
// first, so CI runs get the accurate merged-manifest picture.

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const MOBILE_DIR = path.join(REPO_ROOT, "engcrm-mobile");
const SOURCE_MANIFEST_PATH = path.join(MOBILE_DIR, "android", "app", "src", "main", "AndroidManifest.xml");
// Overridable so CI can hand this off via a flat artifact-download path
// rather than relying on the exact nested Gradle intermediates layout
// surviving an upload/download round-trip.
const MERGED_MANIFEST_PATH = process.env.MERGED_MANIFEST_PATH || path.join(
  MOBILE_DIR, "android", "app", "build", "intermediates", "packaged_manifests",
  "debug", "processDebugManifestForPackage", "AndroidManifest.xml",
);
const BUILD_GRADLE_PATH = path.join(MOBILE_DIR, "android", "app", "build.gradle");
const BASELINE_PATH = path.join(__dirname, "android-baseline.json");

function readManifest() {
  if (existsSync(MERGED_MANIFEST_PATH)) {
    console.error("[android-static-checks] using merged manifest (post-build, includes library-injected components)");
    return readFileSync(MERGED_MANIFEST_PATH, "utf8");
  }
  console.error("[android-static-checks] no merged manifest found — falling back to source manifest only " +
    "(library-injected components like androidx.startup's InitializationProvider won't be visible; " +
    "run `./gradlew :app:processDebugManifestForPackage` first for the full picture)");
  return readFileSync(SOURCE_MANIFEST_PATH, "utf8");
}

function readSourceManifest() {
  return readFileSync(SOURCE_MANIFEST_PATH, "utf8");
}

function readBuildGradle() {
  return readFileSync(BUILD_GRADLE_PATH, "utf8");
}

function readApplicationId(buildGradle) {
  const match = buildGradle.match(/applicationId\s+['"]([^'"]+)['"]/);
  if (!match) throw new Error("could not find applicationId in build.gradle");
  return match[1];
}

// android:name is "." + relative for the app's own components, but already
// fully-qualified for library-injected ones — normalize both to the same
// fully-qualified form so baseline comparisons aren't fooled by which one
// a given manifest source happens to use.
function qualifyComponentName(name, applicationId) {
  return name.startsWith(".") ? `${applicationId}${name}` : name;
}

function readBaseline() {
  return JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
}

// Explicit android:exported="true" only — targetSdk 31+ requires it to be
// explicit on any component with an intent-filter, which this app relies on,
// so implicit (pre-S) export-by-intent-filter isn't handled here.
function findExportedComponents(manifest, applicationId) {
  const found = [];
  const tagRe = /<(activity|service|receiver|provider)\s+([^>]*)>/g;
  let match;
  while ((match = tagRe.exec(manifest)) !== null) {
    const [, tagType, attrs] = match;
    const nameMatch = attrs.match(/android:name="([^"]+)"/);
    const isExported = /android:exported="true"/.test(attrs);
    if (isExported && nameMatch) {
      found.push({ type: tagType, name: qualifyComponentName(nameMatch[1], applicationId) });
    }
  }
  return found;
}

function findPermissions(manifest) {
  const found = [];
  const permRe = /<uses-permission\s+android:name="([^"]+)"/g;
  let match;
  while ((match = permRe.exec(manifest)) !== null) {
    found.push(match[1]);
  }
  return found;
}

function diffExportedComponents(current, baseline) {
  const baselineNames = new Set(baseline.exportedComponents.map((c) => c.name));
  const findings = [];
  for (const component of current) {
    if (!baselineNames.has(component.name)) {
      findings.push({
        severity: "high",
        category: "MASVS-PLATFORM",
        title: `New exported ${component.type} not in baseline: ${component.name}`,
        detail:
          "A newly-exported component is reachable by any other app on the device, unauthenticated. " +
          "If this is intentional, add it to scripts/security/android-baseline.json with a reason.",
      });
    }
  }
  return findings;
}

function diffPermissions(current, baseline) {
  const baselineSet = new Set(baseline.permissions);
  const findings = [];
  for (const permission of current) {
    if (!baselineSet.has(permission)) {
      findings.push({
        severity: "medium",
        category: "MASVS-PLATFORM",
        title: `New permission requested, not in baseline: ${permission}`,
        detail:
          "Confirm this permission is load-bearing for a real feature, then add it to " +
          "scripts/security/android-baseline.json with a reason.",
      });
    }
  }
  return findings;
}

// Deliberately checks the SOURCE manifest, never a merged one — a debug
// build's merged manifest legitimately has debuggable="true" (that's the
// build type doing its job), so checking that would always false-positive.
// The actual smell is a developer hardcoding the attribute in source, which
// would force it on even for release builds.
function checkDebuggable() {
  const sourceManifest = readSourceManifest();
  if (/android:debuggable="true"/.test(sourceManifest)) {
    return [
      {
        severity: "critical",
        category: "MASVS-PLATFORM",
        title: "android:debuggable=\"true\" is hardcoded in the source manifest",
        detail: "This must never be forced on for a release build — it should only ever come from the debug build type.",
      },
    ];
  }
  return [];
}

// The finding this whole pipeline exists to catch a regression on — see the
// 2026-08-04 review: release keystore + literal password were committed to git.
function checkSigningConfig(buildGradle) {
  const findings = [];
  const releaseBlockMatch = buildGradle.match(/release\s*\{([^}]*)\}/s);
  if (!releaseBlockMatch) return findings;
  const releaseBlock = releaseBlockMatch[1];
  const literalPassword = /(storePassword|keyPassword)\s+['"][^'"]+['"]/;
  if (literalPassword.test(releaseBlock)) {
    findings.push({
      severity: "critical",
      category: "build-config",
      title: "Release signing password is a literal string in build.gradle",
      detail:
        "storePassword/keyPassword should be read from an environment variable or a git-ignored " +
        "keystore.properties file, not hardcoded — anyone with repo read access can currently sign " +
        "an update with the same identity as the real app.",
    });
  }
  return findings;
}

function checkKeystoreTrackedInGit() {
  const result = spawnSync(
    "git",
    ["-C", REPO_ROOT, "ls-files", "engcrm-mobile/android/app/keystore", "engcrm-mobile/android/app/*.keystore", "engcrm-mobile/android/app/*.jks"],
    { encoding: "utf8" },
  );
  const tracked = (result.stdout || "")
    .split("\n")
    .filter(Boolean)
    .filter((f) => !f.endsWith("debug.keystore")); // shared, publicly-known debug key by convention
  if (tracked.length > 0) {
    return [
      {
        severity: "critical",
        category: "build-config",
        title: "Release keystore file is committed to git",
        detail: `Tracked: ${tracked.join(", ")}. Rotate the key and remove it (and its history) once the fix is scheduled.`,
      },
    ];
  }
  return [];
}

function checkMinify(buildGradle) {
  if (!/enableMinifyInReleaseBuilds\s*=\s*true/.test(buildGradle) &&
      !/android\.enableMinifyInReleaseBuilds\s*=\s*true/.test(readGradleProperties())) {
    return [
      {
        severity: "low",
        category: "MASVS-RESILIENCE",
        title: "Release builds are not minified/obfuscated (R8 disabled)",
        detail: "Set android.enableMinifyInReleaseBuilds=true in gradle.properties for basic reverse-engineering resistance.",
      },
    ];
  }
  return [];
}

function readGradleProperties() {
  try {
    return readFileSync(path.join(MOBILE_DIR, "android", "gradle.properties"), "utf8");
  } catch {
    return "";
  }
}

function checkWebViewBridge() {
  const result = spawnSync(
    "grep",
    [
      "-rlE", "addJavascriptInterface", MOBILE_DIR,
      "--exclude-dir=node_modules", "--exclude-dir=android", "--exclude-dir=ios",
    ],
    { encoding: "utf8" },
  );
  const hits = (result.stdout || "").split("\n").filter(Boolean);
  if (hits.length > 0) {
    return [
      {
        severity: "high",
        category: "MASVS-PLATFORM",
        title: "addJavascriptInterface found alongside WebView usage",
        detail: `Files: ${hits.join(", ")}. Verify the loaded URL can never be attacker-influenced.`,
      },
    ];
  }
  return [];
}

function main() {
  const manifest = readManifest();
  const buildGradle = readBuildGradle();
  const baseline = readBaseline();
  const applicationId = readApplicationId(buildGradle);

  const exportedComponents = findExportedComponents(manifest, applicationId);
  const permissions = findPermissions(manifest);

  const findings = [
    ...diffExportedComponents(exportedComponents, baseline),
    ...diffPermissions(permissions, baseline),
    ...checkDebuggable(),
    ...checkSigningConfig(buildGradle),
    ...checkKeystoreTrackedInGit(),
    ...checkMinify(buildGradle),
    ...checkWebViewBridge(),
  ];

  const report = {
    check: "android-static-checks",
    timestamp: new Date().toISOString(),
    findings,
  };

  console.log(JSON.stringify(report, null, 2));
  for (const finding of findings) {
    console.error(`[${finding.severity.toUpperCase()}] ${finding.title}`);
  }

  const outPath = process.env.SECURITY_FINDINGS_OUT || path.join(REPO_ROOT, "android-static-findings.json");
  try {
    writeFileSync(outPath, JSON.stringify(report, null, 2));
  } catch {
    // best-effort — stdout above is the source of truth if the write fails
  }

  // Report-only by design (see android-security.yml) — findings are surfaced,
  // never block the push. Only a genuine script error should fail this job.
  process.exitCode = 0;
}

main();

const SEVERITIES = ["info", "low", "moderate", "high", "critical"];

function directAdvisories(report) {
  if (report.error || !report.vulnerabilities || !report.metadata?.vulnerabilities) {
    throw new Error("Dependency audit did not return a complete vulnerability report");
  }
  return Object.entries(report.vulnerabilities).flatMap(([packageName, finding]) => {
    if (!Array.isArray(finding.via) || !finding.via.length || !Array.isArray(finding.nodes)) {
      throw new Error(`Malformed audit finding for ${packageName}`);
    }
    for (const reference of finding.via.filter((entry) => typeof entry === "string")) {
      if (!report.vulnerabilities[reference]) throw new Error(`Unresolved audit finding: ${reference}`);
    }
    return finding.via.filter((entry) => typeof entry === "object").map((advisory) => {
      const identifier = /\/advisories\/(GHSA-[a-z0-9-]+)$/.exec(advisory.url)?.[1];
      if (!identifier || !SEVERITIES.includes(advisory.severity)) {
        throw new Error(`Unrecognized advisory for ${packageName}`);
      }
      return { packageName, identifier, severity: advisory.severity, paths: finding.nodes };
    });
  });
}

function permitsFinding(finding, exception, lockfile, today) {
  return exception.package === finding.packageName && exception.advisory === finding.identifier
    && exception.severity === finding.severity
    && /^\d{4}-\d{2}-\d{2}$/.test(exception.expires) && exception.expires >= today
    && Array.isArray(exception.paths) && Array.isArray(exception.versions)
    && typeof exception.reason === "string" && exception.reason.length > 20
    && finding.paths.length > 0 && finding.paths.every((path) =>
      exception.paths.includes(path) && exception.versions.includes(lockfile.packages?.[path]?.version));
}

export function evaluateAudit(report, policy, lockfile, today = new Date().toISOString().slice(0, 10)) {
  const threshold = SEVERITIES.indexOf(policy.minimumSeverity);
  if (threshold < 0 || !Array.isArray(policy.exceptions)) throw new Error("Invalid dependency policy");
  const findings = directAdvisories(report);
  const usedExceptions = new Set();
  const blocked = findings.filter((finding) => {
    if (SEVERITIES.indexOf(finding.severity) < threshold) return false;
    const exception = policy.exceptions.find((candidate) => permitsFinding(finding, candidate, lockfile, today));
    if (!exception) return true;
    usedExceptions.add(exception);
    return false;
  });
  const stale = policy.exceptions.filter((exception) => !usedExceptions.has(exception));
  return { blocked, stale, accepted: findings.filter((finding) =>
    policy.exceptions.some((exception) => usedExceptions.has(exception) && permitsFinding(finding, exception, lockfile, today))) };
}

export function evaluateBundle(sourceMap, policy) {
  if (!Array.isArray(sourceMap.sources) || sourceMap.sources.length === 0) {
    throw new Error("Android source map has no inspectable source inventory");
  }
  if (!Array.isArray(policy.toolingOnlyPackages)) throw new Error("Missing bundle exclusion policy");
  return policy.toolingOnlyPackages.filter((packageName) => {
    if (!/^(@[a-z0-9-]+\/)?[a-z0-9-]+$/.test(packageName)) throw new Error("Invalid package name in bundle policy");
    const escaped = packageName.replaceAll("/", "\\/");
    const packagePath = new RegExp(`(^|/)node_modules/${escaped}(/|$)`);
    return sourceMap.sources.some((source) => packagePath.test(source.replaceAll("\\", "/")));
  });
}

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };
const SEVERITY_EMOJI = { critical: "🔴", high: "🟠", medium: "🟡", low: "⚪" };

function readReport(filePath) {
  if (!existsSync(filePath)) {
    console.error(`[build-security-report] missing ${filePath} — that check may not have run`);
    return { check: path.basename(filePath), findings: [], missing: true };
  }
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function renderMarkdown(reports, meta) {
  const allFindings = reports.flatMap((r) =>
    r.findings.map((f) => ({ ...f, source: r.check })),
  );
  allFindings.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));

  const lines = [];
  lines.push(`# Android security report — ${meta.commit.slice(0, 7)}`);
  lines.push("");
  lines.push(`Branch: \`${meta.branch}\` · Run: ${meta.runUrl} · ${meta.timestamp}`);
  lines.push("");
  lines.push(
    allFindings.length === 0
      ? "No findings. All static and dynamic checks came back clean."
      : `${allFindings.length} finding(s) — report-only, this never blocks the push.`,
  );
  lines.push("");

  for (const finding of allFindings) {
    const emoji = SEVERITY_EMOJI[finding.severity] ?? "⚪";
    lines.push(`## ${emoji} [${finding.severity.toUpperCase()}] ${finding.title}`);
    lines.push("");
    lines.push(`- **Category:** ${finding.category}`);
    lines.push(`- **Source:** ${finding.source}`);
    lines.push(`- **Detail:** ${finding.detail}`);
    lines.push("");
  }

  for (const report of reports) {
    if (report.missing) {
      lines.push(`> ⚠️ ${report.check} did not produce a report — check the job logs.`);
      lines.push("");
    }
  }

  return lines.join("\n");
}

function main() {
  const staticReport = readReport(
    process.env.STATIC_FINDINGS_PATH || path.join(REPO_ROOT, "android-static-findings.json"),
  );
  const dynamicReport = readReport(
    process.env.DYNAMIC_FINDINGS_PATH || path.join(REPO_ROOT, "android-dynamic-findings.json"),
  );

  const meta = {
    commit: process.env.GITHUB_SHA || "unknown",
    branch: process.env.GITHUB_REF_NAME || "unknown",
    runUrl: process.env.GITHUB_RUN_URL || "n/a",
    timestamp: new Date().toISOString(),
  };

  const combined = {
    meta,
    findings: [
      ...staticReport.findings.map((f) => ({ ...f, source: staticReport.check })),
      ...dynamicReport.findings.map((f) => ({ ...f, source: dynamicReport.check })),
    ],
  };

  writeFileSync(path.join(REPO_ROOT, "android-security-report.json"), JSON.stringify(combined, null, 2));
  writeFileSync(path.join(REPO_ROOT, "android-security-report.md"), renderMarkdown([staticReport, dynamicReport], meta));

  console.log(`[build-security-report] ${combined.findings.length} total finding(s)`);
  process.exitCode = 0;
}

main();

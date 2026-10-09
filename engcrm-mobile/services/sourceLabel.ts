// i18n key for how a record was created (`source` on organizations and people).
// Mirrors gcrm/sources.py label_key(): anything unrecognized reads as "unknown".
const KNOWN = new Set([
  "manual_mobile", "manual_web", "voice", "card_capture", "document_capture", "sign_scan",
  "research_agent", "maps_import", "sign_research", "studies_import", "linkedin",
  "linkedin_import", "manual",
]);

export function sourceLabelKey(source: string | null | undefined): string {
  if (source && KNOWN.has(source)) return `source.${source}`;
  if (source && source.startsWith("bavaria_directory")) return "source.directory_import";
  return "source.unknown";
}

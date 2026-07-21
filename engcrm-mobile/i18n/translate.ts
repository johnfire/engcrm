// Translation lookup for the mobile UI (German + English). Flat, dot-namespaced
// keys (e.g. "nav.contacts"), mirrors gcrm/i18n/translate.py's logic on the web
// side — deliberately hand-rolled rather than i18next, see
// docs/plans/2026-07-21-i18n-design.md for the reasoning. Separate translation
// files per platform (no cross-project sharing), same conventions.
import en from "./en.json";
import de from "./de.json";

export const SUPPORTED_LANGUAGES = ["en", "de"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];
export const DEFAULT_LANGUAGE: Language = "en";

export function isSupportedLanguage(value: unknown): value is Language {
  return typeof value === "string" && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

const CATALOGS: Record<Language, Record<string, string>> = { en, de };

const VAR_PATTERN = /\{\{(\w+)\}\}/g;

function interpolate(text: string, params: Record<string, unknown>): string {
  return text.replace(VAR_PATTERN, (match, key: string) =>
    key in params ? String(params[key]) : match,
  );
}

function resolveKey(key: string, language: Language, count?: number): string | undefined {
  const catalog = CATALOGS[language];
  if (count !== undefined) {
    const pluralized = catalog[`${key}_${count === 1 ? "one" : "other"}`];
    if (pluralized !== undefined) return pluralized;
  }
  return catalog[key];
}

/**
 * Resolve `key` in `language`, falling back to English, then to a visible
 * `[key]` marker so a gap is obvious rather than silently blank. Pass
 * `{count: N}` to pick an `_one`/`_other` pluralized variant.
 */
export function translate(
  key: string,
  language: Language = DEFAULT_LANGUAGE,
  params: Record<string, unknown> = {},
): string {
  const { count, ...rest } = params as { count?: number; [key: string]: unknown };
  let text = resolveKey(key, language, count);
  if (text === undefined && language !== DEFAULT_LANGUAGE) {
    text = resolveKey(key, DEFAULT_LANGUAGE, count);
  }
  if (text === undefined) {
    return `[${key}]`;
  }
  const allParams = count !== undefined ? { ...rest, count } : rest;
  return Object.keys(allParams).length > 0 ? interpolate(text, allParams) : text;
}

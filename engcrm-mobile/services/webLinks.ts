// Opening a stored website in the phone's browser.
//
// Website values reach the CRM from LLM enrichment, scraped directory
// listings, business-card OCR and hand typing, so they arrive without a
// scheme ("acme.de"), padded with whitespace, or carrying a scheme no browser
// should be handed. Linking.openURL rejects all of those with a thrown
// promise, so the screens go through here instead: normalise first, and let a
// bad value fail as plain unlinked text rather than an unhandled rejection.
//
// Parsing is done with a regex rather than `new URL()` because React Native's
// URL polyfill exposes no protocol/hostname getters.

import { Linking } from "react-native";

const HAS_SCHEME = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;
const HTTP_URL = /^https?:\/\/([^/?#\s]+)/i;

/** Return an http(s) URL for `storedWebsite`, or null if it can't be one. */
export function browsableUrl(storedWebsite: string | null | undefined): string | null {
  const trimmed = (storedWebsite ?? "").trim();
  if (!trimmed) return null;
  const candidate = HAS_SCHEME.test(trimmed) ? trimmed : `https://${trimmed}`;
  const authority = HTTP_URL.exec(candidate)?.[1];
  const host = authority?.split("@").pop() ?? "";
  return host.includes(".") ? candidate : null;
}

/** Hand a stored website to the device's default browser. Never throws. */
export async function openWebsite(storedWebsite: string | null | undefined): Promise<boolean> {
  const url = browsableUrl(storedWebsite);
  if (!url) return false;
  try {
    await Linking.openURL(url);
    return true;
  } catch {
    return false;
  }
}

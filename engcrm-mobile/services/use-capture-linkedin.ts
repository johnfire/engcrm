import { useEffect, useState } from "react";
import { ProfileSuggestions, searchCaptureProfiles } from "./capture-linkedin";

export function useCaptureLinkedIn(captureId: number, name: string, company: string, city: string) {
  const [lookup, setLookup] = useState<{ key: string; suggestions: ProfileSuggestions } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const lookupKey = JSON.stringify([captureId, name, company, city, attempt]);
  const canSearch = !!captureId && name.trim().split(/\s+/).length >= 2;
  const searching = canSearch && lookup?.key !== lookupKey;
  const suggestions = !canSearch ? { status: "needs_name", candidates: [] } :
    lookup?.key === lookupKey ? lookup.suggestions : null;

  useEffect(() => {
    let active = true;
    if (!canSearch) return;
    const timer = setTimeout(async () => {
      try {
        const profiles = await searchCaptureProfiles(captureId, name, company, city);
        if (active) setLookup({ key: lookupKey, suggestions: profiles });
      } catch {
        if (active) setLookup({ key: lookupKey, suggestions: { status: "unavailable", candidates: [] } });
      }
    }, 600);
    return () => { active = false; clearTimeout(timer); };
  }, [captureId, name, company, city, canSearch, lookupKey]);

  return { searching, suggestions, canSearch, retry: () => setAttempt((previous) => previous + 1) };
}

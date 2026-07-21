import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import * as SecureStore from "expo-secure-store";
import { DEFAULT_LANGUAGE, Language, isSupportedLanguage, translate } from "./translate";

const LANGUAGE_CACHE_KEY = "engcrm_ui_language";

/** Best-effort local cache so a relaunch shows the right language instantly,
 * before the network round-trip in _layout.tsx's sync effect resolves. */
export async function getCachedLanguage(): Promise<Language> {
  try {
    const cached = await SecureStore.getItemAsync(LANGUAGE_CACHE_KEY);
    return isSupportedLanguage(cached) ? cached : DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

export async function setCachedLanguage(language: Language): Promise<void> {
  try {
    await SecureStore.setItemAsync(LANGUAGE_CACHE_KEY, language);
  } catch {
    // best-effort — worst case the next launch briefly shows English
  }
}

interface I18nContextValue {
  language: Language;
  /** Updates in-memory state and the local cache. Does not call the server —
   * callers that changed the account preference (Settings) or learned it from
   * the server (login, cold-start sync, push) are responsible for that. */
  setLanguage: (language: Language) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

// Default (used only if a component somehow renders without <I18nProvider> —
// shouldn't happen since it wraps the whole app in _layout.tsx, but this way
// a missing provider degrades to correct English text instead of raw keys).
const I18nContext = createContext<I18nContextValue>({
  language: DEFAULT_LANGUAGE,
  setLanguage: () => {},
  t: (key, params) => translate(key, DEFAULT_LANGUAGE, params),
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(DEFAULT_LANGUAGE);

  useEffect(() => {
    getCachedLanguage().then(setLanguageState);
  }, []);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    setCachedLanguage(next);
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, unknown>) => translate(key, language, params),
    [language],
  );

  return (
    <I18nContext.Provider value={{ language, setLanguage, t }}>{children}</I18nContext.Provider>
  );
}

export function useTranslation() {
  return useContext(I18nContext);
}

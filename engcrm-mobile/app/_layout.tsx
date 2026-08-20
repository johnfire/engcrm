import { useCallback, useEffect, useState } from "react";
import { AppState } from "react-native";
import { Stack, useRouter, useSegments } from "expo-router";
import { isLoggedIn } from "../services/auth";
import { fetchHelpTourStatus, fetchMe } from "../services/api";
import { addLanguageChangeListener, registerForPushNotifications } from "../services/notifications";
import { I18nProvider, useTranslation } from "../i18n/I18nContext";
import { isSupportedLanguage } from "../i18n/translate";

function InnerLayout() {
  const router = useRouter();
  const segments = useSegments();
  const [checked, setChecked] = useState(false);
  const { setLanguage } = useTranslation();

  // Pulls the account's current ui_language from the server and applies it.
  // Best-effort: not logged in yet, offline, or an expired token just leaves
  // whatever language is already cached/active — never a hard failure.
  const syncLanguage = useCallback(async () => {
    try {
      const me = await fetchMe();
      if (isSupportedLanguage(me.ui_language)) setLanguage(me.ui_language);
    } catch {
      // ignore — see comment above
    }
  }, [setLanguage]);

  const openTourForNewCustomer = useCallback(async () => {
    try {
      const tour = await fetchHelpTourStatus();
      if (!tour.completed) router.replace("/(drawer)/help?tour=1");
    } catch {
      // Offline customers can continue; the Help Centre still offers the tour.
    }
  }, [router]);

  useEffect(() => {
    isLoggedIn()
      .then((loggedIn) => {
        setChecked(true);
        const inDrawer = segments[0] === "(drawer)";
        if (!loggedIn && inDrawer) {
          router.replace("/login");
        } else if (loggedIn && !inDrawer) {
          router.replace("/(drawer)/organizations");
        }
        if (loggedIn) {
          syncLanguage();
          openTourForNewCustomer();
        }
      })
      .catch(() => {
        // Auth storage unreadable — fall through to login rather than hang
        // forever on the blank (!checked) screen.
        setChecked(true);
        if (segments[0] === "(drawer)") router.replace("/login");
      });
    // This is an initial-session gate; running again after a route change would
    // redirect the user away from their active screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Push registration is best-effort; never let it disrupt startup.
    if (checked) registerForPushNotifications();
  }, [checked]);

  // Covers a language change made on another device while this one was
  // backgrounded — re-checks every time the app comes back to the foreground.
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") syncLanguage();
    });
    return () => subscription.remove();
  }, [syncLanguage]);

  // Covers a language change made elsewhere while THIS device stayed
  // foregrounded the whole time — the silent push carries the new value
  // directly, so no network round-trip is needed to apply it.
  useEffect(() => {
    return addLanguageChangeListener((language) => {
      if (isSupportedLanguage(language)) setLanguage(language);
    });
  }, [setLanguage]);

  if (!checked) return null;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="forgot-password" />
      <Stack.Screen name="(drawer)" />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <I18nProvider>
      <InnerLayout />
    </I18nProvider>
  );
}

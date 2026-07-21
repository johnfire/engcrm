import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { registerPushToken } from "./api";

// A ui_language_changed push (sent when the account's language changes
// elsewhere — see engcrm-mobile/i18n/) is silent: it exists only to tell an
// already-open app to refresh, never to show a banner.
function isSilentLanguagePush(notification: Notifications.Notification): boolean {
  return notification.request.content.data?.type === "ui_language_changed";
}

Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    const silent = isSilentLanguagePush(notification);
    return {
      shouldShowBanner: !silent,
      shouldShowList: !silent,
      shouldPlaySound: !silent,
      shouldSetBadge: false,
    };
  },
});

/**
 * Fires `onLanguageChanged` whenever a ui_language_changed push arrives while
 * the app is running (foregrounded or backgrounded-but-alive) — the fastest
 * path to sync, faster than waiting for the next foreground/cold-start
 * /api/auth/me check. Returns an unsubscribe function.
 */
export function addLanguageChangeListener(onLanguageChanged: (language: string) => void): () => void {
  const subscription = Notifications.addNotificationReceivedListener((notification) => {
    const data = notification.request.content.data;
    if (data?.type === "ui_language_changed" && typeof data.ui_language === "string") {
      onLanguageChanged(data.ui_language);
    }
  });
  return () => subscription.remove();
}

export async function registerForPushNotifications(): Promise<void> {
  // Best-effort: a failure to register (no project id, offline, permission
  // race) must never throw into app startup.
  try {
    if (!Device.isDevice) return;

    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== "granted") return;

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "default",
        importance: Notifications.AndroidImportance.MAX,
      });
    }

    const token = (await Notifications.getExpoPushTokenAsync()).data;
    await registerPushToken(token);
  } catch (error) {
    console.warn("Push registration failed (non-fatal):", error);
  }
}

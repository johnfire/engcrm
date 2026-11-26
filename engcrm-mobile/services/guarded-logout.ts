import { Alert } from "react-native";

import { useOffline } from "./offline-context";
import { readSyncStatus } from "./sync-status";

type OfflineState = ReturnType<typeof useOffline>;
type Translate = (key: string, params?: Record<string, unknown>) => string;

export async function requestGuardedLogout(offline: OfflineState, t: Translate, finishLogout: () => Promise<void>): Promise<void> {
  if (offline.state === "disabled") return finishLogout();
  let pending: number | null = null;
  try {
    if (offline.session) {
      const status = await readSyncStatus(offline.session.database);
      pending = status.pending + status.failed;
    }
  } catch { /* Preserve the database if its status cannot be read. */ }
  if (pending === 0) return finishLogout();
  Alert.alert(t("offlineStatus.logoutTitle"), pending === null ? t("offlineStatus.logoutUnknown")
    : t("offlineStatus.logoutPending", { count: pending }), [
    { text: t("common.cancel"), style: "cancel" },
    { text: t("offlineStatus.logoutKeep"), onPress: () => { void finishLogout(); } },
  ]);
}

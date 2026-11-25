import { Text, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { useOffline } from "../services/offline-context";

export function OfflineStatus() {
  const { t } = useTranslation();
  const { state, status, requestSync, retryOpen, session } = useOffline();
  if (state === "disabled") return null;
  const message = state === "opening" ? t("offlineStatus.opening") : state === "syncing" ? t("offlineStatus.syncing")
    : state === "needs_auth" ? t("offlineStatus.needsAuth") : state === "error" ? t("offlineStatus.error")
      : status?.upToDate ? t("offlineStatus.current") : t("offlineStatus.waiting");
  return <View style={{ paddingHorizontal: 16, paddingVertical: 12 }} accessibilityRole="summary">
    <Text style={{ color: "#fff" }}>{message}</Text>
    {status && <Text style={{ color: "#bbb", marginTop: 4 }}>{t("offlineStatus.counts", {
      pending: status.pending, failed: status.failed, review: status.review,
    })}</Text>}
    {state !== "opening" && state !== "needs_auth" && <TouchableOpacity accessibilityRole="button"
      onPress={session ? requestSync : retryOpen} style={{ marginTop: 8 }}>
      <Text style={{ color: "#b6aaff" }}>{t(session ? "offlineStatus.syncNow" : "offlineStatus.retry")}</Text>
    </TouchableOpacity>}
  </View>;
}

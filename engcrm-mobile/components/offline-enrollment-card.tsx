import { useState } from "react";
import { Alert, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { useOffline } from "../services/offline-context";
import { activateOfflineStorage } from "../services/offline-enrollment";

export function OfflineEnrollmentCard() {
  const { t } = useTranslation();
  const offline = useOffline();
  const [busy, setBusy] = useState(false);
  if (offline.state !== "disabled") return null;
  async function activate() {
    if (busy) return;
    setBusy(true);
    try {
      await activateOfflineStorage();
      offline.retryOpen();
    } catch {
      Alert.alert(t("offlineEnrollment.unavailableTitle"), t("offlineEnrollment.unavailableMessage"));
    } finally {
      setBusy(false);
    }
  }
  return <View style={styles.card}>
    <Text style={styles.label}>{t("offlineEnrollment.description")}</Text>
    <TouchableOpacity accessibilityRole="button" disabled={busy} onPress={activate}>
      <Text style={styles.action}>{t("offlineEnrollment.enable")}</Text>
    </TouchableOpacity>
  </View>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#1a1a2e", borderRadius: 12, padding: 18, marginBottom: 24, borderWidth: 1, borderColor: "#ffffff20" },
  label: { color: "#bbb", fontSize: 13, marginBottom: 8 },
  action: { color: "#b6aaff", fontSize: 15, fontWeight: "600" },
});

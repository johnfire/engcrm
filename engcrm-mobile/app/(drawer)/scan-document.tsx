import { useCallback, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Image } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useDocumentCapture } from "../../hooks/useDocumentCapture";
import { flush, pendingCount } from "../../services/cardQueue";
import { useTranslation } from "../../i18n/I18nContext";

export default function ScanDocumentScreen() {
  const { busy, preview, pickAndUpload } = useDocumentCapture();
  const { t } = useTranslation();
  const router = useRouter();
  const [pending, setPending] = useState(0);
  const retry = useCallback(async () => {
    const queue = await flush().catch(() => null);
    setPending(queue ? queue.remaining : await pendingCount().catch(() => 0));
  }, []);
  useFocusEffect(useCallback(() => { void retry(); }, [retry]));

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>{t("documentCapture.hint")}</Text>
      {busy ? <View style={styles.center}>
        {preview && <Image source={{ uri: preview }} style={styles.preview} resizeMode="contain" />}
        <ActivityIndicator color="#7c6fff" size="large" />
        <Text style={styles.hint}>{t("documentCapture.reading")}</Text>
      </View> : <View style={styles.actions}>
        <TouchableOpacity accessibilityRole="button" style={styles.primary} onPress={() => pickAndUpload("camera")}>
          <Text style={styles.label}>{t("capture.takePhoto")}</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button" style={styles.secondary} onPress={() => pickAndUpload("library")}>
          <Text style={styles.label}>{t("capture.chooseLibrary")}</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button" style={styles.secondary} onPress={() => router.push("/(drawer)/card-queue")}>
          <Text style={styles.label}>{t("documentCapture.review")}</Text>
        </TouchableOpacity>
        {pending > 0 && <TouchableOpacity accessibilityRole="button" onPress={retry}>
          <Text style={styles.hint}>{t("documentCapture.pending", { count: pending })}</Text>
        </TouchableOpacity>}
      </View>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 24, justifyContent: "center" },
  hint: { color: "#bbb", fontSize: 15, textAlign: "center", marginBottom: 24 },
  center: { alignItems: "center", gap: 16 },
  preview: { width: 260, height: 320, borderRadius: 10 },
  actions: { gap: 16 },
  primary: { backgroundColor: "#7c6fff", borderRadius: 12, padding: 18, alignItems: "center" },
  secondary: { backgroundColor: "#1a1a2e", borderRadius: 12, padding: 18, alignItems: "center" },
  label: { color: "#fff", fontSize: 16, fontWeight: "600" },
});

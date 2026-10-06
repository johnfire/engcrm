import { useState, useCallback, useEffect } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Image,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { flush, pendingCount } from "../../services/cardQueue";
import { useContactCapture } from "../../hooks/useContactCapture";
import { useTranslation } from "../../i18n/I18nContext";

export default function CaptureScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { busy, preview, pickAndUpload } = useContactCapture();
  const [pending, setPending] = useState(0);

  useEffect(() => {
    if (!busy) void pendingCount().then(setPending).catch(() => undefined);
  }, [busy]);

  // On entering the screen, retry any captures queued while offline.
  useFocusEffect(
    useCallback(() => {
      let active = true;
      (async () => {
        const res = await flush().catch(() => null);
        const count = res ? res.remaining : await pendingCount().catch(() => 0);
        if (active) setPending(count);
      })();
      return () => {
        active = false;
      };
    }, []),
  );

  async function retryNow() {
    const res = await flush().catch(() => null);
    setPending(res ? res.remaining : await pendingCount().catch(() => 0));
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>{t("capture.hint")}</Text>
      {pending > 0 && !busy && (
        <TouchableOpacity style={styles.pendingBanner} onPress={retryNow}>
          <Text style={styles.pendingText}>{t("capture.pending", { count: pending })}</Text>
        </TouchableOpacity>
      )}
      {busy ? (
        <View style={styles.center}>
          {preview && <Image source={{ uri: preview }} style={styles.preview} resizeMode="contain" />}
          <ActivityIndicator color="#7c6fff" size="large" />
          <Text style={styles.busyText}>{t("capture.reading")}</Text>
        </View>
      ) : (
        <View style={styles.actions}>
          <TouchableOpacity accessibilityRole="button" style={styles.primary} onPress={() => pickAndUpload("camera")}>
            <Text style={styles.primaryText}>{t("capture.takePhoto")}</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="button" style={styles.secondary} onPress={() => pickAndUpload("library")}>
            <Text style={styles.secondaryText}>{t("capture.chooseLibrary")}</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityRole="button" style={styles.secondary} onPress={() => router.push("/(drawer)/scan-document")}>
            <Text style={styles.secondaryText}>{t("capture.multipleContacts")}</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 24, justifyContent: "center" },
  hint: { color: "#888", fontSize: 15, textAlign: "center", marginBottom: 24 },
  pendingBanner: {
    backgroundColor: "#2a2440",
    borderColor: "#7c6fff",
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
    marginBottom: 20,
  },
  pendingText: { color: "#b9adff", fontSize: 13, textAlign: "center", fontWeight: "600" },
  actions: { gap: 16 },
  primary: { backgroundColor: "#7c6fff", borderRadius: 12, padding: 18, alignItems: "center" },
  primaryText: { color: "#fff", fontSize: 17, fontWeight: "600" },
  secondary: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 18,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  secondaryText: { color: "#ccc", fontSize: 16, fontWeight: "500" },
  center: { alignItems: "center", gap: 16 },
  preview: { width: 240, height: 150, borderRadius: 10, marginBottom: 8 },
  busyText: { color: "#888", fontSize: 14 },
});

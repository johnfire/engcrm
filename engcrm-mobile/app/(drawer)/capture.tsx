import { useState, useCallback } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Image,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { captureCard } from "../../services/api";
import { enqueue, flush, pendingCount } from "../../services/cardQueue";
import { setHandoff } from "../../services/handoff";
import { useTranslation } from "../../i18n/I18nContext";

export default function CaptureScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [pending, setPending] = useState(0);

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

  async function pickAndUpload(source: "camera" | "library") {
    let smallUri: string | null = null;
    try {
      if (source === "camera") {
        const perm = await ImagePicker.requestCameraPermissionsAsync();
        if (!perm.granted) {
          Alert.alert(t("capture.cameraPermissionTitle"), t("capture.cameraPermissionMessage"));
          return;
        }
      }
      const picked =
        source === "camera"
          ? await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], allowsEditing: true, quality: 1 })
          : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsEditing: true, quality: 1 });
      if (picked.canceled || !picked.assets?.length) return;

      setBusy(true);
      const raw = picked.assets[0].uri;
      setPreview(raw);
      const small = await manipulateAsync(raw, [{ resize: { width: 1280 } }], {
        compress: 0.7,
        format: SaveFormat.JPEG,
      });
      smallUri = small.uri;
      const capture = await captureCard(small.uri);
      if (!capture.is_card) {
        Alert.alert(
          t("capture.couldntReadTitle"),
          capture.fields?.note || capture.fields?.error || t("capture.notACardMessage"),
        );
        return;
      }
      setHandoff("card", capture);
      router.push("/(drawer)/card-confirm");
    } catch (error: any) {
      // No response object → network/connection failure: save it so it isn't lost.
      if (smallUri && !error?.response) {
        try {
          await enqueue(smallUri);
          setPending(await pendingCount());
          Alert.alert(t("capture.savedOfflineTitle"), t("capture.savedOfflineMessage"));
        } catch {
          Alert.alert(t("capture.uploadFailedTitle"), t("capture.uploadFailedGeneric"));
        }
      } else {
        Alert.alert(
          t("capture.uploadFailedTitle"),
          error?.response
            ? t("common.serverError", { status: error.response.status })
            : t("capture.uploadFailedProcess"),
        );
      }
    } finally {
      setBusy(false);
      setPreview(null);
    }
  }

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
          <TouchableOpacity style={styles.primary} onPress={() => pickAndUpload("camera")}>
            <Text style={styles.primaryText}>{t("capture.takePhoto")}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondary} onPress={() => pickAndUpload("library")}>
            <Text style={styles.secondaryText}>{t("capture.chooseLibrary")}</Text>
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

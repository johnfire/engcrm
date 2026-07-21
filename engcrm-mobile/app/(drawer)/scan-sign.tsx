import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Image,
} from "react-native";
import { useRouter } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { captureSign } from "../../services/api";
import { setHandoff } from "../../services/handoff";

// Unlike capture.tsx (business cards), this screen has no offline queue —
// a sign scan needs a live GPS fix and an immediate Places lookup to be
// useful, so an offline retry queue would mostly just accumulate stale scans.
// If that turns out to matter in the field, port the same enqueue/flush
// pattern capture.tsx uses.
export default function ScanSignScreen() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  async function getGps(): Promise<{ lat: number; lng: number } | undefined> {
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) return undefined;
      const position = await Location.getCurrentPositionAsync({});
      return { lat: position.coords.latitude, lng: position.coords.longitude };
    } catch {
      // GPS is best-effort — resolve_business still works from the name alone,
      // just less precisely, and the confirm screen lets the user reject a bad match.
      return undefined;
    }
  }

  async function pickAndUpload(source: "camera" | "library") {
    try {
      if (source === "camera") {
        const perm = await ImagePicker.requestCameraPermissionsAsync();
        if (!perm.granted) {
          Alert.alert("Camera permission needed", "Enable camera access to scan signs.");
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
      const [small, gps] = await Promise.all([
        manipulateAsync(raw, [{ resize: { width: 1280 } }], { compress: 0.7, format: SaveFormat.JPEG }),
        getGps(),
      ]);
      const capture = await captureSign(small.uri, gps);
      if (!capture.is_sign) {
        Alert.alert(
          "Couldn't read that",
          capture.fields?.note ||
            capture.fields?.error ||
            "That doesn't look like a business sign. Try again with the sign more centered.",
        );
        return;
      }
      setHandoff("sign", capture);
      router.push("/(drawer)/sign-confirm");
    } catch (error: any) {
      Alert.alert(
        "Upload failed",
        error?.response ? `Server error (${error.response.status}). Try again.` : "Could not process the sign. Try again.",
      );
    } finally {
      setBusy(false);
      setPreview(null);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>
        Snap a storefront sign — we'll look up the business and research it.
      </Text>
      {busy ? (
        <View style={styles.center}>
          {preview && <Image source={{ uri: preview }} style={styles.preview} resizeMode="contain" />}
          <ActivityIndicator color="#7c6fff" size="large" />
          <Text style={styles.busyText}>Reading the sign…</Text>
        </View>
      ) : (
        <View style={styles.actions}>
          <TouchableOpacity style={styles.primary} onPress={() => pickAndUpload("camera")}>
            <Text style={styles.primaryText}>📷  Take photo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondary} onPress={() => pickAndUpload("library")}>
            <Text style={styles.secondaryText}>🖼  Choose from library</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 24, justifyContent: "center" },
  hint: { color: "#888", fontSize: 15, textAlign: "center", marginBottom: 24 },
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

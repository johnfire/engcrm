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
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { captureCard } from "../../services/api";

export default function CaptureScreen() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  async function pickAndUpload(source: "camera" | "library") {
    try {
      if (source === "camera") {
        const perm = await ImagePicker.requestCameraPermissionsAsync();
        if (!perm.granted) {
          Alert.alert("Camera permission needed", "Enable camera access to scan cards.");
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
      // Downscale before upload — keeps the request small and the vision tokens (cost) low.
      const small = await manipulateAsync(raw, [{ resize: { width: 1280 } }], {
        compress: 0.7,
        format: SaveFormat.JPEG,
      });
      const capture = await captureCard(small.uri);
      if (!capture.is_card) {
        Alert.alert(
          "Couldn't read that",
          capture.fields?.note ||
            capture.fields?.error ||
            "That doesn't look like a business card. Try again with better lighting.",
        );
        return;
      }
      router.push({
        pathname: "/(drawer)/card-confirm",
        params: { data: JSON.stringify(capture) },
      });
    } catch (e: any) {
      Alert.alert(
        "Upload failed",
        e?.message ? String(e.message) : "Could not process the card. Check your connection and try again.",
      );
    } finally {
      setBusy(false);
      setPreview(null);
    }
  }

  return (
    <View style={s.container}>
      <Text style={s.hint}>Snap a business card — it gets read and turned into a lead.</Text>
      {busy ? (
        <View style={s.center}>
          {preview && <Image source={{ uri: preview }} style={s.preview} resizeMode="contain" />}
          <ActivityIndicator color="#7c6fff" size="large" />
          <Text style={s.busyText}>Reading the card…</Text>
        </View>
      ) : (
        <View style={s.actions}>
          <TouchableOpacity style={s.primary} onPress={() => pickAndUpload("camera")}>
            <Text style={s.primaryText}>📷  Take photo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.secondary} onPress={() => pickAndUpload("library")}>
            <Text style={s.secondaryText}>🖼  Choose from library</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 24, justifyContent: "center" },
  hint: { color: "#888", fontSize: 15, textAlign: "center", marginBottom: 32 },
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

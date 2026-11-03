import { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Image,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";
import { captureSign } from "../../services/api";
import { setHandoff } from "../../services/handoff";
import { useTranslation } from "../../i18n/I18nContext";

// Unlike capture.tsx (business cards), this screen has no offline queue —
// a sign scan needs a live GPS fix and an immediate Places lookup to be
// useful, so an offline retry queue would mostly just accumulate stale scans.
// If that turns out to matter in the field, port the same enqueue/flush
// pattern capture.tsx uses.

// The town is typed once and kept for the next photo: a run of signs is
// usually all in one town. Stored per device; losing it only means retyping.
const TOWN_KEY = "scanSign.town";
// A fresh GPS fix can take minutes indoors or in a car, and the upload waits
// for it. Past this, fall back to the last known position (or none).
const GPS_TIMEOUT_MS = 10000;
const LAST_KNOWN_MAX_AGE_MS = 5 * 60 * 1000;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), ms);
    promise.then(
      (value) => { clearTimeout(timer); resolve(value); },
      () => { clearTimeout(timer); resolve(null); },
    );
  });
}

export default function ScanSignScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [town, setTown] = useState("");

  useEffect(() => {
    AsyncStorage.getItem(TOWN_KEY)
      .then((saved) => { if (saved) setTown((current) => current || saved); })
      .catch(() => {});
  }, []);

  function changeTown(value: string) {
    setTown(value);
    AsyncStorage.setItem(TOWN_KEY, value).catch(() => {});
  }

  async function getGps(): Promise<{ lat: number; lng: number } | undefined> {
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) return undefined;
      const position =
        (await withTimeout(Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }), GPS_TIMEOUT_MS)) ??
        (await Location.getLastKnownPositionAsync({ maxAge: LAST_KNOWN_MAX_AGE_MS }));
      if (!position) return undefined;
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
          Alert.alert(t("capture.cameraPermissionTitle"), t("scanSign.cameraPermissionMessage"));
          return;
        }
      }
      const picked =
        source === "camera"
          ? await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], allowsEditing: false, quality: 1 })
          : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsEditing: false, quality: 1 });
      if (picked.canceled || !picked.assets?.length) return;

      setBusy(true);
      const raw = picked.assets[0].uri;
      setPreview(raw);
      const [small, gps] = await Promise.all([
        manipulateAsync(raw, [{ resize: { width: 1280 } }], { compress: 0.7, format: SaveFormat.JPEG }),
        source === "camera" ? getGps() : Promise.resolve(undefined),
      ]);
      // A typed town is a location hint too, so only warn when there is neither.
      if (!gps && !town.trim()) Alert.alert(t("scanSign.locationUnavailableTitle"),
        t(source === "camera" ? "scanSign.locationUnavailableMessage" : "scanSign.libraryNoTownMessage"));
      const capture = await captureSign(small.uri, gps, town);
      if (!capture.is_sign) {
        Alert.alert(
          t("scanSign.couldntReadTitle"),
          capture.fields?.note || capture.fields?.error || t("scanSign.notASignMessage"),
        );
        return;
      }
      setHandoff("sign", capture);
      router.push("/(drawer)/sign-confirm");
    } catch (error: any) {
      Alert.alert(
        t("scanSign.uploadFailedTitle"),
        error?.response
          ? t("common.serverError", { status: error.response.status })
          : t("scanSign.uploadFailedProcess"),
      );
    } finally {
      setBusy(false);
      setPreview(null);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>{t("scanSign.hint")}</Text>
      <Text style={styles.townLabel}>{t("scanSign.town")}</Text>
      <TextInput
        style={styles.townInput}
        value={town}
        onChangeText={changeTown}
        placeholder={t("scanSign.townPlaceholder")}
        placeholderTextColor="#555"
        autoCorrect={false}
        editable={!busy}
        accessibilityLabel={t("scanSign.town")}
      />
      {busy ? (
        <View style={styles.center}>
          {preview && <Image source={{ uri: preview }} style={styles.preview} resizeMode="contain" />}
          <ActivityIndicator color="#7c6fff" size="large" />
          <Text style={styles.busyText}>{t("scanSign.reading")}</Text>
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
  townLabel: { color: "#888", fontSize: 12, marginBottom: 4, marginLeft: 2 },
  townInput: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    padding: 14,
    fontSize: 15,
    borderWidth: 1,
    borderColor: "#ffffff20",
    marginBottom: 24,
  },
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

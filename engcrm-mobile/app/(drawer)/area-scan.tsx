import { useCallback, useRef, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  Platform,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import * as Location from "expo-location";
import { AppleMaps, GoogleMaps } from "expo-maps";
import Slider from "@react-native-community/slider";
import { scanArea } from "../../services/api";
import { useTranslation } from "../../i18n/I18nContext";

const LEVELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
// Matches pipeline.py's _MAX_AREA_LEVELS — the backend rejects a scan over this,
// so the default selection must already fit under it.
const MAX_LEVELS_PER_SCAN = 6;
const MIN_RADIUS_M = 100;
const MAX_RADIUS_M = 2000;
const DEFAULT_CENTER = { latitude: 48.3705, longitude: 10.8978 }; // Augsburg — used only until GPS resolves

export default function AreaScanScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const mapRef = useRef<any>(null);

  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [radiusM, setRadiusM] = useState(500);
  const [label, setLabel] = useState("");
  const [selectedLevels, setSelectedLevels] = useState<number[]>(LEVELS.slice(0, MAX_LEVELS_PER_SCAN));
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(true);

  const locateMe = useCallback(async () => {
    setLocating(true);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(t("areaScan.locationPermissionTitle"), t("areaScan.locationPermissionMessage"));
        return;
      }
      const position = await Location.getCurrentPositionAsync({});
      const next = { latitude: position.coords.latitude, longitude: position.coords.longitude };
      setCenter(next);
      mapRef.current?.setCameraPosition?.({ coordinates: next, zoom: 15 });
    } catch (error: any) {
      Alert.alert(t("areaScan.locationPermissionTitle"), error?.message || t("common.tryAgain"));
    } finally {
      setLocating(false);
    }
  }, [t]);

  // GPS fallback: resolve device location as soon as the screen opens, so
  // there's always a sensible starting point even if the user never taps the map.
  useFocusEffect(
    useCallback(() => {
      locateMe();
    }, [locateMe]),
  );

  function toggleLevel(level: number) {
    setSelectedLevels((current) => {
      if (current.includes(level)) return current.filter((value) => value !== level);
      if (current.length >= MAX_LEVELS_PER_SCAN) {
        Alert.alert(t("areaScan.tooManyLevelsTitle"), t("areaScan.tooManyLevelsMessage", { max: MAX_LEVELS_PER_SCAN }));
        return current;
      }
      return [...current, level];
    });
  }

  function onMapClick(event: { coordinates: { latitude?: number; longitude?: number } }) {
    const { latitude, longitude } = event.coordinates;
    if (latitude == null || longitude == null) return;
    setCenter({ latitude, longitude });
  }

  async function submitScan() {
    if (!selectedLevels.length) {
      Alert.alert(t("areaScan.levelRequiredTitle"), t("areaScan.levelRequiredMessage"));
      return;
    }
    setBusy(true);
    try {
      const result = await scanArea({
        lat: center.latitude,
        lon: center.longitude,
        radius_m: Math.round(radiusM),
        levels: selectedLevels,
        label: label.trim(),
      });
      Alert.alert(t("areaScan.queuedTitle"), t("areaScan.queuedMessage"));
      router.push({ pathname: "/(drawer)/area-results", params: { areaId: String(result.area_id) } });
    } catch (error: any) {
      Alert.alert(
        t("areaScan.couldntStartTitle"),
        error?.response?.data?.detail || error?.message || t("common.tryAgain"),
      );
    } finally {
      setBusy(false);
    }
  }

  const circles = [
    { center, radius: radiusM, color: "#7c6fff33", lineColor: "#7c6fff", lineWidth: 2 },
  ];
  const cameraPosition = { coordinates: center, zoom: 15 };

  return (
    <View style={styles.container}>
      <View style={styles.mapWrap}>
        {Platform.OS === "ios" ? (
          <AppleMaps.View
            ref={mapRef}
            style={styles.map}
            cameraPosition={cameraPosition}
            circles={circles}
            onMapClick={onMapClick}
          />
        ) : (
          <GoogleMaps.View
            ref={mapRef}
            style={styles.map}
            cameraPosition={cameraPosition}
            circles={circles}
            onMapClick={onMapClick}
          />
        )}
        <TouchableOpacity style={styles.locateBtn} onPress={locateMe} disabled={locating}>
          <Text style={styles.locateText}>{locating ? t("areaScan.locating") : t("areaScan.useMyLocation")}</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.controls}>
        <Text style={styles.hint}>{t("areaScan.tapMapHint")}</Text>

        <View style={styles.row}>
          <Text style={styles.label}>{t("areaScan.radius", { meters: Math.round(radiusM) })}</Text>
        </View>
        <Slider
          minimumValue={MIN_RADIUS_M}
          maximumValue={MAX_RADIUS_M}
          step={50}
          value={radiusM}
          onValueChange={setRadiusM}
          minimumTrackTintColor="#7c6fff"
          maximumTrackTintColor="#ffffff30"
          thumbTintColor="#7c6fff"
        />

        <Text style={styles.label}>{t("areaScan.levels")}</Text>
        <View style={styles.levelRow}>
          {LEVELS.map((level) => (
            <TouchableOpacity
              key={level}
              style={[styles.levelChip, selectedLevels.includes(level) && styles.levelChipActive]}
              onPress={() => toggleLevel(level)}
            >
              <Text style={[styles.levelText, selectedLevels.includes(level) && styles.levelTextActive]}>
                L{level}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <TextInput
          style={styles.input}
          placeholder={t("areaScan.labelPlaceholder")}
          placeholderTextColor="#555"
          value={label}
          onChangeText={setLabel}
        />

        <TouchableOpacity style={[styles.scanBtn, busy && styles.btnBusy]} onPress={submitScan} disabled={busy}>
          <Text style={styles.scanText}>{busy ? t("areaScan.scanning") : t("areaScan.scan")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  mapWrap: { flex: 1 },
  map: { flex: 1 },
  locateBtn: {
    position: "absolute",
    top: 16,
    right: 16,
    backgroundColor: "#1a1a2eee",
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: "#7c6fff55",
  },
  locateText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  controls: { padding: 20, backgroundColor: "#1a1a2e" },
  hint: { color: "#888", fontSize: 12, marginBottom: 12 },
  row: { flexDirection: "row", justifyContent: "space-between" },
  label: {
    color: "#888",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: 8,
    marginTop: 12,
  },
  levelRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  levelChip: {
    backgroundColor: "#ffffff10",
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  levelChipActive: { backgroundColor: "#7c6fff" },
  levelText: { color: "#888", fontSize: 13, fontWeight: "700" },
  levelTextActive: { color: "#fff" },
  input: {
    backgroundColor: "#0f0f23",
    color: "#fff",
    borderRadius: 10,
    padding: 12,
    fontSize: 15,
    borderWidth: 1,
    borderColor: "#ffffff20",
    marginTop: 12,
  },
  scanBtn: {
    backgroundColor: "#7c6fff",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 16,
  },
  btnBusy: { opacity: 0.6 },
  scanText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});

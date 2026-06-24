import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from "react-native";
import { runResearch } from "../../services/api";

const LEVELS = [1, 2, 3, 4, 5];
const COUNTRIES = [
  { code: "DE", label: "Germany" },
  { code: "AT", label: "Austria" },
];

export default function ResearchScreen() {
  const [city, setCity] = useState("");
  const [level, setLevel] = useState(1);
  const [country, setCountry] = useState("DE");
  const [loading, setLoading] = useState(false);

  async function handleRun() {
    if (!city.trim()) {
      Alert.alert("City required", "Please enter a city name.");
      return;
    }
    setLoading(true);
    try {
      await runResearch(city.trim(), level, country);
      Alert.alert(
        "Scan queued",
        `Level ${level} scan for ${city} has started.`,
      );
      setCity("");
    } catch {
      Alert.alert("Error", "Could not start scan. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.label}>City</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. München"
        placeholderTextColor="#555"
        value={city}
        onChangeText={setCity}
        autoCapitalize="words"
      />

      <Text style={styles.label}>Level</Text>
      <View style={styles.row}>
        {LEVELS.map((levelOption) => (
          <TouchableOpacity
            key={levelOption}
            style={[styles.levelBtn, level === levelOption && styles.levelBtnActive]}
            onPress={() => setLevel(levelOption)}
          >
            <Text style={[styles.levelText, level === levelOption && styles.levelTextActive]}>
              {levelOption}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.label}>Country</Text>
      <View style={styles.row}>
        {COUNTRIES.map((countryOption) => (
          <TouchableOpacity
            key={countryOption.code}
            style={[styles.countryBtn, country === countryOption.code && styles.levelBtnActive]}
            onPress={() => setCountry(countryOption.code)}
          >
            <Text
              style={[styles.levelText, country === countryOption.code && styles.levelTextActive]}
            >
              {countryOption.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity style={styles.runBtn} onPress={handleRun} disabled={loading}>
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.runText}>Run Scan</Text>
        )}
      </TouchableOpacity>

      <Text style={styles.hint}>Results appear in the Activity screen.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 24 },
  label: {
    color: "#888",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: 10,
    marginTop: 20,
  },
  input: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    padding: 14,
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  row: { flexDirection: "row", gap: 10, flexWrap: "wrap" },
  levelBtn: {
    backgroundColor: "#ffffff10",
    borderRadius: 10,
    width: 48,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  levelBtnActive: { backgroundColor: "#7c6fff" },
  levelText: { color: "#888", fontSize: 16, fontWeight: "700" },
  levelTextActive: { color: "#fff" },
  countryBtn: {
    backgroundColor: "#ffffff10",
    borderRadius: 10,
    paddingHorizontal: 20,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  runBtn: {
    marginTop: 36,
    backgroundColor: "#7c6fff",
    borderRadius: 12,
    padding: 18,
    alignItems: "center",
  },
  runText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  hint: { color: "#555", fontSize: 12, textAlign: "center", marginTop: 16 },
});

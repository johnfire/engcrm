import { useEffect, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { clearToken, getRole } from "../../services/auth";

export default function SettingsScreen() {
  const router = useRouter();
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    getRole().then(setRole);
  }, []);

  async function handleLogout() {
    await clearToken();
    router.replace("/login");
  }

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.label}>Signed in as</Text>
        <Text style={styles.value}>{role || "—"}</Text>
      </View>
      <TouchableOpacity style={styles.logout} onPress={handleLogout}>
        <Text style={styles.logoutText}>Log out</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 24 },
  card: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 18,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  label: { color: "#888", fontSize: 12, marginBottom: 4 },
  value: { color: "#fff", fontSize: 16, fontWeight: "600" },
  logout: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#ef444455",
  },
  logoutText: { color: "#ef4444", fontSize: 16, fontWeight: "600" },
});

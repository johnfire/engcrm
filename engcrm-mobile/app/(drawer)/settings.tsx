import { useEffect, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, Linking, Alert } from "react-native";
import { useRouter } from "expo-router";
import { AiBackends, API_BASE, fetchAiBackends, updateAiBackends, updateLanguage } from "../../services/api";
import { clearToken, getRole } from "../../services/auth";
import { useTranslation } from "../../i18n/I18nContext";
import { Language, SUPPORTED_LANGUAGES } from "../../i18n/translate";

// Language names are shown in their own language regardless of the current
// UI language — the whole point of a language picker is to stay legible to
// someone who doesn't yet read the active one.
const LANGUAGE_NAMES: Record<Language, string> = { en: "English", de: "Deutsch" };

export default function SettingsScreen() {
  const router = useRouter();
  const { t, language, setLanguage } = useTranslation();
  const [role, setRole] = useState<string | null>(null);
  const [savingLanguage, setSavingLanguage] = useState(false);
  const [aiBackends, setAiBackends] = useState<AiBackends | null>(null);

  useEffect(() => {
    getRole().then(setRole);
    fetchAiBackends().then(setAiBackends).catch(() => undefined);
  }, []);

  async function selectRoutineBackend(cheap_llm: AiBackends["cheap_llm"]) {
    if (!aiBackends) return;
    const previous = aiBackends;
    const next = { ...aiBackends, cheap_llm };
    setAiBackends(next);
    try { await updateAiBackends(next); } catch { setAiBackends(previous); }
  }

  async function handleLogout() {
    await clearToken();
    router.replace("/login");
  }

  async function handleLanguageChange(next: Language) {
    if (next === language || savingLanguage) return;
    const previous = language;
    setLanguage(next); // apply immediately, revert on failure
    setSavingLanguage(true);
    try {
      await updateLanguage(next);
    } catch {
      setLanguage(previous);
      Alert.alert(t("settings.languageUpdateFailedTitle"), t("settings.languageUpdateFailedMessage"));
    } finally {
      setSavingLanguage(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.label}>{t("settings.signedInAs")}</Text>
        <Text style={styles.value}>{role || "—"}</Text>
      </View>
      {role === "admin" && aiBackends && <View style={styles.card}>
        <Text style={styles.label}>{t("settings.aiBackend")}</Text>
        <View style={styles.languageRow}>
          {(["deepseek-v4-flash", "claude-haiku"] as const).map((model) => (
            <TouchableOpacity key={model} style={[styles.languageBtn, aiBackends.cheap_llm === model && styles.languageBtnActive]} onPress={() => selectRoutineBackend(model)}>
              <Text style={[styles.languageText, aiBackends.cheap_llm === model && styles.languageTextActive]}>{model}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>}
      <View style={styles.card}>
        <Text style={styles.label}>{t("settings.language")}</Text>
        <View style={styles.languageRow}>
          {SUPPORTED_LANGUAGES.map((code) => (
            <TouchableOpacity
              key={code}
              style={[styles.languageBtn, language === code && styles.languageBtnActive]}
              onPress={() => handleLanguageChange(code)}
              disabled={savingLanguage}
            >
              <Text style={[styles.languageText, language === code && styles.languageTextActive]}>
                {LANGUAGE_NAMES[code]}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
      <TouchableOpacity style={styles.logout} onPress={handleLogout}>
        <Text style={styles.logoutText}>{t("settings.logout")}</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.impressum}
        onPress={() => Linking.openURL(`${API_BASE}/impressum`)}
      >
        <Text style={styles.impressumText}>{t("settings.impressum")}</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.privacy}
        onPress={() => Linking.openURL(`${API_BASE}/privacy`)}
      >
        <Text style={styles.impressumText}>{t("settings.privacy")}</Text>
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
  languageRow: { flexDirection: "row", gap: 10, marginTop: 8 },
  languageBtn: {
    flex: 1,
    backgroundColor: "#ffffff10",
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: "center",
  },
  languageBtnActive: { backgroundColor: "#7c6fff" },
  languageText: { color: "#888", fontSize: 14, fontWeight: "600" },
  languageTextActive: { color: "#fff" },
  logout: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#ef444455",
  },
  logoutText: { color: "#ef4444", fontSize: 16, fontWeight: "600" },
  impressum: { marginTop: 24, alignItems: "center" },
  privacy: { marginTop: 8, alignItems: "center" },
  impressumText: { color: "#555", fontSize: 12 },
});

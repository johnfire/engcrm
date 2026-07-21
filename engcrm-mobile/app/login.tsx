import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Linking,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { API_BASE, fetchMe, login } from "../services/api";
import { saveToken } from "../services/auth";
import { useTranslation } from "../i18n/I18nContext";
import { isSupportedLanguage } from "../i18n/translate";

export default function LoginScreen() {
  const router = useRouter();
  const { t, setLanguage } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    if (!email.trim() || !password.trim()) return;
    setLoading(true);
    try {
      const { token, role } = await login(email.trim(), password.trim());
      await saveToken(token, role);
      // Best-effort — apply the account's language immediately rather than
      // waiting for the next foreground/cold-start sync cycle.
      try {
        const me = await fetchMe();
        if (isSupportedLanguage(me.ui_language)) setLanguage(me.ui_language);
      } catch {
        // ignore — falls back to whatever's already cached/active
      }
      router.replace("/(drawer)/contacts");
    } catch {
      Alert.alert(t("login.failedTitle"), t("login.failedMessage"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <Text style={styles.title}>{t("login.title")}</Text>
      <Text style={styles.subtitle}>{t("login.subtitle")}</Text>
      <TextInput
        style={styles.input}
        placeholder={t("login.emailPlaceholder")}
        placeholderTextColor="#555"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        value={email}
        onChangeText={setEmail}
        returnKeyType="next"
        autoFocus
      />
      <View style={styles.pwRow}>
        <TextInput
          style={styles.pwInput}
          placeholder={t("login.passwordPlaceholder")}
          placeholderTextColor="#555"
          secureTextEntry={!showPassword}
          autoCapitalize="none"
          autoCorrect={false}
          textContentType="password"
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={handleLogin}
          returnKeyType="go"
        />
        <TouchableOpacity
          onPress={() => setShowPassword((visible) => !visible)}
          style={styles.eyeBtn}
          accessibilityLabel={showPassword ? "Hide password" : "Show password"}
        >
          <Text style={styles.eyeText}>{showPassword ? "🙈" : "👁️"}</Text>
        </TouchableOpacity>
      </View>
      <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={loading}>
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>{t("login.signIn")}</Text>
        )}
      </TouchableOpacity>
      <TouchableOpacity style={styles.forgot} onPress={() => router.push("/forgot-password")}>
        <Text style={styles.forgotText}>{t("login.forgotPassword")}</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.impressum} onPress={() => Linking.openURL(`${API_BASE}/impressum`)}>
        <Text style={styles.impressumText}>{t("login.impressum")}</Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0f0f23",
    justifyContent: "center",
    padding: 32,
  },
  title: { fontSize: 32, fontWeight: "700", color: "#fff", marginBottom: 8 },
  subtitle: { fontSize: 16, color: "#888", marginBottom: 40 },
  input: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    padding: 16,
    fontSize: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  pwRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  pwInput: { flex: 1, color: "#fff", padding: 16, fontSize: 16 },
  eyeBtn: { paddingHorizontal: 14, paddingVertical: 12 },
  eyeText: { fontSize: 20 },
  button: {
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  forgot: { marginTop: 20, alignItems: "center" },
  forgotText: { color: "#7c6fff", fontSize: 14 },
  impressum: { marginTop: 12, alignItems: "center" },
  impressumText: { color: "#555", fontSize: 12 },
});

import { useState } from "react";
import {
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { requestPasswordReset } from "../services/api";
import { useTranslation } from "../i18n/I18nContext";

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSend() {
    if (!email.trim()) return;
    setLoading(true);
    try {
      await requestPasswordReset(email.trim());
    } catch {
      // The backend never errors on a genuine request — treat any failure
      // (e.g. offline) the same as success, so we never leak account state.
    } finally {
      setLoading(false);
      setSent(true);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <Text style={styles.title}>{t("forgotPassword.title")}</Text>
      {sent ? (
        <Text style={styles.hint}>{t("forgotPassword.sentMessage")}</Text>
      ) : (
        <>
          <Text style={styles.hint}>{t("forgotPassword.hint")}</Text>
          <TextInput
            style={styles.input}
            placeholder={t("login.emailPlaceholder")}
            placeholderTextColor="#555"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            value={email}
            onChangeText={setEmail}
            onSubmitEditing={handleSend}
            returnKeyType="go"
            autoFocus
          />
          <TouchableOpacity style={styles.button} onPress={handleSend} disabled={loading}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{t("forgotPassword.submit")}</Text>}
          </TouchableOpacity>
        </>
      )}
      <TouchableOpacity style={styles.back} onPress={() => router.replace("/login")}>
        <Text style={styles.backText}>{t("forgotPassword.backToSignIn")}</Text>
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
  title: { fontSize: 24, fontWeight: "700", color: "#fff", marginBottom: 12 },
  hint: { fontSize: 14, color: "#888", marginBottom: 24, lineHeight: 20 },
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
  button: {
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  back: { marginTop: 24, alignItems: "center" },
  backText: { color: "#7c6fff", fontSize: 14 },
});

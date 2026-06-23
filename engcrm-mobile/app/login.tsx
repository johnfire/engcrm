import { useState } from "react";
import {
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { login } from "../services/api";
import { saveToken } from "../services/auth";

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    if (!email.trim() || !password.trim()) return;
    setLoading(true);
    try {
      const { token, role } = await login(email.trim(), password.trim());
      await saveToken(token, role);
      router.replace("/(drawer)/approvals");
    } catch {
      Alert.alert("Login failed", "Wrong email or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={s.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <Text style={s.title}>EngCRM</Text>
      <Text style={s.subtitle}>Sign in to continue</Text>
      <TextInput
        style={s.input}
        placeholder="Email"
        placeholderTextColor="#555"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        value={email}
        onChangeText={setEmail}
        returnKeyType="next"
        autoFocus
      />
      <TextInput
        style={s.input}
        placeholder="Password"
        placeholderTextColor="#555"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
        onSubmitEditing={handleLogin}
        returnKeyType="go"
      />
      <TouchableOpacity
        style={s.button}
        onPress={handleLogin}
        disabled={loading}
      >
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={s.buttonText}>Sign In</Text>
        )}
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
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
  button: {
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});

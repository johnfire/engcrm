import { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { useTranslation } from "../i18n/I18nContext";
import { getRole } from "../services/auth";

export function AddBusinessButton() {
  const { t } = useTranslation();
  const router = useRouter();
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    let active = true;
    getRole().then((role) => { if (active) setIsAdmin(role === "admin"); }).catch(() => {});
    return () => { active = false; };
  }, []);
  if (!isAdmin) return null;
  return <TouchableOpacity style={styles.button} accessibilityRole="button"
    onPress={() => router.push({ pathname: "/(drawer)/edit-organization", params: {} })}>
    <Text style={styles.label}>{t("businessForm.add")}</Text>
  </TouchableOpacity>;
}

const styles = StyleSheet.create({
  button: { alignSelf: "flex-start", backgroundColor: "#7c6fff", borderRadius: 8, margin: 12,
    minHeight: 44, justifyContent: "center", paddingHorizontal: 16 },
  label: { color: "#fff", fontWeight: "700", fontSize: 15 },
});

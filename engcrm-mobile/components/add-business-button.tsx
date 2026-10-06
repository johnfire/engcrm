import { StyleSheet, Text, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { useTranslation } from "../i18n/I18nContext";

export function AddBusinessButton({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const router = useRouter();
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

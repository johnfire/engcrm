import { StyleSheet, Text, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { useTranslation } from "../i18n/I18nContext";
import { ContactKind } from "../services/contact-feed";

export function ContactDateLink({ kind, id }: { kind: ContactKind; id: number }) {
  const { t } = useTranslation();
  const router = useRouter();
  return <TouchableOpacity style={styles.button} accessibilityRole="button"
    onPress={() => router.push({ pathname: "/(drawer)/contact-date", params: { kind, id: String(id) } })}>
    <Text style={styles.label}>{t("contactDate.title")}</Text>
  </TouchableOpacity>;
}

const styles = StyleSheet.create({
  button: { minHeight: 44, justifyContent: "center", paddingVertical: 8 },
  label: { color: "#b9adff", fontSize: 14 },
});

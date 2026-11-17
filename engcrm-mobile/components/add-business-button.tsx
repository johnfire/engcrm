import { StyleSheet, Text, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { useTranslation } from "../i18n/I18nContext";

// The purple "+" beside a list's search box. `label` is what a screen reader says.
export function ListAddButton({ label, onPress }: { label: string; onPress: () => void }) {
  return <TouchableOpacity style={styles.button} onPress={onPress} accessibilityRole="button" accessibilityLabel={label}>
    <Text style={styles.plus}>+</Text>
  </TouchableOpacity>;
}

export function AddBusinessButton({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const router = useRouter();
  if (!isAdmin) return null;
  return <ListAddButton label={t("businessForm.add")}
    onPress={() => router.push({ pathname: "/(drawer)/edit-organization", params: {} })} />;
}

const styles = StyleSheet.create({
  button: { alignItems: "center", backgroundColor: "#7c6fff", borderRadius: 10, justifyContent: "center",
    minHeight: 44, width: 44 },
  plus: { color: "#fff", fontSize: 24, fontWeight: "600", lineHeight: 28 },
});

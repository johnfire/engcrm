import { ActivityIndicator, Alert, Linking, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "../i18n/I18nContext";
import { useCaptureLinkedIn } from "../services/use-capture-linkedin";
import { CardField } from "./CardField";

interface Props {
  captureId: number;
  name: string;
  company: string;
  city: string;
  value?: string | null;
  onChange: (url: string) => void;
  disabled: boolean;
}

export function CaptureLinkedIn({ captureId, name, company, city, value, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const { searching, suggestions, canSearch, retry } = useCaptureLinkedIn(captureId, name, company, city);

  return <View style={styles.section}>
    <CardField label={t("captureLinkedIn.profile")} value={value} onChange={onChange} keyboardType="url" />
    <Text style={styles.hint}>{t("captureLinkedIn.review")}</Text>
    {searching && <View style={styles.loading}>
      <ActivityIndicator color="#7c6fff" /><Text style={styles.hint}>{t("captureLinkedIn.searching")}</Text>
    </View>}
    {suggestions && suggestions.status !== "found" &&
      <Text style={styles.hint}>{t(`captureLinkedIn.${suggestions.status}`)}</Text>}
    {!searching && suggestions?.candidates.map((profile) => <View key={profile.url} style={styles.candidate}>
      <Text style={styles.title}>{profile.title}</Text>
      <Text style={styles.hint}>{profile.snippet}</Text>
      <TouchableOpacity accessibilityRole="link" onPress={() => {
        Linking.openURL(profile.url).catch(() => Alert.alert(t("captureLinkedIn.openFailed")));
      }}>
        <Text style={styles.link}>{profile.url}</Text>
      </TouchableOpacity>
      <TouchableOpacity accessibilityRole="button" disabled={disabled}
        accessibilityState={{ selected: value === profile.url, disabled }}
        onPress={() => onChange(profile.url)} style={styles.button}>
        <Text style={styles.label}>{t(value === profile.url ? "captureLinkedIn.selected" : "captureLinkedIn.useProfile")}</Text>
      </TouchableOpacity>
    </View>)}
    {!searching && canSearch &&
      <TouchableOpacity accessibilityRole="button" disabled={disabled} onPress={retry}>
        <Text style={styles.link}>{t("captureLinkedIn.retry")}</Text>
      </TouchableOpacity>}
  </View>;
}

const styles = StyleSheet.create({
  section: { marginBottom: 16, gap: 8 },
  hint: { color: "#bbb", fontSize: 13 },
  loading: { flexDirection: "row", alignItems: "center", gap: 8 },
  candidate: { backgroundColor: "#1a1a2e", borderRadius: 10, padding: 12, gap: 8 },
  title: { color: "#fff", fontWeight: "600" },
  link: { color: "#b4adff", paddingVertical: 8 },
  button: { backgroundColor: "#7c6fff", borderRadius: 8, padding: 12, alignItems: "center" },
  label: { color: "#fff", fontWeight: "600" },
});

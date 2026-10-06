import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useTranslation } from "../../i18n/I18nContext";
import { ContactKind } from "../../services/contact-feed";
import { dateInDays } from "../../services/followUps";
import { useContactDate } from "../../services/use-contact-date";

export default function ContactDateScreen() {
  const params = useLocalSearchParams<{ kind: string; id: string }>();
  const { t } = useTranslation();
  if (!["person", "organization"].includes(params.kind) || !Number.isInteger(Number(params.id)) || Number(params.id) < 1)
    return <Text style={styles.error}>{t("contactDate.loadFailed")}</Text>;
  return <ContactDateForm kind={params.kind as ContactKind} id={Number(params.id)} />;
}

function ContactDateForm({ kind, id }: { kind: ContactKind; id: number }) {
  const { t } = useTranslation();
  const router = useRouter();
  const editor = useContactDate(kind, id);
  if (editor.isAdmin === false) return <Text style={styles.error}>{t("recordForm.adminOnly")}</Text>;
  if (!editor.record) return editor.error ? <Text style={styles.error}>{editor.error}</Text> : <ActivityIndicator color="#7c6fff" />;
  return <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
    <Text style={styles.heading}>{editor.record.name}</Text>
    <Text style={styles.hint}>{t(editor.record.interaction_id ? "contactDate.hint" : "contactDate.firstHint")}</Text>
    <Text style={styles.label}>{t("contactDate.date")}</Text>
    <TextInput style={styles.input} value={editor.selected} onChangeText={editor.setSelected}
      accessibilityLabel={t("contactDate.date")} placeholder="YYYY-MM-DD" keyboardType="numbers-and-punctuation"
      editable={!editor.saving} maxLength={10} />
    <View style={styles.choices}>
      {[0, -1, -2].map((days) => <TouchableOpacity key={days} style={styles.choice} disabled={editor.saving}
        onPress={() => editor.setSelected(dateInDays(days))} accessibilityRole="button">
        <Text style={styles.label}>{t(days === 0 ? "contactDate.today" : days === -1 ? "contactDate.yesterday" : "contactDate.twoDaysAgo")}</Text>
      </TouchableOpacity>)}
    </View>
    {!!editor.error && <Text style={styles.error} accessibilityRole="alert">{editor.error}</Text>}
    <TouchableOpacity style={styles.save} disabled={editor.saving} accessibilityRole="button"
      onPress={() => { void editor.save().then((saved) => { if (saved) { if (router.canGoBack()) router.back(); else router.replace("/(drawer)/contacts"); } }); }}>
      <Text style={styles.label}>{t(editor.saving ? "common.saving" : "common.save")}</Text>
    </TouchableOpacity>
  </ScrollView>;
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 12, backgroundColor: "#0f0f23", flexGrow: 1 },
  heading: { color: "#fff", fontSize: 22, fontWeight: "600" },
  hint: { color: "#bbb", fontSize: 14 },
  label: { color: "#fff", fontSize: 15 },
  input: { backgroundColor: "#1a1a2e", color: "#fff", padding: 12, borderRadius: 8, fontSize: 18 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: { backgroundColor: "#302953", padding: 12, borderRadius: 8, minHeight: 44 },
  save: { backgroundColor: "#7c6fff", padding: 14, borderRadius: 8, alignItems: "center" },
  error: { color: "#ef8a8a", padding: 12 },
});

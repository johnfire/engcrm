import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { SavedMessageLibrary } from "../../components/saved-message-library";
import { useTranslation } from "../../i18n/I18nContext";
import { fetchPerson, Person } from "../../services/api";

export default function SavedMessagesScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useTranslation();
  const [loaded, setLoaded] = useState<{ id: string; person: Person | null } | null>(null);
  const contact = loaded?.id === id ? loaded.person : null;
  useEffect(() => {
    let active = true;
    fetchPerson(Number(id)).then((person) => { if (active) setLoaded({ id, person }); })
      .catch(() => { if (active) setLoaded({ id, person: null }); });
    return () => { active = false; };
  }, [id]);
  return <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {contact && <Text style={styles.name}>{contact.name}</Text>}
      {loaded?.id === id && !contact && <Text style={styles.hint}>{t("savedMessages.contactFailed")}</Text>}
      <SavedMessageLibrary key={id} profile={contact?.linkedin_url} />
    </ScrollView>
  </KeyboardAvoidingView>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" }, content: { padding: 16, paddingBottom: 48 },
  name: { color: "#fff", fontSize: 20, fontWeight: "600", marginBottom: 16 },
  hint: { color: "#bbb", marginBottom: 16 },
});

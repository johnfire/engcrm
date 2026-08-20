import { useCallback, useState } from "react";
import {
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { confirmVoice, VoiceResult } from "../../services/api";
import { takeHandoff } from "../../services/handoff";
import { useTranslation } from "../../i18n/I18nContext";

export default function VoiceConfirmScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [result, setResult] = useState<VoiceResult>({} as VoiceResult);
  const [summary, setSummary] = useState("");
  const [followDate, setFollowDate] = useState("");
  const [followText, setFollowText] = useState("");
  const [selected, setSelected] = useState<number | "new">("new");
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const candidates = result.candidates || [];

  // Drawer screens stay mounted and get reused, so useState initialisers only
  // run once — the second note would otherwise still show the first note's data
  // (issue #18). Take the freshly processed note on each focus and re-seed.
  useFocusEffect(
    useCallback(() => {
      const next = takeHandoff<VoiceResult>("voice");
      if (!next) return;
      const nextCandidates = next.candidates || [];
      setResult(next);
      setSummary(next.summary || "");
      setFollowDate(next.follow_up_date || "");
      setFollowText(next.follow_up_text || "");
      setSelected(nextCandidates.length > 0 && !next.is_new_lead ? nextCandidates[0].id : "new");
      setNewName(next.contact_query || "");
      setSaving(false);
    }, []),
  );

  async function save() {
    if (selected === "new" && !newName.trim()) {
      Alert.alert(t("voiceConfirm.nameNeededTitle"), t("voiceConfirm.nameNeededMessage"));
      return;
    }
    setSaving(true);
    try {
      await confirmVoice({
        contact_id: selected === "new" ? null : selected,
        new_contact_name: selected === "new" ? newName.trim() : null,
        summary: summary.trim(),
        follow_up_date: followDate.trim() || null,
        follow_up_text: followText.trim() || null,
      });
      Alert.alert(
        t("voiceConfirm.savedTitle"),
        followDate ? t("voiceConfirm.savedWithFollowup") : t("voiceConfirm.savedNoFollowup"),
        [{ text: "OK", onPress: () => router.replace("/(drawer)/voice") }],
      );
    } catch (error: any) {
      Alert.alert(
        t("voiceConfirm.couldntSaveTitle"),
        error?.response ? t("common.serverError", { status: error.response.status }) : error?.message || t("common.tryAgain"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.label}>{t("voiceConfirm.heard")}</Text>
        <Text style={styles.transcript}>{result.transcript}</Text>

        <Text style={styles.label}>{t("voiceConfirm.organization")}</Text>
        {candidates.map((candidate) => (
          <TouchableOpacity
            key={candidate.id}
            style={[styles.option, selected === candidate.id && styles.optionActive]}
            onPress={() => setSelected(candidate.id)}
          >
            <Text style={styles.optionText}>
              {candidate.name}
              {candidate.city ? ` — ${candidate.city}` : ""}
              {candidate.decision_maker ? `\n${candidate.decision_maker}` : ""}
            </Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity
          style={[styles.option, selected === "new" && styles.optionActive]}
          onPress={() => setSelected("new")}
        >
          <Text style={styles.optionText}>{t("voiceConfirm.newContact")}</Text>
        </TouchableOpacity>
        {selected === "new" && (
          <TextInput
            style={styles.input}
            value={newName}
            onChangeText={setNewName}
            placeholder={t("voiceConfirm.newContactNamePlaceholder")}
            placeholderTextColor="#555"
          />
        )}

        <Text style={styles.label}>{t("voiceConfirm.summary")}</Text>
        <TextInput
          style={[styles.input, styles.multi]}
          value={summary}
          onChangeText={setSummary}
          multiline
          placeholderTextColor="#555"
        />

        <Text style={styles.label}>{t("voiceConfirm.followUpDate")}</Text>
        <TextInput
          style={styles.input}
          value={followDate}
          onChangeText={setFollowDate}
          placeholder={t("voiceConfirm.none")}
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={styles.label}>{t("voiceConfirm.followUpAction")}</Text>
        <TextInput
          style={styles.input}
          value={followText}
          onChangeText={setFollowText}
          placeholder={t("voiceConfirm.none")}
          placeholderTextColor="#555"
        />

        <TouchableOpacity style={styles.save} onPress={save} disabled={saving}>
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{t("common.save")}</Text>}
        </TouchableOpacity>
        <TouchableOpacity style={styles.cancel} onPress={() => router.replace("/(drawer)/voice")}>
          <Text style={styles.cancelText}>{t("voiceConfirm.discard")}</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  content: { padding: 16, paddingBottom: 48 },
  label: { color: "#888", fontSize: 12, marginBottom: 5, marginTop: 14, marginLeft: 2 },
  transcript: {
    color: "#ccc",
    fontSize: 14,
    fontStyle: "italic",
    backgroundColor: "#15152a",
    borderRadius: 8,
    padding: 12,
    lineHeight: 20,
  },
  option: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#ffffff15",
  },
  optionActive: { borderColor: "#7c6fff", backgroundColor: "#221f3a" },
  optionText: { color: "#fff", fontSize: 14 },
  input: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    padding: 14,
    fontSize: 15,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  multi: { minHeight: 80, textAlignVertical: "top" },
  save: {
    backgroundColor: "#7c6fff",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 20,
  },
  saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  cancel: { padding: 14, alignItems: "center", marginTop: 6 },
  cancelText: { color: "#ef4444", fontSize: 15 },
});

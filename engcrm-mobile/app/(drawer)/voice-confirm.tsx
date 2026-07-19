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

export default function VoiceConfirmScreen() {
  const router = useRouter();
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
      Alert.alert("Name needed", "Give the new contact a name, or pick an existing one.");
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
      Alert.alert("Saved", followDate ? "Interaction logged with a follow-up." : "Interaction logged.", [
        { text: "OK", onPress: () => router.replace("/(drawer)/voice") },
      ]);
    } catch (error: any) {
      Alert.alert(
        "Couldn't save",
        error?.response ? `Server error (${error.response.status}).` : error?.message || "Try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.label}>Heard</Text>
        <Text style={styles.transcript}>{result.transcript}</Text>

        <Text style={styles.label}>Contact</Text>
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
          <Text style={styles.optionText}>+ New contact</Text>
        </TouchableOpacity>
        {selected === "new" && (
          <TextInput
            style={styles.input}
            value={newName}
            onChangeText={setNewName}
            placeholder="New contact name"
            placeholderTextColor="#555"
          />
        )}

        <Text style={styles.label}>Summary</Text>
        <TextInput
          style={[styles.input, styles.multi]}
          value={summary}
          onChangeText={setSummary}
          multiline
          placeholderTextColor="#555"
        />

        <Text style={styles.label}>Follow-up date (YYYY-MM-DD)</Text>
        <TextInput
          style={styles.input}
          value={followDate}
          onChangeText={setFollowDate}
          placeholder="none"
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={styles.label}>Follow-up action</Text>
        <TextInput
          style={styles.input}
          value={followText}
          onChangeText={setFollowText}
          placeholder="none"
          placeholderTextColor="#555"
        />

        <TouchableOpacity style={styles.save} onPress={save} disabled={saving}>
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>Save</Text>}
        </TouchableOpacity>
        <TouchableOpacity style={styles.cancel} onPress={() => router.replace("/(drawer)/voice")}>
          <Text style={styles.cancelText}>Discard</Text>
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

import { useState } from "react";
import {
  View,
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
import { useRouter, useLocalSearchParams } from "expo-router";
import { confirmVoice, VoiceResult } from "../../services/api";

export default function VoiceConfirmScreen() {
  const router = useRouter();
  const { data } = useLocalSearchParams<{ data: string }>();
  const result: VoiceResult = JSON.parse(data || "{}");
  const candidates = result.candidates || [];

  const [summary, setSummary] = useState(result.summary || "");
  const [followDate, setFollowDate] = useState(result.follow_up_date || "");
  const [followText, setFollowText] = useState(result.follow_up_text || "");
  const [selected, setSelected] = useState<number | "new">(
    candidates.length > 0 && !result.is_new_lead ? candidates[0].id : "new",
  );
  const [newName, setNewName] = useState(result.contact_query || "");
  const [saving, setSaving] = useState(false);

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
    } catch (e: any) {
      Alert.alert(
        "Couldn't save",
        e?.response ? `Server error (${e.response.status}).` : e?.message || "Try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView style={s.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        <Text style={s.label}>Heard</Text>
        <Text style={s.transcript}>{result.transcript}</Text>

        <Text style={s.label}>Contact</Text>
        {candidates.map((c) => (
          <TouchableOpacity
            key={c.id}
            style={[s.option, selected === c.id && s.optionActive]}
            onPress={() => setSelected(c.id)}
          >
            <Text style={s.optionText}>
              {c.name}
              {c.city ? ` — ${c.city}` : ""}
              {c.decision_maker ? `\n${c.decision_maker}` : ""}
            </Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity
          style={[s.option, selected === "new" && s.optionActive]}
          onPress={() => setSelected("new")}
        >
          <Text style={s.optionText}>+ New contact</Text>
        </TouchableOpacity>
        {selected === "new" && (
          <TextInput
            style={s.input}
            value={newName}
            onChangeText={setNewName}
            placeholder="New contact name"
            placeholderTextColor="#555"
          />
        )}

        <Text style={s.label}>Summary</Text>
        <TextInput
          style={[s.input, s.multi]}
          value={summary}
          onChangeText={setSummary}
          multiline
          placeholderTextColor="#555"
        />

        <Text style={s.label}>Follow-up date (YYYY-MM-DD)</Text>
        <TextInput
          style={s.input}
          value={followDate}
          onChangeText={setFollowDate}
          placeholder="none"
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={s.label}>Follow-up action</Text>
        <TextInput
          style={s.input}
          value={followText}
          onChangeText={setFollowText}
          placeholder="none"
          placeholderTextColor="#555"
        />

        <TouchableOpacity style={s.save} onPress={save} disabled={saving}>
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveText}>Save</Text>}
        </TouchableOpacity>
        <TouchableOpacity style={s.cancel} onPress={() => router.replace("/(drawer)/voice")}>
          <Text style={s.cancelText}>Discard</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
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

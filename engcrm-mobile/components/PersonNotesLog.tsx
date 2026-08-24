import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import {
  useAudioRecorder,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
} from "expo-audio";

import {
  addPersonNote,
  deletePersonNote,
  fetchPersonNotes,
  transcribePersonNote,
  PersonInteraction,
} from "../services/api";
import { useTranslation } from "../i18n/I18nContext";

const METHODS = [
  { value: "call", labelKey: "personDetail.notes.methodCall" },
  { value: "visit", labelKey: "personDetail.notes.methodVisit" },
  { value: "email", labelKey: "personDetail.notes.methodEmail" },
  { value: "other", labelKey: "personDetail.notes.methodOther" },
];

export function PersonNotesLog({ personId }: { personId: number }) {
  const { t } = useTranslation();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [notes, setNotes] = useState<PersonInteraction[]>([]);
  const [loading, setLoading] = useState(true);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [method, setMethod] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    return fetchPersonNotes(personId)
      .then(setNotes)
      .catch(() => setError(t("personDetail.notes.loadFailed")));
  }, [personId, t]);

  useEffect(() => {
    reload().finally(() => setLoading(false));
  }, [reload]);

  async function toggleRecording() {
    if (busy) return;
    if (recording) {
      setRecording(false);
      setBusy(true);
      try {
        await recorder.stop();
        const uri = recorder.uri;
        if (!uri) throw new Error("No recording captured");
        const result = await transcribePersonNote(personId, uri);
        setText((prev) => (prev ? `${prev}\n${result.transcript}` : result.transcript));
        setError(null);
      } catch (err: any) {
        setError(err?.response?.data?.detail || err?.message || t("personDetail.notes.transcribeFailed"));
      } finally {
        setBusy(false);
      }
    } else {
      try {
        const perm = await requestRecordingPermissionsAsync();
        if (!perm.granted) {
          Alert.alert(t("voice.micNeededTitle"), t("voice.micNeededMessage"));
          return;
        }
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        await recorder.prepareToRecordAsync();
        recorder.record();
        setRecording(true);
        setError(null);
      } catch (err: any) {
        Alert.alert(t("voice.couldntStartTitle"), err?.message || t("common.tryAgain"));
      }
    }
  }

  async function save() {
    const note = text.trim();
    if (!note || saving) return;
    setSaving(true);
    setError(null);
    try {
      await addPersonNote(personId, note, method);
      setText("");
      setMethod(null);
      await reload();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || t("personDetail.notes.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(note: PersonInteraction) {
    Alert.alert(t("personDetail.notes.deleteConfirm"), undefined, [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("personDetail.notes.delete"),
        style: "destructive",
        onPress: () => {
          setNotes((prev) => prev.filter((n) => n.id !== note.id));
          deletePersonNote(personId, note.id).catch(() => reload());
        },
      },
    ]);
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t("personDetail.notes.title")}</Text>

      <TextInput
        style={styles.input}
        multiline
        value={text}
        onChangeText={setText}
        placeholder={t("personDetail.notes.notePlaceholder")}
        placeholderTextColor="#666"
        editable={!saving}
      />

      <View style={styles.methods}>
        {METHODS.map(({ value, labelKey }) => {
          const isSelected = method === value;
          return (
            <TouchableOpacity
              key={value}
              style={[styles.methodChip, isSelected && styles.methodChipSelected]}
              onPress={() => setMethod(isSelected ? null : value)}
              disabled={saving}
            >
              <Text style={[styles.methodText, isSelected && styles.methodTextSelected]}>
                {t(labelKey)}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={styles.actions}>
        <TouchableOpacity
          style={[styles.recordButton, recording && styles.recordButtonActive]}
          onPress={toggleRecording}
          disabled={busy || saving}
        >
          {busy ? (
            <ActivityIndicator color="#7c6fff" size="small" />
          ) : (
            <Text style={styles.recordIcon}>{recording ? "⏹" : "🎙"}</Text>
          )}
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.saveButton, (!text.trim() || saving) && styles.saveButtonDisabled]}
          onPress={save}
          disabled={!text.trim() || saving}
        >
          <Text style={styles.saveText}>
            {saving ? t("personDetail.notes.saving") : t("personDetail.notes.save")}
          </Text>
        </TouchableOpacity>
      </View>
      {!!error && <Text style={styles.error}>{error}</Text>}

      {loading ? (
        <ActivityIndicator color="#7c6fff" style={{ marginTop: 16 }} />
      ) : notes.length === 0 ? (
        <Text style={styles.empty}>{t("personDetail.notes.empty")}</Text>
      ) : (
        notes.map((note) => (
          <View key={note.id} style={styles.entry}>
            <View style={styles.entryHeader}>
              <Text style={styles.entryDate}>{note.occurred_at.slice(0, 16).replace("T", " ")}</Text>
              {!!note.method && <Text style={styles.entryMethod}>{note.method}</Text>}
              <TouchableOpacity onPress={() => confirmDelete(note)}>
                <Text style={styles.entryDelete}>{t("personDetail.notes.delete")}</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.entryNote}>{note.note}</Text>
          </View>
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 20 },
  title: {
    color: "#888",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    marginBottom: 8,
    textTransform: "uppercase",
  },
  input: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff25",
    borderRadius: 10,
    borderWidth: 1,
    color: "#fff",
    fontSize: 14,
    minHeight: 70,
    padding: 12,
    textAlignVertical: "top",
  },
  methods: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 10 },
  methodChip: {
    backgroundColor: "#ffffff10",
    borderColor: "#ffffff25",
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  methodChipSelected: { backgroundColor: "#7c6fff", borderColor: "#aaa3ff" },
  methodText: { color: "#aaa", fontSize: 12, fontWeight: "600" },
  methodTextSelected: { color: "#fff" },
  actions: { alignItems: "center", flexDirection: "row", gap: 10, marginTop: 12 },
  recordButton: {
    alignItems: "center",
    backgroundColor: "#1a1a2e",
    borderColor: "#7c6fff",
    borderRadius: 22,
    borderWidth: 2,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  recordButtonActive: { borderColor: "#ef4444", backgroundColor: "#2a1620" },
  recordIcon: { fontSize: 18 },
  saveButton: {
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    flex: 1,
    paddingVertical: 12,
  },
  saveButtonDisabled: { opacity: 0.4 },
  saveText: { color: "#fff", fontSize: 14, fontWeight: "700", textAlign: "center" },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
  empty: { color: "#555", fontSize: 13, marginTop: 12 },
  entry: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    marginTop: 10,
    padding: 12,
  },
  entryHeader: { alignItems: "center", flexDirection: "row", gap: 8 },
  entryDate: { color: "#888", fontSize: 11 },
  entryMethod: {
    backgroundColor: "#ffffff10",
    borderRadius: 8,
    color: "#aaa",
    fontSize: 10,
    fontWeight: "700",
    paddingHorizontal: 6,
    paddingVertical: 2,
    textTransform: "uppercase",
  },
  entryDelete: { color: "#ef8a8a", fontSize: 11, marginLeft: "auto" },
  entryNote: { color: "#ccc", fontSize: 13, lineHeight: 19, marginTop: 6 },
});

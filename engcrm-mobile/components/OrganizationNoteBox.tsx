// Type a note about an organization and save it, right on its screen. It lands in
// the organization's history (the same log "Log a meeting" writes to), and the
// screen reloads to show it.
import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { addOrganizationNote } from "../services/api";
import { notifyChanged, organizationKey } from "../services/refreshBus";
import { useTranslation } from "../i18n/I18nContext";

export function OrganizationNoteBox({ organizationId }: { organizationId: number }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    const note = text.trim();
    if (!note || saving) return;
    setSaving(true);
    setFailed(false);
    try {
      await addOrganizationNote(organizationId, {
        note,
        method: null,
        follow_up_date: null,
        follow_up_text: null,
      });
      setText("");
      setSaved(true);
      notifyChanged(organizationKey(organizationId));
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.box}>
      <Text style={styles.title}>{t("organizationDetail.notes.title")}</Text>
      <TextInput
        style={styles.input}
        value={text}
        onChangeText={(value) => {
          setText(value);
          setSaved(false);
        }}
        placeholder={t("organizationDetail.notes.placeholder")}
        placeholderTextColor="#666"
        multiline
        editable={!saving}
        accessibilityLabel={t("organizationDetail.notes.title")}
      />
      <View style={styles.row}>
        <TouchableOpacity
          style={[styles.button, (!text.trim() || saving) && styles.buttonDisabled]}
          onPress={save}
          disabled={!text.trim() || saving}
          accessibilityRole="button"
          accessibilityState={{ disabled: !text.trim() || saving, busy: saving }}
        >
          {saving ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.buttonText}>{t("organizationDetail.notes.save")}</Text>
          )}
        </TouchableOpacity>
        {saved && <Text style={styles.saved}>{t("organizationDetail.notes.saved")}</Text>}
      </View>
      {failed && <Text style={styles.error}>{t("organizationDetail.notes.saveFailed")}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { backgroundColor: "#1a1a2e", borderRadius: 10, marginTop: 16, padding: 14 },
  title: { color: "#fff", fontSize: 13, fontWeight: "700", marginBottom: 8 },
  input: {
    backgroundColor: "#0f0f23",
    borderColor: "#333",
    borderRadius: 8,
    borderWidth: 1,
    color: "#fff",
    minHeight: 80,
    padding: 10,
    textAlignVertical: "top",
  },
  row: { alignItems: "center", flexDirection: "row", gap: 12, marginTop: 10 },
  button: { alignItems: "center", backgroundColor: "#7c6fff", borderRadius: 8, minHeight: 40, justifyContent: "center", paddingHorizontal: 16 },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: "#fff", fontWeight: "700" },
  saved: { color: "#888", fontSize: 12 },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
});

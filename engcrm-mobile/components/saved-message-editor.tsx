import { useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useTranslation } from "../i18n/I18nContext";
import { MessageWording, SavedMessage } from "../services/saved-messages";

interface Props {
  existing?: SavedMessage;
  onSave: (wording: MessageWording, existing?: SavedMessage) => Promise<SavedMessage>;
  onDone: (saved: SavedMessage) => void;
  onCancel: () => void;
}

export function SavedMessageEditor({ existing, onSave, onDone, onCancel }: Props) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(existing?.title || "");
  const [body, setBody] = useState(existing?.body || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = !!title.trim() && !!body.trim();
  async function save() {
    setSaving(true);
    setError(null);
    try { onDone(await onSave({ title, body }, existing)); }
    catch (failure: any) { setError(t(failure?.response?.status === 409 ? "savedMessages.conflict" : "savedMessages.saveFailed")); }
    finally { setSaving(false); }
  }
  function cancel() {
    if (title === (existing?.title || "") && body === (existing?.body || "")) return onCancel();
    Alert.alert(t("savedMessages.discardChanges"), undefined, [
      { text: t("savedMessages.keepEditing"), style: "cancel" },
      { text: t("savedMessages.discard"), style: "destructive", onPress: onCancel },
    ]);
  }
  return <View style={styles.editor}>
    <Text style={styles.label}>{t("savedMessages.titleLabel")}</Text>
    <TextInput accessibilityLabel={t("savedMessages.titleLabel")} style={styles.input}
      value={title} onChangeText={setTitle} maxLength={100} autoCapitalize="none" autoCorrect={false} editable={!saving} />
    <Text style={styles.label}>{t("savedMessages.wording")}</Text>
    <TextInput accessibilityLabel={t("savedMessages.wording")} style={[styles.input, styles.body]}
      value={body} onChangeText={setBody} maxLength={20000} multiline autoCapitalize="none" autoCorrect={false} editable={!saving} />
    {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    <TouchableOpacity accessibilityRole="button" onPress={save} disabled={!valid || saving} style={[styles.button, !valid && styles.disabled]}>
      {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.text}>{t("savedMessages.save")}</Text>}
    </TouchableOpacity>
    <TouchableOpacity accessibilityRole="button" onPress={cancel} disabled={saving} style={styles.button}>
      <Text style={styles.text}>{t("common.cancel")}</Text>
    </TouchableOpacity>
  </View>;
}

const styles = StyleSheet.create({
  editor: { gap: 12 }, label: { color: "#bbb", fontSize: 14 },
  input: { backgroundColor: "#1a1a2e", color: "#fff", borderRadius: 10, padding: 14, fontSize: 16 },
  body: { minHeight: 220, textAlignVertical: "top" },
  button: { backgroundColor: "#7c6fff", borderRadius: 10, padding: 14, alignItems: "center" },
  text: { color: "#fff", fontWeight: "600" }, error: { color: "#ff9999" }, disabled: { opacity: 0.5 },
});

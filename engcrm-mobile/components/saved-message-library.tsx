import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "../i18n/I18nContext";
import { SavedMessage } from "../services/saved-messages";
import { useSavedMessages } from "../services/use-saved-messages";
import { SavedMessageEditor } from "./saved-message-editor";
import { SavedMessagePreview } from "./saved-message-preview";

export function SavedMessageLibrary({ profile }: { profile?: string | null }) {
  const { t } = useTranslation();
  const library = useSavedMessages();
  const [selected, setSelected] = useState<SavedMessage | null>(null);
  const [editor, setEditor] = useState<SavedMessage | "new" | null>(null);
  if (library.loading) return <ActivityIndicator color="#7c6fff" />;
  if (editor) return <SavedMessageEditor key={editor === "new" ? "new" : `${editor.id}-${editor.version}`}
    existing={editor === "new" ? undefined : editor} onSave={library.save}
    onDone={(saved) => { setSelected(saved); setEditor(null); }} onCancel={() => setEditor(null)} />;
  return <View style={styles.library}>
    <Text style={styles.hint}>{t("savedMessages.privateHint")}</Text>
    {library.loadFailed ? <View>
      <Text accessibilityRole="alert" style={styles.hint}>{t("savedMessages.loadFailed")}</Text>
      <TouchableOpacity accessibilityRole="button" onPress={library.reload} style={styles.button}>
        <Text style={styles.text}>{t("savedMessages.retry")}</Text>
      </TouchableOpacity>
    </View> : <>
      {!library.messages.length && <Text style={styles.hint}>{t("savedMessages.empty")}</Text>}
      <TouchableOpacity accessibilityRole="button" onPress={() => setEditor("new")} style={styles.button}>
        <Text style={styles.text}>{t("savedMessages.add")}</Text>
      </TouchableOpacity>
      <TouchableOpacity accessibilityRole="button" onPress={() => { setSelected(null); library.reload(); }} style={styles.button}>
        <Text style={styles.text}>{t("savedMessages.refresh")}</Text>
      </TouchableOpacity>
      {library.messages.map((message) => <TouchableOpacity key={message.id} accessibilityRole="button"
        accessibilityState={{ selected: selected?.id === message.id }}
        onPress={() => setSelected(message)} style={[styles.row, selected?.id === message.id && styles.selected]}>
        <Text style={styles.text}>{message.title}</Text><Text style={styles.hint} numberOfLines={2}>{message.body}</Text>
      </TouchableOpacity>)}
    </>}
    {selected && <SavedMessagePreview key={`${selected.id}-${selected.version}`} message={selected}
      profile={profile} onEdit={() => setEditor(selected)} />}
  </View>;
}

const styles = StyleSheet.create({
  library: { gap: 16 }, hint: { color: "#bbb", fontSize: 14 },
  button: { backgroundColor: "#7c6fff", borderRadius: 10, padding: 14, alignItems: "center" },
  text: { color: "#fff", fontSize: 16 }, row: { backgroundColor: "#1a1a2e", borderRadius: 10, padding: 14, gap: 8, borderWidth: 1, borderColor: "transparent" },
  selected: { borderColor: "#b4adff" },
});

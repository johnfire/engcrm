import { useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "../i18n/I18nContext";
import { copyMessage, SavedMessage } from "../services/saved-messages";
import { openWebsite } from "../services/webLinks";

export function SavedMessagePreview({ message, profile, onEdit }: {
  message: SavedMessage; profile?: string | null; onEdit: () => void;
}) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<"copied" | "copyFailed" | "openFailed" | null>(null);
  const [copying, setCopying] = useState(false);
  async function copy() {
    setCopying(true);
    try { await copyMessage(message.body); setStatus("copied"); }
    catch { setStatus("copyFailed"); }
    finally { setCopying(false); }
  }
  async function openProfile() {
    if (!await openWebsite(profile)) setStatus("openFailed");
  }
  return <View style={styles.preview}>
    <Text style={styles.title}>{message.title}</Text>
    <Text style={styles.body} selectable>{message.body}</Text>
    <Text style={styles.hint}>{t("savedMessages.pasteHint")}</Text>
    {status && <Text accessibilityLiveRegion="polite" style={styles.hint}>{t(`savedMessages.${status}`)}</Text>}
    <TouchableOpacity accessibilityRole="button" disabled={copying} style={styles.button} onPress={copy}>
      <Text style={styles.text}>{t("savedMessages.copy")}</Text>
    </TouchableOpacity>
    {!!profile && <TouchableOpacity accessibilityRole="link" style={styles.button} onPress={openProfile}>
      <Text style={styles.text}>{t("savedMessages.openLinkedin")}</Text>
    </TouchableOpacity>}
    <TouchableOpacity accessibilityRole="button" style={styles.button} onPress={onEdit}>
      <Text style={styles.text}>{t("savedMessages.edit")}</Text>
    </TouchableOpacity>
  </View>;
}

const styles = StyleSheet.create({
  preview: { backgroundColor: "#1a1a2e", borderRadius: 12, padding: 16, gap: 14 },
  title: { color: "#fff", fontSize: 18, fontWeight: "600" }, body: { color: "#fff", fontSize: 16, lineHeight: 24 },
  hint: { color: "#bbb", fontSize: 14 }, button: { padding: 14, backgroundColor: "#7c6fff", borderRadius: 10, alignItems: "center" },
  text: { color: "#fff", fontWeight: "600" },
});

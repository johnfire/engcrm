import { useCallback, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { confirmCard, discardCard, CaptureResult, CardFields } from "../../services/api";
import { takeHandoff } from "../../services/handoff";
import { CardField } from "../../components/CardField";
import { useTranslation } from "../../i18n/I18nContext";

export default function CardConfirmScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [capture, setCapture] = useState<CaptureResult>({} as CaptureResult);
  const [fields, setFields] = useState<CardFields>({});
  const [linkDup, setLinkDup] = useState(false);
  const [saving, setSaving] = useState(false);
  const dup = capture.dup_suggestion;

  // This screen is a drawer screen, so its instance is kept mounted and reused
  // for every scan — a useState initialiser would only ever run for the first
  // card (issue #18). Take the freshly captured card on each focus instead, so
  // every scan re-seeds the form regardless of the reused instance.
  useFocusEffect(
    useCallback(() => {
      const next = takeHandoff<CaptureResult>("card");
      if (!next) return;
      setCapture(next);
      setFields(next.fields || {});
      setLinkDup(false);
      setSaving(false);
    }, []),
  );

  const set =
    (fieldKey: keyof CardFields) =>
    (value: string) =>
      setFields((prev) => ({ ...prev, [fieldKey]: value }));

  async function save() {
    setSaving(true);
    try {
      await confirmCard(capture.capture_id, fields, linkDup && dup ? dup.id : null);
      Alert.alert(
        linkDup ? t("cardConfirm.linkedTitle") : t("cardConfirm.savedTitle"),
        t("cardConfirm.savedMessage"),
        [{ text: "OK", onPress: () => router.replace("/(drawer)/capture") }],
      );
    } catch (error: any) {
      Alert.alert(t("cardConfirm.couldntSaveTitle"), String(error?.message || t("common.tryAgain")));
    } finally {
      setSaving(false);
    }
  }

  async function discard() {
    try {
      await discardCard(capture.capture_id);
    } catch {
      // best-effort; the capture row stays pending if this fails
    }
    router.replace("/(drawer)/capture");
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {dup && (
          <View style={styles.dupBanner}>
            <Text style={styles.dupTitle}>{t("cardConfirm.duplicateWarning")}</Text>
            <Text style={styles.dupText}>
              {dup.name}
              {dup.city ? ` — ${dup.city}` : ""}
              {dup.email ? `\n${dup.email}` : ""}
            </Text>
            <View style={styles.dupActions}>
              <TouchableOpacity
                style={[styles.dupBtn, !linkDup && styles.dupBtnActive]}
                onPress={() => setLinkDup(false)}
              >
                <Text style={[styles.dupBtnText, !linkDup && styles.dupBtnTextActive]}>
                  {t("cardConfirm.createNew")}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.dupBtn, linkDup && styles.dupBtnActive]}
                onPress={() => setLinkDup(true)}
              >
                <Text style={[styles.dupBtnText, linkDup && styles.dupBtnTextActive]}>
                  {t("cardConfirm.linkExisting")}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {typeof capture.confidence === "number" && (
          <Text style={styles.confidence}>{t("cardConfirm.confidence", { confidence: capture.confidence })}</Text>
        )}

        <CardField label={t("cardConfirm.company")} value={fields.company} onChange={set("company")} />
        <CardField label={t("cardConfirm.name")} value={fields.name} onChange={set("name")} />
        <CardField label={t("cardConfirm.title")} value={fields.title} onChange={set("title")} />
        <CardField label={t("cardConfirm.email")} value={fields.email} onChange={set("email")} keyboardType="email-address" />
        <CardField label={t("cardConfirm.phone")} value={fields.phone} onChange={set("phone")} keyboardType="phone-pad" />
        <CardField label={t("cardConfirm.mobile")} value={fields.mobile} onChange={set("mobile")} keyboardType="phone-pad" />
        <CardField label={t("cardConfirm.website")} value={fields.website} onChange={set("website")} keyboardType="url" />
        <CardField label={t("cardConfirm.address")} value={fields.address} onChange={set("address")} />
        <CardField label={t("cardConfirm.city")} value={fields.city} onChange={set("city")} />
        <CardField label={t("cardConfirm.country")} value={fields.country} onChange={set("country")} />
        <CardField label={t("cardConfirm.industry")} value={fields.industry} onChange={set("industry")} />
        <CardField label={t("cardConfirm.note")} value={fields.note} onChange={set("note")} multiline />

        <TouchableOpacity style={styles.save} onPress={save} disabled={saving}>
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.saveText}>
              {linkDup ? t("cardConfirm.linkToExistingLead") : t("cardConfirm.saveLead")}
            </Text>
          )}
        </TouchableOpacity>
        <View style={styles.row}>
          <TouchableOpacity style={styles.retake} onPress={() => router.replace("/(drawer)/capture")}>
            <Text style={styles.retakeText}>{t("cardConfirm.retake")}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.discardBtn} onPress={discard}>
            <Text style={styles.discardText}>{t("cardConfirm.discard")}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  content: { padding: 16, paddingBottom: 48 },
  dupBanner: {
    backgroundColor: "#3a2e10",
    borderColor: "#a07b1e",
    borderWidth: 1,
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
  },
  dupTitle: { color: "#f0c040", fontWeight: "700", marginBottom: 4 },
  dupText: { color: "#ddd", fontSize: 14, marginBottom: 10 },
  dupActions: { flexDirection: "row", gap: 8 },
  dupBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: "#ffffff10",
    alignItems: "center",
  },
  dupBtnActive: { backgroundColor: "#7c6fff" },
  dupBtnText: { color: "#aaa", fontSize: 13, fontWeight: "600" },
  dupBtnTextActive: { color: "#fff" },
  confidence: { color: "#666", fontSize: 12, marginBottom: 12, textAlign: "right" },
  save: {
    backgroundColor: "#7c6fff",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 8,
  },
  saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  row: { flexDirection: "row", gap: 12, marginTop: 12 },
  retake: {
    flex: 1,
    padding: 14,
    borderRadius: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  retakeText: { color: "#ccc", fontSize: 15 },
  discardBtn: { flex: 1, padding: 14, borderRadius: 10, alignItems: "center" },
  discardText: { color: "#ef4444", fontSize: 15 },
});

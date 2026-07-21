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
import { confirmSign, discardSign, SignCaptureResult } from "../../services/api";
import { takeHandoff } from "../../services/handoff";
import { CardField } from "../../components/CardField";
import { useTranslation } from "../../i18n/I18nContext";

export default function SignConfirmScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [capture, setCapture] = useState<SignCaptureResult>({} as SignCaptureResult);
  const [businessName, setBusinessName] = useState("");
  const [acceptPlace, setAcceptPlace] = useState(false);
  const [linkDup, setLinkDup] = useState(false);
  const [saving, setSaving] = useState(false);
  const place = capture.place;
  const dup = capture.dup_suggestion;

  // sign-confirm is a drawer screen, so its instance is reused for every scan
  // (same reuse issue card-confirm guards against — issue #18). Take the
  // freshly captured sign on each focus instead of on mount.
  useFocusEffect(
    useCallback(() => {
      const next = takeHandoff<SignCaptureResult>("sign");
      if (!next) return;
      setCapture(next);
      setBusinessName(next.fields?.business_name || next.place?.name || "");
      setAcceptPlace(!!next.place);
      setLinkDup(false);
      setSaving(false);
    }, []),
  );

  async function save() {
    if (!businessName.trim()) {
      Alert.alert(t("signConfirm.businessNameRequiredTitle"), t("signConfirm.enterOrConfirmMessage"));
      return;
    }
    setSaving(true);
    try {
      await confirmSign(
        capture.capture_id,
        businessName.trim(),
        acceptPlace,
        linkDup && dup ? dup.id : null,
      );
      Alert.alert(
        linkDup ? t("cardConfirm.linkedTitle") : t("signConfirm.savedTitle"),
        t("signConfirm.savedMessage"),
        [{ text: "OK", onPress: () => router.replace("/(drawer)/scan-sign") }],
      );
    } catch (error: any) {
      Alert.alert(t("cardConfirm.couldntSaveTitle"), String(error?.message || t("common.tryAgain")));
    } finally {
      setSaving(false);
    }
  }

  async function discard() {
    try {
      await discardSign(capture.capture_id);
    } catch {
      // best-effort; the capture row stays pending if this fails
    }
    router.replace("/(drawer)/scan-sign");
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {place && (
          <View style={styles.placeBanner}>
            <Text style={styles.placeTitle}>{t("signConfirm.matched")}</Text>
            <Text style={styles.placeText}>
              {place.name}
              {place.address ? `\n${place.address}` : ""}
              {place.city ? ` — ${place.city}` : ""}
            </Text>
            <View style={styles.placeActions}>
              <TouchableOpacity
                style={[styles.placeBtn, acceptPlace && styles.placeBtnActive]}
                onPress={() => setAcceptPlace(true)}
              >
                <Text style={[styles.placeBtnText, acceptPlace && styles.placeBtnTextActive]}>
                  {t("signConfirm.acceptMatch")}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.placeBtn, !acceptPlace && styles.placeBtnActive]}
                onPress={() => setAcceptPlace(false)}
              >
                <Text style={[styles.placeBtnText, !acceptPlace && styles.placeBtnTextActive]}>
                  {t("signConfirm.rejectMatch")}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {dup && (
          <View style={styles.dupBanner}>
            <Text style={styles.dupTitle}>{t("cardConfirm.duplicateWarning")}</Text>
            <Text style={styles.dupText}>
              {dup.name}
              {dup.city ? ` — ${dup.city}` : ""}
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

        <CardField label={t("signConfirm.businessName")} value={businessName} onChange={setBusinessName} />

        <TouchableOpacity style={styles.save} onPress={save} disabled={saving}>
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.saveText}>
              {linkDup ? t("cardConfirm.linkToExistingLead") : t("signConfirm.saveBusiness")}
            </Text>
          )}
        </TouchableOpacity>
        <View style={styles.row}>
          <TouchableOpacity style={styles.retake} onPress={() => router.replace("/(drawer)/scan-sign")}>
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
  placeBanner: {
    backgroundColor: "#132a1f",
    borderColor: "#2ea15e",
    borderWidth: 1,
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
  },
  placeTitle: { color: "#4ade80", fontWeight: "700", marginBottom: 4 },
  placeText: { color: "#ddd", fontSize: 14, marginBottom: 10 },
  placeActions: { flexDirection: "row", gap: 8 },
  placeBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: "#ffffff10",
    alignItems: "center",
  },
  placeBtnActive: { backgroundColor: "#2ea15e" },
  placeBtnText: { color: "#aaa", fontSize: 13, fontWeight: "600" },
  placeBtnTextActive: { color: "#fff" },
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

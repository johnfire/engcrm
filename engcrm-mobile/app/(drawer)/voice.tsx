import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import {
  useAudioRecorder,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
} from "expo-audio";
import { processVoice } from "../../services/api";
import { setHandoff } from "../../services/handoff";
import { useTranslation } from "../../i18n/I18nContext";

export default function VoiceScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (busy) return;
    if (recording) {
      setRecording(false);
      setBusy(true);
      try {
        await recorder.stop();
        const uri = recorder.uri;
        if (!uri) throw new Error("No recording captured");
        const result = await processVoice(uri);
        setHandoff("voice", result);
        router.push("/(drawer)/voice-confirm");
      } catch (error: any) {
        Alert.alert(
          t("voice.couldntProcessTitle"),
          error?.response ? t("common.serverError", { status: error.response.status }) : error?.message || t("common.tryAgain"),
        );
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
      } catch (error: any) {
        Alert.alert(t("voice.couldntStartTitle"), error?.message || t("common.tryAgain"));
      }
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>{t("voice.hint")}</Text>
      {busy ? (
        <View style={styles.center}>
          <ActivityIndicator color="#7c6fff" size="large" />
          <Text style={styles.busyText}>{t("voice.transcribing")}</Text>
        </View>
      ) : (
        <TouchableOpacity
          style={[styles.mic, recording && styles.micActive]}
          onPress={toggle}
          activeOpacity={0.85}
        >
          <Text style={styles.micIcon}>{recording ? "⏹" : "🎙"}</Text>
          <Text style={styles.micLabel}>
            {recording ? t("voice.recordingTapStop") : t("voice.tapToRecord")}
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", padding: 28, justifyContent: "center", alignItems: "center" },
  hint: { color: "#888", fontSize: 15, textAlign: "center", marginBottom: 40, lineHeight: 21 },
  mic: {
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: "#1a1a2e",
    borderWidth: 2,
    borderColor: "#7c6fff",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  micActive: { borderColor: "#ef4444", backgroundColor: "#2a1620" },
  micIcon: { fontSize: 54 },
  micLabel: { color: "#ccc", fontSize: 13, fontWeight: "600", textAlign: "center", paddingHorizontal: 16 },
  center: { alignItems: "center", gap: 16 },
  busyText: { color: "#888", fontSize: 14 },
});

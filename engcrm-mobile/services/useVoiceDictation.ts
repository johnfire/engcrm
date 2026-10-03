import { useState } from "react";
import { Alert } from "react-native";
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";

import { useTranslation } from "../i18n/I18nContext";

export type DictationPhase = "idle" | "recording" | "transcribing";

/**
 * Tap to start, tap to stop: the recording is sent to `transcribe` and the text handed
 * to `onText` for the user to read before saving. Nothing is stored by dictation itself.
 */
export function useVoiceDictation(opts: {
  transcribe: (audioUri: string) => Promise<string>;
  onText: (text: string) => void;
}) {
  const { t } = useTranslation();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [phase, setPhase] = useState<DictationPhase>("idle");
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (phase === "transcribing") return;
    if (phase === "recording") {
      setPhase("transcribing");
      try {
        await recorder.stop();
        const uri = recorder.uri;
        if (!uri) throw new Error("No recording captured");
        opts.onText(await opts.transcribe(uri));
        setError(null);
      } catch (err: any) {
        setError(err?.response?.data?.detail || err?.message || t("meeting.transcribeFailed"));
      } finally {
        setPhase("idle");
      }
      return;
    }
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(t("voice.micNeededTitle"), t("voice.micNeededMessage"));
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setPhase("recording");
      setError(null);
    } catch (err: any) {
      Alert.alert(t("voice.couldntStartTitle"), err?.message || t("common.tryAgain"));
    }
  }

  return { phase, error, toggle };
}

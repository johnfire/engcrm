import { useState } from "react";
import { Alert } from "react-native";
import { useRouter } from "expo-router";
import { captureCard } from "../services/api";
import { enqueue } from "../services/cardQueue";
import { setHandoff } from "../services/handoff";
import { chooseDocumentPhoto, prepareDocumentPhoto } from "../services/documentPhoto";
import { useTranslation } from "../i18n/I18nContext";

type CaptureContext = {
  t: ReturnType<typeof useTranslation>["t"];
  router: ReturnType<typeof useRouter>;
  setBusy: (busy: boolean) => void;
  setPreview: (preview: string | null) => void;
};

async function reportCaptureFailure(error: unknown, imageUri: string | null, t: CaptureContext["t"]) {
  const failure = error as { message?: string; response?: { status: number } };
  if (failure.message === "camera-permission") {
    Alert.alert(t("capture.cameraPermissionTitle"), t("capture.cameraPermissionMessage"));
    return;
  }
  if (imageUri && !failure.response) {
    try {
      await enqueue(imageUri);
      Alert.alert(t("capture.savedOfflineTitle"), t("capture.savedOfflineMessage"));
      return;
    } catch { /* Fall through to the retry message if storage also fails. */ }
  }
  Alert.alert(t("capture.uploadFailedTitle"), failure.response
    ? t("common.serverError", { status: failure.response.status }) : t("capture.uploadFailedGeneric"));
}

async function uploadContactPhoto(source: "camera" | "library", context: CaptureContext) {
  const { t, router, setBusy, setPreview } = context;
  let imageUri: string | null = null;
  setBusy(true);
  try {
    const photo = await chooseDocumentPhoto(source);
    if (!photo) return;
    setPreview(photo.uri);
    imageUri = await prepareDocumentPhoto(photo);
    const capture = await captureCard(imageUri);
    if (!capture.is_card) {
      Alert.alert(t("capture.couldntReadTitle"),
        capture.fields?.note || capture.fields?.error || t("capture.notACardMessage"));
      return;
    }
    setHandoff("card", capture);
    router.push("/(drawer)/card-confirm");
  } catch (error) {
    await reportCaptureFailure(error, imageUri, t);
  } finally {
    setBusy(false);
    setPreview(null);
  }
}

export function useContactCapture() {
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const { t } = useTranslation();
  const router = useRouter();
  const pickAndUpload = (source: "camera" | "library") => {
    if (busy) return Promise.resolve();
    return uploadContactPhoto(source, { t, router, setBusy, setPreview });
  };
  return { busy, preview, pickAndUpload };
}

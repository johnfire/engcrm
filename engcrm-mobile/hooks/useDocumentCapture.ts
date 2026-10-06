import { useState } from "react";
import { Alert } from "react-native";
import { useRouter } from "expo-router";
import { useTranslation } from "../i18n/I18nContext";
import { captureDocument } from "../services/documentApi";
import { enqueue } from "../services/cardQueue";
import { chooseDocumentPhoto, newDocumentBatchId, prepareDocumentPhoto } from "../services/documentPhoto";

type CaptureContext = {
  t: ReturnType<typeof useTranslation>["t"];
  router: ReturnType<typeof useRouter>;
  setBusy: (busy: boolean) => void;
  setPreview: (preview: string | null) => void;
};

async function reportUploadFailure(error: unknown, imageUri: string | null, batchId: string, t: CaptureContext["t"]) {
  const failure = error as { message?: string; response?: { status: number } };
  if (imageUri && !failure.response) {
    try {
      await enqueue(imageUri, "document", batchId);
      Alert.alert(t("capture.savedOfflineTitle"), t("documentCapture.savedOffline"));
      return;
    } catch { /* Show a retry message if local storage also failed. */ }
  }
  Alert.alert(t("capture.uploadFailedTitle"), failure.message === "camera-permission"
    ? t("documentCapture.cameraPermission") : t("documentCapture.uploadFailed"));
}

async function uploadDocumentPhoto(source: "camera" | "library", context: CaptureContext) {
  const { t, router, setBusy, setPreview } = context;
  const batchId = newDocumentBatchId();
  let imageUri: string | null = null;
  setBusy(true);
  try {
    const photo = await chooseDocumentPhoto(source);
    if (!photo) return;
    setPreview(photo.uri);
    imageUri = await prepareDocumentPhoto(photo);
    const capture = await captureDocument(imageUri, batchId);
    if (!capture.is_document) {
      Alert.alert(t("capture.couldntReadTitle"), capture.note || t("documentCapture.unreadable"));
      return;
    }
    Alert.alert(t("documentCapture.readyTitle"), t("documentCapture.ready", { count: capture.captures.length }),
      [{ text: t("documentCapture.review"), onPress: () => router.push("/(drawer)/card-queue") }]);
  } catch (error) {
    await reportUploadFailure(error, imageUri, batchId, t);
  } finally {
    setBusy(false);
    setPreview(null);
  }
}

export function useDocumentCapture() {
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const { t } = useTranslation();
  const router = useRouter();
  const pickAndUpload = (source: "camera" | "library") => {
    if (busy) return Promise.resolve();
    return uploadDocumentPhoto(source, { t, router, setBusy, setPreview });
  };
  return { busy, preview, pickAndUpload };
}

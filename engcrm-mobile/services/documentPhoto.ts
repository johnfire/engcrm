import * as ImagePicker from "expo-image-picker";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";

export function newDocumentBatchId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

export async function chooseDocumentPhoto(source: "camera" | "library"): Promise<ImagePicker.ImagePickerAsset | null> {
  if (source === "camera") {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) throw new Error("camera-permission");
  }
  // iOS's editing picker crops to a square, which removes document rows.
  const options: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], allowsEditing: false, quality: 1 };
  const selection = source === "camera"
    ? await ImagePicker.launchCameraAsync(options)
    : await ImagePicker.launchImageLibraryAsync(options);
  return selection.canceled ? null : selection.assets?.[0] ?? null;
}

export async function prepareDocumentPhoto(photo: ImagePicker.ImagePickerAsset): Promise<string> {
  const context = ImageManipulator.manipulate(photo.uri);
  const longestEdge = Math.max(photo.width, photo.height);
  if (longestEdge > 2048) {
    context.resize(photo.width >= photo.height ? { width: 2048 } : { height: 2048 });
  }
  const rendered = await context.renderAsync();
  const saved = await rendered.saveAsync({ compress: 0.85, format: SaveFormat.JPEG });
  return saved.uri;
}

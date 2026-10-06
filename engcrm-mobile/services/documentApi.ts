import { client, CardFields } from "./api";

export interface DocumentCaptureResult {
  is_document: boolean;
  captures: { capture_id: number; fields: CardFields; confidence: number | null }[];
  note: string | null;
}

export async function captureDocument(imageUri: string, batchId: string): Promise<DocumentCaptureResult> {
  const form = new FormData();
  form.append("image", { uri: imageUri, name: "page.jpg", type: "image/jpeg" } as any);
  form.append("capture_batch_id", batchId);
  const response = await client.post("/api/documents", form, { timeout: 120000 });
  return response.data;
}

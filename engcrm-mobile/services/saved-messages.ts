import * as Clipboard from "expo-clipboard";
import { client } from "./api";

export interface SavedMessage {
  id: number;
  title: string;
  body: string;
  version: number;
  created_at: string;
  updated_at: string;
}
export type MessageWording = Pick<SavedMessage, "title" | "body">;

export async function fetchSavedMessages(): Promise<SavedMessage[]> {
  return (await client.get("/api/saved-messages")).data;
}

export async function saveMessage(wording: MessageWording, existing?: SavedMessage): Promise<SavedMessage> {
  const response = existing ?
    await client.put(`/api/saved-messages/${existing.id}`, { ...wording, version: existing.version }) :
    await client.post("/api/saved-messages", wording);
  return response.data;
}

export async function copyMessage(wording: string): Promise<void> {
  const copied = await Clipboard.setStringAsync(wording);
  if (!copied) throw new Error("Clipboard unavailable");
}

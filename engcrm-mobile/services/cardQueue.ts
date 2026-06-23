/**
 * Offline capture queue. When a card upload fails because there's no connection,
 * the downscaled image is persisted to the document directory and an index entry
 * is kept in AsyncStorage. On the next online visit to the Scan screen the queue
 * is flushed — each card re-uploads and lands in pending-review on the server.
 * A capture is never lost just because signal dropped in the field.
 */
import { Directory, File, Paths } from "expo-file-system";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { captureCard } from "./api";

const QUEUE_KEY = "card_upload_queue_v1";
const DIR_NAME = "card-queue";

export interface QueueEntry {
  id: string;
  uri: string;
  ts: number;
}

function queueDir(): Directory {
  return new Directory(Paths.document, DIR_NAME);
}

async function readIndex(): Promise<QueueEntry[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as QueueEntry[]) : [];
  } catch {
    return [];
  }
}

async function writeIndex(entries: QueueEntry[]): Promise<void> {
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(entries));
}

/** Persist a downscaled card image for later upload (called when a live upload fails offline). */
export async function enqueue(imageUri: string): Promise<void> {
  const dir = queueDir();
  if (!dir.exists) dir.create();
  const id = `${Date.now()}-${Math.round(Math.random() * 1e6)}`;
  const dest = new File(dir, `${id}.jpg`);
  if (dest.exists) dest.delete();
  new File(imageUri).copy(dest);
  const entries = await readIndex();
  entries.push({ id, uri: dest.uri, ts: Date.now() });
  await writeIndex(entries);
}

export async function pendingCount(): Promise<number> {
  return (await readIndex()).length;
}

/** Re-upload queued captures. Successful ones become pending-review on the server. */
export async function flush(): Promise<{ uploaded: number; remaining: number }> {
  const entries = await readIndex();
  if (entries.length === 0) return { uploaded: 0, remaining: 0 };
  const keep: QueueEntry[] = [];
  let uploaded = 0;
  for (const e of entries) {
    try {
      await captureCard(e.uri);
      uploaded += 1;
      try {
        new File(e.uri).delete();
      } catch {
        // file already gone — ignore
      }
    } catch {
      keep.push(e); // still offline / server unreachable — retry next time
    }
  }
  await writeIndex(keep);
  return { uploaded, remaining: keep.length };
}

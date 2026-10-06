/**
 * Offline capture queue. When a card or document upload fails because there's no connection,
 * the downscaled image is persisted to the document directory and an index entry
 * is kept in AsyncStorage. On the next online visit to the Scan screen the queue
 * is flushed — each photo re-uploads and lands in pending-review on the server.
 * A capture is never lost just because signal dropped in the field.
 */
import { Directory, File, Paths } from "expo-file-system";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { captureCard } from "./api";
import { captureDocument } from "./documentApi";

const QUEUE_KEY = "card_upload_queue_v1";
const DIR_NAME = "card-queue";

export interface QueueEntry {
  id: string;
  uri: string;
  ts: number;
  kind?: "card" | "document";
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

/** Persist a prepared card or page image for later upload (called when a live upload fails offline). */
async function persistQueuedPhoto(imageUri: string, kind: "card" | "document", batchId?: string): Promise<void> {
  const dir = queueDir();
  if (!dir.exists) dir.create();
  const id = batchId ?? `${Date.now()}-${Math.round(Math.random() * 1e6)}`;
  const dest = new File(dir, `${id}.jpg`);
  if (dest.exists) dest.delete();
  new File(imageUri).copy(dest);
  const entries = await readIndex();
  if (!entries.some((entry) => entry.id === id)) entries.push({ id, uri: dest.uri, ts: Date.now(), kind });
  await writeIndex(entries);
}

export async function pendingCount(): Promise<number> {
  return (await readIndex()).length;
}

/** Re-upload queued captures. Successful ones become pending-review on the server. */
async function flushEntries(): Promise<{ uploaded: number; remaining: number }> {
  const entries = await readIndex();
  if (entries.length === 0) return { uploaded: 0, remaining: 0 };
  const keep: QueueEntry[] = [];
  let uploaded = 0;
  for (const entry of entries) {
    try {
      await uploadQueuedPhoto(entry);
      uploaded += 1;
      try {
        new File(entry.uri).delete();
      } catch {
        // file already gone — ignore
      }
    } catch {
      keep.push(entry); // still offline / server unreachable — retry next time
    }
  }
  await writeIndex(keep);
  return { uploaded, remaining: keep.length };
}

async function uploadQueuedPhoto(entry: QueueEntry): Promise<void> {
  if (entry.kind === "document") {
    const capture = await captureDocument(entry.uri, entry.id);
    if (!capture.is_document) throw new Error("Page needs a clearer photo");
  } else {
    await captureCard(entry.uri);
  }
}

let activeFlush: Promise<{ uploaded: number; remaining: number }> | null = null;

export function flush(): Promise<{ uploaded: number; remaining: number }> {
  if (!activeFlush) activeFlush = mutateQueue(flushEntries).finally(() => { activeFlush = null; });
  return activeFlush;
}

let pendingMutation: Promise<unknown> = Promise.resolve();

function mutateQueue<T>(mutation: () => Promise<T>): Promise<T> {
  const operation = pendingMutation.then(mutation);
  pendingMutation = operation.catch(() => undefined);
  return operation;
}

export function enqueue(imageUri: string, kind: "card" | "document" = "card", batchId?: string): Promise<void> {
  return mutateQueue(() => persistQueuedPhoto(imageUri, kind, batchId));
}

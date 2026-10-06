const mockStorage = new Map<string, string>();
const mockCaptureCard = jest.fn();
const mockCaptureDocument = jest.fn();
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: async (key: string) => mockStorage.get(key) ?? null,
  setItem: async (key: string, value: string) => { mockStorage.set(key, value); },
}));
jest.mock("expo-file-system", () => ({
  Paths: { document: "file:///documents" },
  Directory: class { exists = true; create() {} },
  File: class {
    uri: string; exists = false;
    constructor(_directory: unknown, name?: string) { this.uri = `file:///documents/${name}`; }
    copy() {} delete() {}
  },
}));
jest.mock("../../services/api", () => ({ captureCard: (...args: unknown[]) => mockCaptureCard(...args) }));
jest.mock("../../services/documentApi", () => ({ captureDocument: (...args: unknown[]) => mockCaptureDocument(...args) }));
import { enqueue, flush, pendingCount } from "../../services/cardQueue";

beforeEach(() => { mockStorage.clear(); jest.clearAllMocks(); });

it("retries document photos with the original batch ID and capture mode", async () => {
  mockCaptureDocument.mockResolvedValue({ is_document: true });
  await enqueue("page.jpg", "document", "page-batch");
  expect(await pendingCount()).toBe(1);
  expect(await flush()).toEqual({ uploaded: 1, remaining: 0 });
  expect(mockCaptureDocument).toHaveBeenCalledWith("file:///documents/page-batch.jpg", "page-batch");
  expect(mockCaptureCard).not.toHaveBeenCalled();
});

it("retains a failed or unreadable document for another attempt", async () => {
  mockCaptureDocument.mockResolvedValue({ is_document: false });
  await enqueue("page.jpg", "document", "page-batch");
  expect(await flush()).toEqual({ uploaded: 0, remaining: 1 });
  expect(await pendingCount()).toBe(1);
});

it("remains compatible with old card queue entries", async () => {
  mockStorage.set("card_upload_queue_v1", JSON.stringify([{ id: "old", uri: "old.jpg", ts: 1 }]));
  mockCaptureCard.mockResolvedValue({ is_card: true });
  expect(await flush()).toEqual({ uploaded: 1, remaining: 0 });
  expect(mockCaptureCard).toHaveBeenCalledWith("old.jpg");
});

it("keeps a new offline photo queued while an earlier upload is flushing", async () => {
  let finishUpload: (capture: { is_document: boolean }) => void = () => {};
  mockCaptureDocument.mockReturnValueOnce(new Promise((resolve) => { finishUpload = resolve; }));
  await enqueue("first.jpg", "document", "first");
  const uploading = flush();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const savingNext = enqueue("second.jpg", "document", "second");
  finishUpload({ is_document: true });
  await uploading;
  await savingNext;
  expect(await pendingCount()).toBe(1);
  expect(JSON.parse(mockStorage.get("card_upload_queue_v1")!)[0].id).toBe("second");
});

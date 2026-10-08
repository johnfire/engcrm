import * as Clipboard from "expo-clipboard";
import { client } from "../../services/api";
import { copyMessage, fetchSavedMessages, saveMessage } from "../../services/saved-messages";

jest.mock("../../services/api", () => ({ client: { get: jest.fn(), put: jest.fn(), post: jest.fn() } }));
jest.mock("expo-clipboard", () => ({ setStringAsync: jest.fn() }));
const wording = { title: " label ", body: "  α\r\n\n🙂\t  " };
const stored = { ...wording, id: 7, version: 1, created_at: "2026-10-08", updated_at: "2026-10-08" };

beforeEach(() => jest.clearAllMocks());

it("loads the private account library", async () => {
  (client.get as jest.Mock).mockResolvedValue({ data: [stored] });
  expect(await fetchSavedMessages()).toEqual([stored]);
  expect(client.get).toHaveBeenCalledWith("/api/saved-messages");
});

it("creates and edits messages without changing whitespace or inserting recipient names", async () => {
  (client.post as jest.Mock).mockResolvedValue({ data: stored });
  (client.put as jest.Mock).mockResolvedValue({ data: { ...stored, version: 2 } });
  expect(await saveMessage(wording)).toEqual(stored);
  expect(client.post).toHaveBeenCalledWith("/api/saved-messages", wording);
  await saveMessage(wording, stored);
  expect(client.put).toHaveBeenCalledWith("/api/saved-messages/7", { ...wording, version: 1 });
});

it("copies only the exact body and reports clipboard failure", async () => {
  (Clipboard.setStringAsync as jest.Mock).mockResolvedValueOnce(true).mockResolvedValueOnce(false);
  await copyMessage(wording.body);
  expect(Clipboard.setStringAsync).toHaveBeenCalledWith(wording.body);
  await expect(copyMessage(wording.body)).rejects.toThrow("Clipboard unavailable");
});

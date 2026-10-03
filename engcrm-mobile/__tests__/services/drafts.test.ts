const store: Record<string, string> = {};
jest.mock("@react-native-async-storage/async-storage", () => ({
  __esModule: true,
  default: {
    getItem: jest.fn(async (k: string) => (k in store ? store[k] : null)),
    setItem: jest.fn(async (k: string, v: string) => { store[k] = v; }),
    removeItem: jest.fn(async (k: string) => { delete store[k]; }),
  },
}));
import AsyncStorage from "@react-native-async-storage/async-storage";
const mockStorage = AsyncStorage as unknown as { getItem: jest.Mock; setItem: jest.Mock; removeItem: jest.Mock };

import { clearDraft, loadDraft, saveDraft } from "../../services/drafts";
import { notifyChanged, onChanged, organizationKey, personKey } from "../../services/refreshBus";

const draft = { note: "hello", method: "phone", followUp: "1w", followUpText: "quote" };

describe("drafts", () => {
  beforeEach(() => {
    for (const k of Object.keys(store)) delete store[k];
    jest.clearAllMocks();
  });

  it("round-trips a draft", async () => {
    await saveDraft("organization:1", draft);
    expect(await loadDraft("organization:1")).toEqual(draft);
  });

  it("keeps drafts for different records apart", async () => {
    await saveDraft("organization:1", draft);
    expect(await loadDraft("organization:2")).toBeNull();
    expect(await loadDraft("person:1")).toBeNull();
  });

  it("removes the draft once it is empty, and clearDraft removes it", async () => {
    await saveDraft("organization:1", draft);
    await saveDraft("organization:1", { ...draft, note: "  ", followUpText: "" });
    expect(await loadDraft("organization:1")).toBeNull();
    await saveDraft("organization:1", draft);
    await clearDraft("organization:1");
    expect(await loadDraft("organization:1")).toBeNull();
  });

  it("tolerates corrupt or partial stored data", async () => {
    store["meeting_draft_v1:a"] = "{not json";
    expect(await loadDraft("a")).toBeNull();
    store["meeting_draft_v1:b"] = JSON.stringify({ method: "phone" });
    expect(await loadDraft("b")).toBeNull();
    store["meeting_draft_v1:c"] = JSON.stringify({ note: "x" });
    expect(await loadDraft("c")).toEqual({ note: "x", method: null, followUp: "none", followUpText: "" });
  });

  it("never throws when storage fails", async () => {
    mockStorage.getItem.mockRejectedValueOnce(new Error("disk"));
    mockStorage.setItem.mockRejectedValueOnce(new Error("full"));
    mockStorage.removeItem.mockRejectedValueOnce(new Error("denied"));
    await expect(loadDraft("x")).resolves.toBeNull();
    await expect(saveDraft("x", draft)).resolves.toBeUndefined();
    await expect(clearDraft("x")).resolves.toBeUndefined();
  });
});

describe("refreshBus", () => {
  it("notifies only listeners of that key, and stops after unsubscribe", () => {
    const a = jest.fn();
    const b = jest.fn();
    const offA = onChanged(organizationKey(1), a);
    const offB = onChanged(personKey(1), b);
    notifyChanged(organizationKey(1));
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).not.toHaveBeenCalled();
    offA();
    notifyChanged(organizationKey(1));
    expect(a).toHaveBeenCalledTimes(1);
    offB();
  });

  it("one failing listener does not stop the others", () => {
    const bad = jest.fn(() => { throw new Error("x"); });
    const good = jest.fn();
    const off1 = onChanged("k", bad);
    const off2 = onChanged("k", good);
    expect(() => notifyChanged("k")).not.toThrow();
    expect(good).toHaveBeenCalled();
    off1(); off2();
  });

  it("notifying a key nobody watches is harmless", () => {
    expect(() => notifyChanged("nobody")).not.toThrow();
  });
});

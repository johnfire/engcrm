const mockCalls: string[] = [];
const mockSecure = new Map<string, string>();

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async (key: string) => mockSecure.get(key) ?? null),
  setItemAsync: jest.fn(async (key: string, value: string) => { mockSecure.set(key, value); }),
  deleteItemAsync: jest.fn(async (key: string) => { mockSecure.delete(key); }),
}));
jest.mock("../../services/auth", () => ({
  clearToken: jest.fn(async () => { mockCalls.push("clearToken"); }),
}));
jest.mock("../../services/fieldMode", () => ({
  stopFieldMode: jest.fn(async () => { mockCalls.push("stopFieldMode"); }),
  clearFieldData: jest.fn(async () => { mockCalls.push("clearFieldData"); }),
}));
jest.mock("../../services/cardQueue", () => ({
  clearCardQueue: jest.fn(async () => { mockCalls.push("clearCardQueue"); }),
}));
jest.mock("../../services/drafts", () => ({
  clearAllDrafts: jest.fn(async () => { mockCalls.push("clearAllDrafts"); }),
}));

import { endSession, recordSignIn } from "../../services/session-end";
import { stopFieldMode } from "../../services/fieldMode";

const PURGED = ["clearFieldData", "clearCardQueue", "clearAllDrafts"];

beforeEach(() => {
  mockCalls.length = 0;
  mockSecure.clear();
  jest.clearAllMocks();
});

describe("endSession", () => {
  it("stops field mode before the token is cleared, so queued points still upload", async () => {
    await endSession();
    expect(mockCalls).toEqual(["stopFieldMode", "clearToken"]);
  });

  it("still clears the token when stopping field mode fails", async () => {
    (stopFieldMode as jest.Mock).mockRejectedValueOnce(new Error("service gone"));
    await endSession();
    expect(mockCalls).toEqual(["clearToken"]);
  });
});

describe("recordSignIn", () => {
  it("keeps queued data when the same account signs in again, however it is typed", async () => {
    await recordSignIn("Chris@Example.test");
    await recordSignIn("  chris@example.TEST ");
    expect(mockCalls).toEqual([]);
  });

  it("purges queued captures, points and drafts when a different account signs in", async () => {
    await recordSignIn("a@example.test");
    await recordSignIn("b@example.test");
    expect([...mockCalls].sort()).toEqual([...PURGED].sort());
  });

  it("remembers the newest account, so switching back purges again", async () => {
    await recordSignIn("a@example.test");
    await recordSignIn("b@example.test");
    mockCalls.length = 0;
    await recordSignIn("a@example.test");
    expect([...mockCalls].sort()).toEqual([...PURGED].sort());
  });

  it("does not purge on the very first sign-in, when no earlier account is known", async () => {
    await recordSignIn("a@example.test");
    expect(mockCalls).toEqual([]);
    expect(mockSecure.get("engcrm_last_account")).toBe("a@example.test");
  });

  it("still records the account when one of the purges fails", async () => {
    const { clearCardQueue } = jest.requireMock("../../services/cardQueue");
    await recordSignIn("a@example.test");
    clearCardQueue.mockRejectedValueOnce(new Error("disk"));
    await recordSignIn("b@example.test");
    expect(mockSecure.get("engcrm_last_account")).toBe("b@example.test");
    expect(mockCalls).toEqual(expect.arrayContaining(["clearFieldData", "clearAllDrafts"]));
  });
});

import { getSession } from "../../services/auth";
import { openLocalDatabase } from "../../services/local-database";
import { openOfflineSession } from "../../services/offline-session";
import { loadVerifiedIdentity, saveVerifiedIdentity } from "../../services/sync-identity-cache";
import { fetchSyncIdentity } from "../../services/sync-network";
import { isOfflineStorageActivatedFor, markOfflineStorageActivated } from "../../services/offline-activation";

jest.mock("../../services/auth", () => ({ getSession: jest.fn() }));
jest.mock("../../services/local-database", () => ({ openLocalDatabase: jest.fn() }));
jest.mock("../../services/sync-identity-cache", () => ({ loadVerifiedIdentity: jest.fn(), saveVerifiedIdentity: jest.fn() }));
jest.mock("../../services/sync-network", () => ({ fetchSyncIdentity: jest.fn() }));
jest.mock("../../services/offline-activation", () => ({ markOfflineStorageActivated: jest.fn(), isOfflineStorageActivatedFor: jest.fn() }));

const identity = { environment: "production" as const, workspaceId: 3, userId: 5 };

beforeEach(() => {
  jest.resetAllMocks();
  jest.mocked(getSession).mockResolvedValue({ token: "token", role: "admin", server: "production" });
  jest.mocked(openLocalDatabase).mockResolvedValue({} as never);
  jest.mocked(markOfflineStorageActivated).mockResolvedValue();
  jest.mocked(isOfflineStorageActivatedFor).mockResolvedValue(true);
});

it("does not open a different account when recovering after offline mode was switched off", async () => {
  jest.mocked(loadVerifiedIdentity).mockResolvedValue(identity);
  jest.mocked(isOfflineStorageActivatedFor).mockResolvedValue(false);
  await expect(openOfflineSession(true)).rejects.toThrow("not activated");
  expect(openLocalDatabase).not.toHaveBeenCalled();
});

it("does not open the database when its activation marker cannot be recorded", async () => {
  jest.mocked(loadVerifiedIdentity).mockResolvedValue(identity);
  jest.mocked(markOfflineStorageActivated).mockRejectedValue(new Error("secure storage unavailable"));
  await expect(openOfflineSession()).rejects.toThrow("secure storage unavailable");
  expect(openLocalDatabase).not.toHaveBeenCalled();
});

it("opens an already verified account locally without waiting for a network request", async () => {
  jest.mocked(loadVerifiedIdentity).mockResolvedValue(identity);
  expect((await openOfflineSession()).identity).toEqual(identity);
  expect(fetchSyncIdentity).not.toHaveBeenCalled();
  expect(openLocalDatabase).toHaveBeenCalledWith(identity);
});

it("verifies a first-time identity and caches it only while the session remains the same", async () => {
  jest.mocked(loadVerifiedIdentity).mockResolvedValue(null);
  jest.mocked(fetchSyncIdentity).mockResolvedValue(identity);
  await openOfflineSession();
  expect(saveVerifiedIdentity).toHaveBeenCalledWith("token", identity);
});

it("does not expose a database if the session changes while it opens", async () => {
  jest.mocked(loadVerifiedIdentity).mockResolvedValue(identity);
  jest.mocked(getSession).mockResolvedValueOnce({ token: "token", role: "admin", server: "production" })
    .mockResolvedValueOnce({ token: "different", role: "admin", server: "production" });
  await expect(openOfflineSession()).rejects.toThrow("session changed");
});

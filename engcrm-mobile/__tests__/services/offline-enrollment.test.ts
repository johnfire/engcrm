import axios from "axios";

import { markOfflineStorageActivated } from "../../services/offline-activation";
import { activateOfflineStorage } from "../../services/offline-enrollment";
import { ensureOfflineSessionUnchanged, resolveOfflineIdentity } from "../../services/offline-identity";

jest.mock("axios", () => ({ create: jest.fn() }));
jest.mock("../../services/offline-activation", () => ({ markOfflineStorageActivated: jest.fn() }));
jest.mock("../../services/offline-identity", () => ({ resolveOfflineIdentity: jest.fn(), ensureOfflineSessionUnchanged: jest.fn() }));

const identity = { environment: "reviewer" as const, workspaceId: 3, userId: 5 };
const get = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(resolveOfflineIdentity).mockResolvedValue({ identity, token: "account-token", server: "reviewer" });
  jest.mocked(axios.create).mockReturnValue({ get } as never);
  jest.mocked(ensureOfflineSessionUnchanged).mockResolvedValue();
  jest.mocked(markOfflineStorageActivated).mockResolvedValue();
});

it("activates only after the matching server says writes are enabled", async () => {
  get.mockResolvedValue({ data: { offline_writes_enabled: true } });
  await activateOfflineStorage();
  expect(axios.create).toHaveBeenCalledWith(expect.objectContaining({ baseURL: expect.stringContaining("/reviewer"),
    headers: { Authorization: "Bearer account-token" } }));
  expect(get).toHaveBeenCalledWith("/api/sync/capabilities");
  expect(markOfflineStorageActivated).toHaveBeenCalledWith(identity);
});

it("keeps offline mode off when the server is not ready or the account changes", async () => {
  get.mockResolvedValueOnce({ data: { offline_writes_enabled: false } }).mockResolvedValueOnce({ data: { offline_writes_enabled: true } });
  await expect(activateOfflineStorage()).rejects.toThrow("not ready");
  jest.mocked(ensureOfflineSessionUnchanged).mockRejectedValueOnce(new Error("session changed"));
  await expect(activateOfflineStorage()).rejects.toThrow("session changed");
  expect(markOfflineStorageActivated).not.toHaveBeenCalled();
});

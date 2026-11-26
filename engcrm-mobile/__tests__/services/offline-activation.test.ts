import * as SecureStore from "expo-secure-store";

import { hasActivatedOfflineStorage, markOfflineStorageActivated } from "../../services/offline-activation";
import { resolveOfflineIdentity } from "../../services/offline-identity";

jest.mock("../../services/offline-identity", () => ({ resolveOfflineIdentity: jest.fn() }));
const identity = { environment: "reviewer" as const, workspaceId: 3, userId: 5 };

it("records and reads the durable offline activation marker", async () => {
  jest.mocked(resolveOfflineIdentity).mockResolvedValue({ identity, token: "test", server: "reviewer" });
  jest.mocked(SecureStore.getItemAsync).mockResolvedValueOnce(null).mockResolvedValueOnce("1").mockResolvedValueOnce("1");
  expect(await hasActivatedOfflineStorage()).toBe(false);
  await markOfflineStorageActivated(identity);
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith("engcrm_offline_reviewer_3_5", "1", expect.any(Object));
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith("engcrm_offline_storage_activated", "1", expect.any(Object));
  expect(await hasActivatedOfflineStorage()).toBe(true);
});

it("does not activate offline storage for a different account or environment", async () => {
  jest.mocked(resolveOfflineIdentity).mockResolvedValue({ identity: { ...identity, environment: "production" },
    token: "test", server: "production" });
  jest.mocked(SecureStore.getItemAsync).mockResolvedValueOnce("1").mockResolvedValueOnce(null);
  expect(await hasActivatedOfflineStorage()).toBe(false);
  expect(SecureStore.getItemAsync).toHaveBeenLastCalledWith("engcrm_offline_production_3_5", expect.any(Object));
});

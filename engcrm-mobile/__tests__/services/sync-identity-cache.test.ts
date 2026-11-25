import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import { loadVerifiedIdentity, saveVerifiedIdentity } from "../../services/sync-identity-cache";

jest.mock("expo-crypto", () => ({ CryptoDigestAlgorithm: { SHA256: "SHA-256" }, digestStringAsync: jest.fn() }));

beforeEach(() => jest.clearAllMocks());

it("opens a cached identity only for the same token and environment", async () => {
  jest.mocked(Crypto.digestStringAsync).mockResolvedValue("token-hash");
  await saveVerifiedIdentity("secret-token", { environment: "production", workspaceId: 3, userId: 5 });
  const saved = jest.mocked(SecureStore.setItemAsync).mock.calls[0][1];
  expect(saved).not.toContain("secret-token");
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(saved);
  await expect(loadVerifiedIdentity("secret-token", "production")).resolves.toEqual({ environment: "production", workspaceId: 3, userId: 5 });
  await expect(loadVerifiedIdentity("secret-token", "reviewer")).resolves.toBeNull();
  jest.mocked(Crypto.digestStringAsync).mockResolvedValue("different-token-hash");
  await expect(loadVerifiedIdentity("another-token", "production")).resolves.toBeNull();
});

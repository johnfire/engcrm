import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import type { LocalDatabaseIdentity } from "./local-database";
import type { Server } from "./reviewer-routing";

const IDENTITY_KEY = "engcrm_verified_sync_identity";
const secureOptions = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

export async function saveVerifiedIdentity(token: string, identity: LocalDatabaseIdentity): Promise<void> {
  const fingerprint = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, token);
  await SecureStore.setItemAsync(IDENTITY_KEY, JSON.stringify({ fingerprint, ...identity }), secureOptions);
}

export async function loadVerifiedIdentity(token: string, environment: Server): Promise<LocalDatabaseIdentity | null> {
  const stored = await SecureStore.getItemAsync(IDENTITY_KEY, secureOptions);
  if (!stored) return null;
  try {
    const identity: unknown = JSON.parse(stored);
    if (!identity || typeof identity !== "object" || !("fingerprint" in identity) ||
        !("environment" in identity) || !("workspaceId" in identity) || !("userId" in identity)) return null;
    const fingerprint = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, token);
    if (identity.fingerprint !== fingerprint || identity.environment !== environment ||
        !Number.isSafeInteger(identity.workspaceId) || (identity.workspaceId as number) < 1 ||
        !Number.isSafeInteger(identity.userId) || (identity.userId as number) < 1) return null;
    return { environment, workspaceId: identity.workspaceId as number, userId: identity.userId as number };
  } catch {
    return null;
  }
}

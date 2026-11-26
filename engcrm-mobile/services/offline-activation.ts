import * as SecureStore from "expo-secure-store";
import type { LocalDatabaseIdentity } from "./local-database";
import { resolveOfflineIdentity } from "./offline-identity";

const ACTIVATION_KEY = "engcrm_offline_storage_activated";
const SECURE_OPTIONS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

export async function hasActivatedOfflineStorage(): Promise<boolean> {
  if ((await SecureStore.getItemAsync(ACTIVATION_KEY, SECURE_OPTIONS)) !== "1") return false;
  const { identity } = await resolveOfflineIdentity();
  return isOfflineStorageActivatedFor(identity);
}

function accountKey(identity: LocalDatabaseIdentity): string {
  return `engcrm_offline_${identity.environment}_${identity.workspaceId}_${identity.userId}`;
}

export async function isOfflineStorageActivatedFor(identity: LocalDatabaseIdentity): Promise<boolean> {
  return (await SecureStore.getItemAsync(accountKey(identity), SECURE_OPTIONS)) === "1";
}

export async function markOfflineStorageActivated(identity: LocalDatabaseIdentity): Promise<void> {
  await SecureStore.setItemAsync(accountKey(identity), "1", SECURE_OPTIONS);
  await SecureStore.setItemAsync(ACTIVATION_KEY, "1", SECURE_OPTIONS);
}

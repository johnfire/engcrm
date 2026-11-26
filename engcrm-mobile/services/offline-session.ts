import { type LocalDatabaseIdentity, openLocalDatabase } from "./local-database";
import { isOfflineStorageActivatedFor, markOfflineStorageActivated } from "./offline-activation";
import { ensureOfflineSessionUnchanged, resolveOfflineIdentity } from "./offline-identity";

export async function openOfflineSession(requireActivation = false): Promise<{
  identity: LocalDatabaseIdentity;
  database: Awaited<ReturnType<typeof openLocalDatabase>>;
}> {
  const { identity, token, server } = await resolveOfflineIdentity();
  if (requireActivation && !await isOfflineStorageActivatedFor(identity)) throw new Error("Offline storage is not activated for this account");
  await markOfflineStorageActivated(identity);
  const database = await openLocalDatabase(identity);
  await ensureOfflineSessionUnchanged(token, server);
  return { identity, database };
}

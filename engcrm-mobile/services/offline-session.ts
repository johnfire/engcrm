import { getSession } from "./auth";
import { type LocalDatabaseIdentity, openLocalDatabase } from "./local-database";
import type { Server } from "./reviewer-routing";
import { loadVerifiedIdentity, saveVerifiedIdentity } from "./sync-identity-cache";
import { fetchSyncIdentity } from "./sync-network";

async function ensureSessionUnchanged(token: string, server: Server): Promise<void> {
  const current = await getSession();
  if (current.token !== token || current.server !== server) throw new Error("Sync session changed while opening offline data");
}

export async function openOfflineSession(): Promise<{
  identity: LocalDatabaseIdentity;
  database: Awaited<ReturnType<typeof openLocalDatabase>>;
}> {
  const session = await getSession();
  if (!session.token) throw new Error("Sign in to open offline data");
  let identity = await loadVerifiedIdentity(session.token, session.server);
  if (!identity) {
    identity = await fetchSyncIdentity(session.server);
    await ensureSessionUnchanged(session.token, session.server);
    await saveVerifiedIdentity(session.token, identity);
  }
  const database = await openLocalDatabase(identity);
  await ensureSessionUnchanged(session.token, session.server);
  return { identity, database };
}

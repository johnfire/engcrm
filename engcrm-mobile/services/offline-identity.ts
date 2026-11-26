import { getSession } from "./auth";
import type { LocalDatabaseIdentity } from "./local-database";
import type { Server } from "./reviewer-routing";
import { loadVerifiedIdentity, saveVerifiedIdentity } from "./sync-identity-cache";
import { fetchSyncIdentity } from "./sync-network";

export async function ensureOfflineSessionUnchanged(token: string, server: Server): Promise<void> {
  const current = await getSession();
  if (current.token !== token || current.server !== server) throw new Error("Sync session changed while opening offline data");
}

export async function resolveOfflineIdentity(): Promise<{ identity: LocalDatabaseIdentity; token: string; server: Server }> {
  const session = await getSession();
  if (!session.token) throw new Error("Sign in to open offline data");
  let identity = await loadVerifiedIdentity(session.token, session.server);
  if (!identity) {
    identity = await fetchSyncIdentity(session.server);
    await ensureOfflineSessionUnchanged(session.token, session.server);
    await saveVerifiedIdentity(session.token, identity);
  }
  return { identity, token: session.token, server: session.server };
}

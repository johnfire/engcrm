import { getSession } from "./auth";
import { createBoundSyncNetwork } from "./bound-sync-network";
import type { openOfflineSession } from "./offline-session";
import { synchronizeCycle } from "./sync-cycle";
import { loadVerifiedIdentity } from "./sync-identity-cache";
import { getSyncDeviceId } from "./sync-network";

export async function synchronizeOfflineSession(offline: Awaited<ReturnType<typeof openOfflineSession>>, appVersion: string): Promise<void> {
  const session = await getSession();
  if (!session.token || session.server !== offline.identity.environment) throw new Error("Sign in to the matching account to sync");
  const verified = await loadVerifiedIdentity(session.token, session.server);
  if (!verified || verified.workspaceId !== offline.identity.workspaceId || verified.userId !== offline.identity.userId ||
      verified.environment !== offline.identity.environment) throw new Error("Offline data belongs to another account");
  const deviceId = await getSyncDeviceId();
  const network = createBoundSyncNetwork(session.token, session.server, deviceId, appVersion);
  await synchronizeCycle(offline.database, deviceId, network);
}

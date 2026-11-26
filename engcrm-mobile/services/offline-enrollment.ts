import axios from "axios";

import { baseForServer } from "./api-origin";
import { markOfflineStorageActivated } from "./offline-activation";
import { ensureOfflineSessionUnchanged, resolveOfflineIdentity } from "./offline-identity";

export async function activateOfflineStorage(): Promise<void> {
  const { identity, token, server } = await resolveOfflineIdentity();
  const client = axios.create({ baseURL: baseForServer(server), headers: { Authorization: `Bearer ${token}` } });
  const response = await client.get("/api/sync/capabilities");
  await ensureOfflineSessionUnchanged(token, server);
  if (response.data?.offline_writes_enabled !== true) throw new Error("Offline sync is not ready on this server");
  await markOfflineStorageActivated(identity);
  await ensureOfflineSessionUnchanged(token, server);
}

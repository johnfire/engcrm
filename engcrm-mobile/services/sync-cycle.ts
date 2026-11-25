import { withLocalRead, withLocalWrite } from "./local-transaction";
import { synchronizeBootstrap } from "./sync-bootstrap-worker";
import { synchronizePull } from "./sync-pull-worker";
import { type OutboxDatabase, synchronizeOutbox } from "./sync-push-worker";

export interface SyncNetwork {
  register(): Promise<void>;
  bootstrap(token: string | null): Promise<unknown>;
  pull(cursor: number): Promise<unknown>;
  push?(mutations: Record<string, unknown>[]): Promise<unknown>;
}

const activeCycles = new WeakMap<OutboxDatabase, { deviceId: string; promise: Promise<void> }>();

async function runCycle(database: OutboxDatabase, deviceId: string, network: SyncNetwork): Promise<void> {
  const pending = await withLocalRead(database, () => database.getFirstAsync<{ count: number }>("SELECT count(*) AS count FROM sync_outbox"));
  if (pending && pending.count > 0 && !network.push) throw new Error("Cannot synchronize pending edits until offline writes are enabled");
  await network.register();
  const state = await withLocalRead(database, () => database.getFirstAsync<{ active_generation: number | null }>(
    "SELECT active_generation FROM sync_state WHERE singleton=1",
  ));
  const loading = await withLocalRead(database, () => database.getFirstAsync<{ id: number }>(
    "SELECT id FROM bootstrap_generations WHERE status='loading' LIMIT 1",
  ));
  if (pending && pending.count > 0 && network.push) await synchronizeOutbox(database, network.push);
  if ((!state?.active_generation || loading) && pending && pending.count > 0) {
    const remaining = await withLocalRead(database, () => database.getFirstAsync<{ count: number }>("SELECT count(*) AS count FROM sync_outbox"));
    if (remaining && remaining.count > 0) throw new Error("Cannot switch bootstrap generation while edits are pending");
  }
  if (!state?.active_generation || loading) await synchronizeBootstrap(database, deviceId, network.bootstrap);
  await synchronizePull(database, network.pull);
  await withLocalWrite(database, async () => {
    const unsent = await database.getFirstAsync<{ count: number }>("SELECT count(*) AS count FROM sync_outbox");
    if (unsent?.count === 0) await database.runAsync("UPDATE sync_state SET last_success_at=CURRENT_TIMESTAMP WHERE singleton=1");
  });
}

export function synchronizeCycle(database: OutboxDatabase, deviceId: string, network: SyncNetwork): Promise<void> {
  const active = activeCycles.get(database);
  if (active) {
    if (active.deviceId !== deviceId) return Promise.reject(new Error("A different device is already synchronizing"));
    return active.promise;
  }
  const promise = runCycle(database, deviceId, network).finally(() => activeCycles.delete(database));
  activeCycles.set(database, { deviceId, promise });
  return promise;
}

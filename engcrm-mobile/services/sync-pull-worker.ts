import { savePullPage } from "./local-pull";
import type { LocalDatabase } from "./local-transaction";
import { parsePullPage } from "./sync-contracts";

type ChangeFetcher = (cursor: number) => Promise<unknown>;
const activePulls = new WeakMap<LocalDatabase, Promise<void>>();

async function pullUntilCurrent(database: LocalDatabase, fetchPage: ChangeFetcher): Promise<void> {
  const state = await database.getFirstAsync<{ cursor: number; active_generation: number | null }>(
    "SELECT cursor,active_generation FROM sync_state WHERE singleton=1",
  );
  if (!state || state.active_generation === null) throw new Error("Offline database needs its first bootstrap");
  let cursor = state.cursor;
  while (true) {
    const page = parsePullPage(await fetchPage(cursor));
    if (page.has_more && page.next_cursor <= cursor) throw new Error("Sync cursor did not advance");
    await savePullPage(database, cursor, page);
    cursor = page.next_cursor;
    if (!page.has_more) return;
  }
}

export function synchronizePull(database: LocalDatabase, fetchPage: ChangeFetcher): Promise<void> {
  const active = activePulls.get(database);
  if (active) return active;
  const promise = pullUntilCurrent(database, fetchPage).finally(() => activePulls.delete(database));
  activePulls.set(database, promise);
  return promise;
}

import { abandonBootstrap, beginBootstrap, saveBootstrapPage } from "./local-bootstrap";
import type { LocalDatabase } from "./local-transaction";
import { parseBootstrapPage } from "./sync-contracts";

type PageFetcher = (token: string | null) => Promise<unknown>;
export class BootstrapExpiredError extends Error {}
const activeBootstraps = new WeakMap<LocalDatabase, { deviceId: string; promise: Promise<void> }>();

async function downloadBootstrap(database: LocalDatabase, deviceId: string, fetchPage: PageFetcher): Promise<void> {
  let generation = await beginBootstrap(database, deviceId);
  let token = generation.token;
  let hasRestarted = false;
  while (true) {
    let response: unknown;
    try {
      response = await fetchPage(token);
    } catch (error) {
      if (!(error instanceof BootstrapExpiredError) || token === null || hasRestarted) throw error;
      await abandonBootstrap(database, generation.id);
      generation = await beginBootstrap(database, deviceId);
      token = null;
      hasRestarted = true;
      continue;
    }
    const page = parseBootstrapPage(response);
    if (page.next_token !== null && page.next_token === token) throw new Error("Bootstrap continuation did not advance");
    await saveBootstrapPage(database, generation.id, token, page);
    if (page.next_token === null) return;
    token = page.next_token;
  }
}

export function synchronizeBootstrap(database: LocalDatabase, deviceId: string, fetchPage: PageFetcher): Promise<void> {
  const active = activeBootstraps.get(database);
  if (active) {
    if (active.deviceId !== deviceId) return Promise.reject(new Error("A different device is already bootstrapping"));
    return active.promise;
  }
  const promise = downloadBootstrap(database, deviceId, fetchPage).finally(() => activeBootstraps.delete(database));
  activeBootstraps.set(database, { deviceId, promise });
  return promise;
}

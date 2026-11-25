import axios from "axios";

import { baseForServer } from "./api-origin";
import { getSession } from "./auth";
import type { Server } from "./reviewer-routing";
import { BootstrapExpiredError } from "./sync-bootstrap-worker";
import type { SyncNetwork } from "./sync-cycle";
import { isExpiredBootstrap, isSingleMutationConflict } from "./sync-errors";

export function createBoundSyncNetwork(token: string, environment: Server, deviceId: string, appVersion: string): SyncNetwork {
  const client = axios.create({ baseURL: baseForServer(environment), headers: { Authorization: `Bearer ${token}` } });
  async function assertSession(): Promise<void> {
    const session = await getSession();
    if (session.token !== token || session.server !== environment) throw new Error("Sync session changed");
  }
  async function guarded<T>(operation: () => Promise<T>): Promise<T> {
    await assertSession();
    const result = await operation();
    await assertSession();
    return result;
  }
  return {
    register: () => guarded(async () => {
      const response = await client.post("/api/sync/devices", { device_id: deviceId, server_environment: environment,
        app_version: appVersion, schema_version: 1 });
      if (response.data?.protocol_version !== 1 || typeof response.data.bootstrap_required !== "boolean") {
        throw new Error("Server returned an unsupported sync protocol");
      }
    }),
    bootstrap: (continuation) => guarded(async () => {
      try {
        return (await client.get("/api/sync/bootstrap", { params: { device_id: deviceId, server_environment: environment,
          ...(continuation ? { token: continuation } : {}) } })).data;
      } catch (error) {
        if (isExpiredBootstrap(error)) throw new BootstrapExpiredError("Bootstrap continuation expired");
        throw error;
      }
    }),
    pull: (cursor) => guarded(async () => (await client.get("/api/sync/changes", {
      params: { device_id: deviceId, server_environment: environment, after: cursor },
    })).data),
    push: (mutations) => guarded(async () => {
      try {
        return (await client.post("/api/sync/push", { server_environment: environment, mutations })).data;
      } catch (error) {
        if (isSingleMutationConflict(error, mutations)) {
          return { outcomes: [{ mutation_id: mutations[0].mutation_id, status: "conflict", entity: null }] };
        }
        throw error;
      }
    }),
    reviewOutcomes: (mutationIds) => guarded(async () => (await client.post("/api/sync/review-outcomes", {
      device_id: deviceId, server_environment: environment, mutation_ids: mutationIds,
    })).data),
    offers: () => guarded(async () => (await client.get("/api/offers")).data),
  };
}

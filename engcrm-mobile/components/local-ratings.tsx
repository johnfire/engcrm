import * as Crypto from "expo-crypto";

import { queueLocalUpdate } from "../services/local-outbox";
import type { LocalRecord } from "../services/local-records";
import { useOffline } from "../services/offline-context";
import { getSyncDeviceId } from "../services/sync-network";
import { PersonalPrioritySelector } from "./PersonalPrioritySelector";
import { ValueRatings } from "./ValueRatings";

export function LocalRatings({ item, kind }: { item: LocalRecord; kind: "person" | "organization" }) {
  const { session, refreshStatus, requestSync } = useOffline();
  async function save(field: string, value: number | null) {
    if (!session) throw new Error("Offline account is unavailable");
    const changedAt = new Date().toISOString();
    await queueLocalUpdate(session.database, { mutationId: Crypto.randomUUID(), deviceId: await getSyncDeviceId(),
      entityKind: kind, entitySyncId: item.syncId, changedAt, patch: { [field]: value } });
    void refreshStatus().catch(() => {});
    requestSync();
  }
  const rating = (field: string) => typeof item.fields[field] === "number" ? item.fields[field] as number : null;
  const priorityField = kind === "person" ? "value_rating" : "personal_priority";
  return <>
    <PersonalPrioritySelector kind={kind} priority={rating(priorityField)} onSave={(value) => save(priorityField, value)} />
    <ValueRatings shortTerm={rating("short_term_value")} longTerm={rating("long_term_value")}
      onSave={(horizon, value) => save(horizon === "short-term" ? "short_term_value" : "long_term_value", value)} />
  </>;
}

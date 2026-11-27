import * as Crypto from "expo-crypto";
import { Text, View } from "react-native";

import type { LocalRecord } from "../services/local-records";
import { queueLocalUpdate } from "../services/local-outbox";
import { useOffline } from "../services/offline-context";
import { PIPELINE_STAGES, STATUSES, type OrganizationStatus, type PipelineStage } from "../services/organizationState";
import { getSyncDeviceId } from "../services/sync-network";
import { PersonNextStep } from "./PersonNextStep";
import { StageStatusPicker } from "./StageStatusPicker";

export function LocalDealCard({ deal, canEdit }: { deal: LocalRecord; canEdit: boolean }) {
  const { session, requestSync, refreshStatus } = useOffline();
  const stage = deal.fields.pipeline_stage, status = deal.fields.status;
  const known = typeof stage === "string" && PIPELINE_STAGES.includes(stage as PipelineStage) &&
    typeof status === "string" && STATUSES.includes(status as OrganizationStatus);
  const step = typeof deal.fields.next_step === "string" ? deal.fields.next_step : null;
  const date = typeof deal.fields.next_step_date === "string" ? deal.fields.next_step_date : null;
  async function save(patch: Record<string, string | null>): Promise<void> {
    if (!session) throw new Error("Offline account is unavailable");
    const changedAt = new Date().toISOString();
    await queueLocalUpdate(session.database, { mutationId: Crypto.randomUUID(), deviceId: await getSyncDeviceId(),
      entityKind: "deal", entitySyncId: deal.syncId, changedAt, patch });
    void Promise.resolve(refreshStatus()).catch(() => {});
    requestSync();
  }
  return <View>
    <Text style={{ color: "#fff", fontSize: 15 }}>{String(deal.fields.offer_name ?? deal.fields.offer_slug ?? "")}</Text>
    {known && (canEdit ? <StageStatusPicker key={`${deal.syncId}:${stage}:${status}`} stage={stage as PipelineStage}
      status={status as OrganizationStatus} onSave={async (change) => save({
        ...(change.pipeline_stage ? { pipeline_stage: change.pipeline_stage } : {}),
        ...(change.status ? { status: change.status } : {}),
      })} />
      : <Text style={{ color: "#bbb" }}>{String(stage)} · {String(status)}</Text>)}
    <PersonNextStep step={step} date={date} canEdit={canEdit} onSaved={() => {}} save={async (nextStep, nextDate, type) => {
      await save({ next_step: nextStep, next_step_date: nextDate, ...(type ? { task_type: type } : {}) });
      return { next_step: nextStep, next_step_date: nextDate };
    }} />
  </View>;
}

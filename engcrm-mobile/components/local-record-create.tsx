import * as Crypto from "expo-crypto";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Text } from "react-native";
import { useRouter } from "expo-router";

import { useLocalOffers } from "../hooks/useLocalOffers";
import { useTranslation } from "../i18n/I18nContext";
import { getLastOffer, setLastOffer } from "../services/deals";
import { queueLocalCreate, queueLocalCreateWithInitialDeal } from "../services/local-outbox";
import { useOffline } from "../services/offline-context";
import { type PipelineStage } from "../services/organizationState";
import { ORGANIZATION_FIELDS, PERSON_FIELDS } from "../services/recordFields";
import { getSyncDeviceId } from "../services/sync-network";
import { useAdminRole } from "../services/use-admin-role";
import { BusinessStagePicker } from "./business-stage-picker";
import { OfferPicker } from "./OfferPicker";
import { PersonStagePicker } from "./PersonStagePicker";
import { RecordForm, type Values } from "./RecordForm";

type Kind = "person" | "organization";

export function LocalRecordCreate({ kind, organizationSyncId, initialName }: { kind: Kind; organizationSyncId?: string; initialName?: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const admin = useAdminRole();
  const { session, requestSync, refreshStatus } = useOffline();
  const offers = useLocalOffers();
  const [offer, setOffer] = useState("consulting");
  const [offerChosen, setOfferChosen] = useState(false);
  const [stage, setStage] = useState<PipelineStage | null>(kind === "organization" ? "candidate" : null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const offerChosenRef = useRef(false);
  const unavailable = stage !== null && offerChosen && offers.length > 0 && !offers.some((item) => item.slug === offer);
  const chosen = !offerChosen && offers.length && !offers.some((item) => item.slug === offer)
    ? offers.find((item) => item.slug === "consulting")?.slug ?? offers[0].slug : offer;

  useEffect(() => {
    let active = true;
    getLastOffer().then((saved) => { if (active && !offerChosenRef.current) setOffer(saved); });
    return () => { active = false; };
  }, []);

  async function save(changed: Values) {
    if (!session || busy.current) return;
    if (unavailable) { setError(t("offlineDetail.offerUnavailable")); return; }
    busy.current = true;
    setSaving(true);
    setError(null);
    const syncId = Crypto.randomUUID();
    const changedAt = new Date().toISOString();
    try {
      const creation = { mutationId: Crypto.randomUUID(), deviceId: await getSyncDeviceId(), entityKind: kind,
        entitySyncId: syncId, changedAt, patch: { ...changed,
          ...(kind === "person" && organizationSyncId ? { organization_sync_id: organizationSyncId } : {}) } };
      if (stage) await queueLocalCreateWithInitialDeal(session.database, creation, { mutationId: Crypto.randomUUID(),
        entitySyncId: Crypto.randomUUID(), offerSlug: chosen, stage, status: "none" });
      else await queueLocalCreate(session.database, creation);
    } catch {
      setError(t("recordForm.saveFailed"));
      busy.current = false;
      setSaving(false);
      return;
    }
    if (stage) void setLastOffer(chosen);
    void refreshStatus();
    requestSync();
    router.replace({ pathname: kind === "person" ? "/(drawer)/person-detail" : "/(drawer)/organization-detail", params: { sync_id: syncId } });
  }

  if (admin === false) return <Text>{t("recordForm.adminOnly")}</Text>;
  if (admin === null || !session) return <ActivityIndicator color="#7c6fff" />;
  return <RecordForm fields={kind === "person" ? PERSON_FIELDS : ORGANIZATION_FIELDS} baseline={{}}
    start={initialName ? { name: initialName } : undefined} saving={saving} error={error ?? (unavailable ? t("offlineDetail.offerUnavailable") : null)}
    submitLabel={t(kind === "person" ? "recordForm.addPerson" : "businessForm.add")} onSubmit={save}>
    <OfferPicker offers={offers} value={chosen} onChange={(value) => { offerChosenRef.current = true; setOfferChosen(true); setOffer(value); }}
      label={t("offerFilter.label")} disabled={saving} />
    {kind === "person" ? <PersonStagePicker stage={stage} onSave={async (value) => setStage(value)} />
      : <BusinessStagePicker stage={stage ?? "candidate"} onChange={setStage} disabled={saving} />}
  </RecordForm>;
}

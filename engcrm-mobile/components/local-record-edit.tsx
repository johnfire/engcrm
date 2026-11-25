import * as Crypto from "expo-crypto";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Text } from "react-native";
import { useRouter } from "expo-router";

import { useTranslation } from "../i18n/I18nContext";
import { queueLocalUpdate } from "../services/local-outbox";
import { readLocalRecord } from "../services/local-records";
import { useOffline } from "../services/offline-context";
import { PERSON_FIELDS, ORGANIZATION_FIELDS } from "../services/recordFields";
import { notifyChanged } from "../services/refreshBus";
import { getSyncDeviceId } from "../services/sync-network";
import { useAdminRole } from "../services/use-admin-role";
import { RecordForm, type Values } from "./RecordForm";

type Kind = "person" | "organization";
export const localRecordKey = (kind: Kind, syncId: string) => `offline:${kind}:${syncId}`;

export function LocalRecordEdit({ kind, syncId }: { kind: Kind; syncId: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const admin = useAdminRole();
  const { session, requestSync, refreshStatus } = useOffline();
  const [loaded, setLoaded] = useState<{ database: object; key: string; values: Values } | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const fields = kind === "person" ? PERSON_FIELDS : ORGANIZATION_FIELDS;
  const key = localRecordKey(kind, syncId);
  const values = session && loaded?.database === session.database && loaded.key === key ? loaded.values : null;

  useEffect(() => {
    let active = true;
    if (session) readLocalRecord(session.database, kind, syncId).then((record) => {
      if (!active) return;
      if (!record) { setLoadError(true); return; }
      const baseline: Values = {};
      for (const field of fields) baseline[field.key] = typeof record.fields[field.key] === "string" ? record.fields[field.key] as string : "";
      setLoaded({ database: session.database, key, values: baseline });
      setLoadError(false);
    }).catch(() => { if (active) setLoadError(true); });
    return () => { active = false; };
  }, [session, kind, syncId, fields, key]);

  async function save(changed: Values) {
    if (!session || busy.current) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    const changedAt = new Date().toISOString();
    try {
      await queueLocalUpdate(session.database, { mutationId: Crypto.randomUUID(), deviceId: await getSyncDeviceId(),
        entityKind: kind, entitySyncId: syncId, changedAt, patch: changed });
      notifyChanged(localRecordKey(kind, syncId));
      void refreshStatus();
      requestSync();
      router.back();
    } catch {
      setError(t("recordForm.saveFailed"));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  if (admin === false) return <Text>{t("recordForm.adminOnly")}</Text>;
  if (loadError && !values) return <Text>{t("offlineDetail.notFound")}</Text>;
  if (admin === null || !values) return <ActivityIndicator color="#7c6fff" />;
  return <RecordForm fields={fields} baseline={values} saving={saving} submitLabel={t("common.save")} error={error} onSubmit={save} />;
}

import { useEffect, useState } from "react";
import { useTranslation } from "../i18n/I18nContext";
import { ContactKind } from "./contact-feed";
import { ContactDateRecord, fetchContactDate, saveContactDate } from "./contact-dates";
import { dateInDays } from "./followUps";
import { notifyChanged, organizationKey, personKey } from "./refreshBus";
import { useAdminRole } from "./use-admin-role";

export function useContactDate(kind: ContactKind, id: number) {
  const { t } = useTranslation();
  const isAdmin = useAdminRole();
  const [record, setRecord] = useState<ContactDateRecord | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    fetchContactDate(kind, id).then((loaded) => {
      if (!active) return;
      setRecord(loaded);
      setSelected(loaded.contact_date ?? dateInDays(0));
    }).catch(() => { if (active) setError(t("contactDate.loadFailed")); });
    return () => { active = false; };
  }, [kind, id, isAdmin, t]);
  async function save(): Promise<boolean> {
    if (!record || saving || !isAdmin) return false;
    setSaving(true);
    setError(null);
    try {
      await saveContactDate(record, selected);
      notifyChanged(kind === "person" ? personKey(id) : organizationKey(id));
      return true;
    } catch (failure: any) {
      const detail = failure?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("contactDate.failed"));
      return false;
    } finally { setSaving(false); }
  }
  return { isAdmin, record, selected, setSelected, error, saving, save };
}

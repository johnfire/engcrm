import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { createPerson, duplicateOf, editPerson, fetchPerson, Person } from "../../services/api";
import { getRole } from "../../services/auth";
import { PipelineStage } from "../../services/organizationState";
import { notifyChanged, personKey } from "../../services/refreshBus";
import { PERSON_FIELDS } from "../../services/recordFields";
import { PersonStagePicker } from "../../components/PersonStagePicker";
import { RecordForm, Values } from "../../components/RecordForm";
import { useTranslation } from "../../i18n/I18nContext";

const VALUE_KEYS = PERSON_FIELDS.map((field) => field.key);

function valuesOf(person: Person): Values {
  const record = person as unknown as Record<string, unknown>;
  const values: Values = {};
  for (const key of VALUE_KEYS) {
    const value = record[key];
    values[key] = typeof value === "string" ? value : "";
  }
  return values;
}

/** Add a person by hand (no id), optionally at an organization (companyId) and
 *  with a starting stage, or change one (id). Admin only. An existing person's
 *  stage is set on their detail screen, where a tap saves it at once. */
export default function EditPersonScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string; name?: string; companyId?: string; companyName?: string }>();
  const id = params.id ? Number(params.id) : null;
  const companyId = params.companyId ? Number(params.companyId) : null;
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [person, setPerson] = useState<Person | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<PipelineStage | null>(null);

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useEffect(() => {
    if (id === null) return;
    let cancelled = false;
    fetchPerson(id)
      .then((loaded) => {
        if (!cancelled) setPerson(loaded);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  function goToDetail(personId: number) {
    router.replace({ pathname: "/(drawer)/person-detail", params: { id: String(personId) } });
  }

  function reportDuplicate(error: unknown): boolean {
    const duplicate = duplicateOf(error);
    if (!duplicate) return false;
    const existingId = duplicate.existingId;
    if (existingId === null) {
      Alert.alert(t("recordForm.duplicateTitle"), t("recordForm.saveFailed"));
      return true;
    }
    Alert.alert(t("recordForm.duplicateTitle"), t("recordForm.duplicatePerson"), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("recordForm.openExisting"), onPress: () => goToDetail(existingId) },
    ]);
    return true;
  }

  async function save(changed: Values) {
    setSaving(true);
    setError(null);
    try {
      if (id === null) {
        const created = await createPerson({
          ...changed,
          ...(companyId !== null ? { contact_id: companyId } : {}),
          ...(stage !== null ? { pipeline_stage: stage } : {}),
        });
        goToDetail(created.id);
      } else {
        await editPerson(id, changed);
        notifyChanged(personKey(id));
        if (router.canGoBack()) router.back();
        else goToDetail(id);
      }
    } catch (err: any) {
      if (!reportDuplicate(err)) setError(err?.response?.data?.detail || t("recordForm.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  if (isAdmin === null || (id !== null && !person && !loadFailed)) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#7c6fff" />
      </View>
    );
  }
  if (!isAdmin) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{t("recordForm.adminOnly")}</Text>
      </View>
    );
  }
  if (id !== null && !person) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{t("personDetail.couldntLoad")}</Text>
      </View>
    );
  }

  const at = id === null ? params.companyName : person?.company;
  return (
    <RecordForm
      fields={PERSON_FIELDS}
      baseline={person ? valuesOf(person) : {}}
      start={id === null && params.name ? { name: params.name } : undefined}
      saving={saving}
      error={error}
      submitLabel={id === null ? t("recordForm.addPerson") : t("recordForm.save")}
      onSubmit={save}
    >
      {!!at && <Text style={styles.at}>{t("recordForm.worksAt", { company: at })}</Text>}
      {id === null && <PersonStagePicker stage={stage} onSave={async (next) => setStage(next)} />}
    </RecordForm>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: "center", flex: 1, justifyContent: "center", padding: 24 },
  muted: { color: "#888", fontSize: 15, textAlign: "center" },
  at: { color: "#999", fontSize: 13, marginTop: 4 },
});

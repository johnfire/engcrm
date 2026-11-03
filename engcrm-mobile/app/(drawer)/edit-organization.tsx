import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  createOrganization,
  duplicateOf,
  editOrganization,
  fetchOrganization,
  OrganizationDetail,
  OrganizationFields,
} from "../../services/api";
import { getRole } from "../../services/auth";
import { notifyChanged, organizationKey } from "../../services/refreshBus";
import { ORGANIZATION_FIELDS } from "../../services/recordFields";
import { BusinessStagePicker } from "../../components/business-stage-picker";
import { OfferPicker } from "../../components/OfferPicker";
import { useCreationOffer } from "../../hooks/useCreationOffer";
import { PipelineStage } from "../../services/organizationState";
import { RecordForm, Values } from "../../components/RecordForm";
import { useTranslation } from "../../i18n/I18nContext";

const VALUE_KEYS = ORGANIZATION_FIELDS.map((field) => field.key);

// The suppression flags, as on the web edit form. Do not contact asks before it is lifted.
const FLAGS = ["do_not_contact", "email_bounced", "research_exhausted"] as const;
type Flag = (typeof FLAGS)[number];
type Flags = Record<Flag, boolean>;

function flagsOf(organization: OrganizationDetail): Flags {
  return {
    do_not_contact: !!organization.do_not_contact,
    email_bounced: !!organization.email_bounced,
    research_exhausted: !!organization.research_exhausted,
  };
}

/** The typed fit score: null for blank, undefined when it is not a whole number 0–100. */
export function typedScore(text: string): number | null | undefined {
  const typed = text.trim();
  if (!typed) return null;
  if (!/^\d{1,3}$/.test(typed)) return undefined;
  const score = Number(typed);
  return score <= 100 ? score : undefined;
}

function valuesOf(organization: OrganizationDetail): Values {
  const record = organization as unknown as Record<string, unknown>;
  const values: Values = {};
  for (const key of VALUE_KEYS) {
    const value = record[key];
    values[key] = typeof value === "string" ? value : "";
  }
  return values;
}

/** Add an organization by hand (no id), or change one (id). Admin only. */
export default function EditOrganizationScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string; name?: string }>();
  const id = params.id ? Number(params.id) : null;
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [organization, setOrganization] = useState<OrganizationDetail | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [stage, setStage] = useState<PipelineStage>("candidate");
  const creationOffer = useCreationOffer();
  const [error, setError] = useState<string | null>(null);
  const [flags, setFlags] = useState<Flags | null>(null);
  const [score, setScore] = useState("");

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useEffect(() => {
    if (id === null) return;
    let cancelled = false;
    fetchOrganization(id)
      .then((loaded) => {
        if (cancelled) return;
        setOrganization(loaded);
        setFlags(flagsOf(loaded));
        setScore(loaded.fit_score === null || loaded.fit_score === undefined ? "" : String(loaded.fit_score));
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  function goToDetail(organizationId: number) {
    router.replace({ pathname: "/(drawer)/organization-detail", params: { id: String(organizationId) } });
  }

  function reportDuplicate(error: unknown): boolean {
    const duplicate = duplicateOf(error);
    if (!duplicate) return false;
    const where = [duplicate.name, duplicate.city].filter(Boolean).join(", ");
    if (duplicate.existingId === null) {
      Alert.alert(
        t("recordForm.duplicateTitle"),
        duplicate.name ? t("recordForm.duplicateDeleted", { where }) : t("recordForm.blockedChain"),
      );
      return true;
    }
    const existingId = duplicate.existingId;
    Alert.alert(t("recordForm.duplicateTitle"), t("recordForm.duplicateOrganization", { where }), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("recordForm.openExisting"), onPress: () => goToDetail(existingId) },
    ]);
    return true;
  }

  async function save(changed: Values) {
    setSaving(true);
    setError(null);
    const body: OrganizationFields = { ...changed };
    if (id !== null && organization && flags) {
      const before = flagsOf(organization);
      for (const flag of FLAGS) if (flags[flag] !== before[flag]) body[flag] = flags[flag];
      const typed = typedScore(score);
      if (typed === undefined) {
        setError(t("recordForm.scoreInvalid"));
        setSaving(false);
        return;
      }
      if (typed !== (organization.fit_score ?? null)) body.fit_score = typed;
    }
    try {
      if (id === null) {
        const created = await createOrganization({ ...body, pipeline_stage: stage, offer: creationOffer.sent });
        void creationOffer.remember();
        goToDetail(created.id);
      } else {
        await editOrganization(id, body);
        notifyChanged(organizationKey(id));
        if (router.canGoBack()) router.back();
        else goToDetail(id);
      }
    } catch (err: any) {
      if (!reportDuplicate(err)) setError(err?.response?.data?.detail || t("recordForm.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  function toggleFlag(flag: Flag, next: boolean) {
    const set = () => setFlags((current) => (current ? { ...current, [flag]: next } : current));
    if (flag !== "do_not_contact" || next) {
      set();
      return;
    }
    Alert.alert(t("recordForm.allowContactTitle"), t("recordForm.allowContactBody"), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("recordForm.allowContact"), style: "destructive", onPress: set },
    ]);
  }

  const before = organization ? flagsOf(organization) : null;
  const flagsChanged = !!flags && !!before && FLAGS.some((flag) => flags[flag] !== before[flag]);
  const scoreChanged =
    !!organization && score.trim() !== (organization.fit_score == null ? "" : String(organization.fit_score));

  if (isAdmin === null || (id !== null && !organization && !loadFailed)) {
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
  if (id !== null && !organization) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{t("organizationDetail.couldntLoad")}</Text>
      </View>
    );
  }

  return (
    <RecordForm
      fields={ORGANIZATION_FIELDS}
      baseline={organization ? valuesOf(organization) : {}}
      start={id === null && params.name ? { name: params.name } : undefined}
      saving={saving}
      error={error}
      submitLabel={id === null ? t("businessForm.add") : t("recordForm.save")}
      extraChange={id !== null && (flagsChanged || scoreChanged)}
      onSubmit={save}
    >
      {id === null && (
        <OfferPicker offers={creationOffer.offers} value={creationOffer.offer} onChange={creationOffer.choose}
          label={t("offerFilter.label")} disabled={saving} />
      )}
      {id === null && <BusinessStagePicker stage={stage} disabled={saving} onChange={setStage} />}
      {id !== null && (
        <View style={styles.field}>
          <Text style={styles.fieldLabel}>{t("organizationDetail.fitScore")}</Text>
          <TextInput
            style={styles.input}
            value={score}
            onChangeText={setScore}
            keyboardType="number-pad"
            maxLength={3}
            editable={!saving}
            placeholder="0–100"
            placeholderTextColor="#555"
            accessibilityLabel={t("organizationDetail.fitScore")}
          />
        </View>
      )}
      {id !== null && flags && (
        <>
          <Text style={styles.fieldLabel}>{t("organizations.suppression")}</Text>
          {FLAGS.map((flag) => (
            <View key={flag} style={styles.switchRow}>
              <View style={styles.switchText}>
                <Text style={styles.switchLabel}>{t(`flag.${flag}`)}</Text>
                {flag === "do_not_contact" && (
                  <Text style={styles.switchHint}>{t("recordForm.doNotContactHint")}</Text>
                )}
              </View>
              <Switch
                value={flags[flag]}
                onValueChange={(next) => toggleFlag(flag, next)}
                disabled={saving}
                accessibilityLabel={t(`flag.${flag}`)}
              />
            </View>
          ))}
        </>
      )}
    </RecordForm>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: "center", flex: 1, justifyContent: "center", padding: 24 },
  muted: { color: "#888", fontSize: 15, textAlign: "center" },
  switchRow: { alignItems: "center", flexDirection: "row", gap: 12, marginBottom: 6, marginTop: 6 },
  field: { marginBottom: 14 },
  fieldLabel: { color: "#888", fontSize: 12, marginBottom: 4, marginLeft: 2 },
  input: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff20",
    borderRadius: 10,
    borderWidth: 1,
    color: "#fff",
    fontSize: 16,
    minHeight: 48,
    paddingHorizontal: 14,
  },
  switchText: { flex: 1 },
  switchLabel: { color: "#fff", fontSize: 15, fontWeight: "600" },
  switchHint: { color: "#888", fontSize: 12, marginTop: 2 },
});

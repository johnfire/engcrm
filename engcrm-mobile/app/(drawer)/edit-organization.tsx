import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Switch, Text, View } from "react-native";
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
import { RecordForm, Values } from "../../components/RecordForm";
import { useTranslation } from "../../i18n/I18nContext";

const VALUE_KEYS = ORGANIZATION_FIELDS.map((field) => field.key);

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
  const [error, setError] = useState<string | null>(null);
  const [doNotContact, setDoNotContact] = useState<boolean | null>(null);

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
        setDoNotContact(!!loaded.do_not_contact);
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
    if (id !== null && doNotContact !== null && doNotContact !== !!organization?.do_not_contact) {
      body.do_not_contact = doNotContact;
    }
    try {
      if (id === null) {
        const created = await createOrganization(body);
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

  function toggleDoNotContact(next: boolean) {
    if (next) {
      setDoNotContact(true);
      return;
    }
    Alert.alert(t("recordForm.allowContactTitle"), t("recordForm.allowContactBody"), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("recordForm.allowContact"), style: "destructive", onPress: () => setDoNotContact(false) },
    ]);
  }

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
      submitLabel={id === null ? t("recordForm.addOrganization") : t("recordForm.save")}
      extraChange={id !== null && doNotContact !== !!organization?.do_not_contact}
      onSubmit={save}
    >
      {id !== null && (
        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text style={styles.switchLabel}>{t("recordForm.doNotContact")}</Text>
            <Text style={styles.switchHint}>{t("recordForm.doNotContactHint")}</Text>
          </View>
          <Switch
            value={!!doNotContact}
            onValueChange={toggleDoNotContact}
            disabled={saving}
            accessibilityLabel={t("recordForm.doNotContact")}
          />
        </View>
      )}
    </RecordForm>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: "center", flex: 1, justifyContent: "center", padding: 24 },
  muted: { color: "#888", fontSize: 15, textAlign: "center" },
  switchRow: { alignItems: "center", flexDirection: "row", gap: 12, marginTop: 6 },
  switchText: { flex: 1 },
  switchLabel: { color: "#fff", fontSize: 15, fontWeight: "600" },
  switchHint: { color: "#888", fontSize: 12, marginTop: 2 },
});

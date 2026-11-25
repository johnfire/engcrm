import { useCallback, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { useTranslation } from "../i18n/I18nContext";
import { readLocalWorkspace } from "../services/local-records";
import { useOffline } from "../services/offline-context";
import { stageLabelKey, statusLabelKey } from "../services/organizationState";
import { useAdminRole } from "../services/use-admin-role";

type Snapshot = Awaited<ReturnType<typeof readLocalWorkspace>>;
type Kind = "person" | "organization";

export function LocalRecordDetail({ kind, syncId }: { kind: Kind; syncId: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const admin = useAdminRole();
  const { session, status } = useOffline();
  const [loaded, setLoaded] = useState<{ database: object; snapshot: Snapshot } | null>(null);
  const [error, setError] = useState(false);
  const snapshot = session && loaded?.database === session.database ? loaded.snapshot : null;
  useFocusEffect(useCallback(() => {
    let active = true;
    if (session && status?.ready) {
      readLocalWorkspace(session.database).then((value) => { if (active) { setLoaded({ database: session.database, snapshot: value }); setError(false); } })
        .catch(() => { if (active) setError(true); });
    }
    return () => { active = false; };
  }, [session, status]));
  if (!snapshot) return error ? <Text style={styles.text}>{t("common.couldntLoadRefresh")}</Text>
    : <ActivityIndicator style={styles.loading} color="#7c6fff" />;
  const item = snapshot[kind].find((record) => record.syncId === syncId);
  if (!item) return <Text style={styles.text}>{t("offlineDetail.notFound")}</Text>;
  const parentField = kind === "person" ? "person_sync_id" : "organization_sync_id";
  const history = (kind === "person" ? snapshot.person_note : snapshot.organization_activity)
    .filter((entry) => entry.fields[parentField] === syncId)
    .sort((a, b) => String(b.fields.occurred_at ?? b.fields.interaction_date ?? "")
      .localeCompare(String(a.fields.occurred_at ?? a.fields.interaction_date ?? "")));
  const deals = snapshot.deal.filter((entry) => entry.fields[parentField] === syncId);
  return <ScrollView style={styles.container} contentContainerStyle={styles.content}>
    <Text style={styles.name}>{String(item.fields.name ?? "")}</Text>
    {admin && <TouchableOpacity accessibilityRole="button" onPress={() => router.push({
      pathname: kind === "person" ? "/(drawer)/edit-person" : "/(drawer)/edit-organization", params: { sync_id: syncId },
    })}><Text style={styles.pending}>{t("recordForm.edit")}</Text></TouchableOpacity>}
    {(item.pendingCount > 0 || item.failedCount > 0) && <Text style={styles.pending}>
      {t(item.failedCount > 0 ? "offlineDetail.failed" : "offlineDetail.pending")}</Text>}
    {["title", "city", "country", "email", "phone", "website", "notes"].map((field) =>
      typeof item.fields[field] === "string" && item.fields[field] ? <View key={field} style={styles.section}>
        <Text style={styles.label}>{t(`offlineDetail.${field}`)}</Text><Text style={styles.text}>{String(item.fields[field])}</Text>
      </View> : null)}
    <Text style={styles.heading}>{t("offlineDetail.deals")}</Text>
    {deals.map((deal) => <View key={deal.syncId} style={styles.section}>
      <Text style={styles.text}>{String(deal.fields.offer_name ?? deal.fields.offer_slug ?? "")}</Text>
      {typeof deal.fields.pipeline_stage === "string" && <Text style={styles.label}>{t(stageLabelKey(deal.fields.pipeline_stage))}</Text>}
      {typeof deal.fields.status === "string" && <Text style={styles.label}>{t(statusLabelKey(deal.fields.status))}</Text>}
    </View>)}
    <Text style={styles.heading}>{t("offlineDetail.history")}</Text>
    {history.length ? history.map((entry) => <View key={entry.syncId} style={styles.section}>
      <Text style={styles.label}>{String(entry.fields.occurred_at ?? entry.fields.interaction_date ?? "")}</Text>
      <Text style={styles.text}>{String(entry.fields.note ?? entry.fields.summary ?? "")}</Text>
    </View>) : <Text style={styles.label}>{t("activity.empty")}</Text>}
  </ScrollView>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" }, content: { padding: 16 }, loading: { flex: 1 },
  name: { color: "#fff", fontSize: 22, fontWeight: "600" }, heading: { color: "#fff", fontSize: 18, marginTop: 22 },
  text: { color: "#fff", fontSize: 15 }, label: { color: "#bbb", fontSize: 13 }, pending: { color: "#f6c770", marginTop: 8 },
  section: { paddingVertical: 8 },
});

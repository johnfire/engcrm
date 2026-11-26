import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";

import { useTranslation } from "../i18n/I18nContext";
import { useLocalSnapshot } from "../hooks/useLocalSnapshot";
import { useAdminRole } from "../services/use-admin-role";
import { LocalDealCard } from "./local-deal-card";
import { LocalRatings } from "./local-ratings";
import { LocalActivityEntry } from "./local-activity-entry";

type Kind = "person" | "organization";

export function LocalRecordDetail({ kind, syncId }: { kind: Kind; syncId: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const admin = useAdminRole();
  const { snapshot, error } = useLocalSnapshot();
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
  const linkedPeople = kind === "organization" ? snapshot.person.filter((entry) => entry.fields.organization_sync_id === syncId) : [];
  return <ScrollView style={styles.container} contentContainerStyle={styles.content}>
    <Text style={styles.name}>{String(item.fields.name ?? "")}</Text>
    {admin && <TouchableOpacity accessibilityRole="button" onPress={() => router.push({
      pathname: kind === "person" ? "/(drawer)/edit-person" : "/(drawer)/edit-organization", params: { sync_id: syncId },
    })}><Text style={styles.pending}>{t("recordForm.edit")}</Text></TouchableOpacity>}
    {(item.pendingCount > 0 || item.failedCount > 0) && <Text style={styles.pending}>
      {t(item.failedCount > 0 ? "offlineDetail.failed" : "offlineDetail.pending")}</Text>}
    {item.serverId !== null && <TouchableOpacity accessibilityRole="button" onPress={() => router.push({
      pathname: kind === "person" ? "/(drawer)/person-detail" : "/(drawer)/organization-detail",
      params: { id: String(item.serverId) },
    })}><Text style={styles.pending}>{t("offlineDetail.moreOnline")}</Text></TouchableOpacity>}
    {item.serverId !== null && item.pendingCount > 0 && <Text style={styles.label}>{t("offlineDetail.onlineStale")}</Text>}
    {admin && <TouchableOpacity accessibilityRole="button" onPress={() => router.push({ pathname: "/(drawer)/log-meeting",
      params: { kind, sync_id: syncId, name: String(item.fields.name ?? "") } })}>
      <Text style={styles.pending}>{t("meeting.logButton")}</Text></TouchableOpacity>}
    {["title", "city", "country", "email", "phone", "website", "notes"].map((field) =>
      typeof item.fields[field] === "string" && item.fields[field] ? <View key={field} style={styles.section}>
        <Text style={styles.label}>{t(`offlineDetail.${field}`)}</Text><Text style={styles.text}>{String(item.fields[field])}</Text>
      </View> : null)}
    {admin && <LocalRatings item={item} kind={kind} />}
    <Text style={styles.heading}>{t("offlineDetail.deals")}</Text>
    {deals.map((deal) => <View key={deal.syncId} style={styles.section}><LocalDealCard deal={deal} canEdit={!!admin} /></View>)}
    {kind === "organization" && <>
      <Text style={styles.heading}>{t("offlineDetail.people")}</Text>
      {linkedPeople.map((person) => <TouchableOpacity key={person.syncId} accessibilityRole="button"
        onPress={() => router.push({ pathname: "/(drawer)/person-detail", params: { sync_id: person.syncId } })} style={styles.section}>
        <Text style={styles.text}>{String(person.fields.name ?? "")}</Text></TouchableOpacity>)}
      {admin && <TouchableOpacity accessibilityRole="button" onPress={() => router.push({ pathname: "/(drawer)/edit-person",
        params: { offline_create: "1", organization_sync_id: syncId } })}><Text style={styles.pending}>{t("recordForm.addPerson")}</Text></TouchableOpacity>}
    </>}
    <Text style={styles.heading}>{t("offlineDetail.history")}</Text>
    {history.length ? history.map((entry) => <LocalActivityEntry key={entry.syncId} record={entry} owner={kind} />)
      : <Text style={styles.label}>{t("activity.empty")}</Text>}
  </ScrollView>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" }, content: { padding: 16 }, loading: { flex: 1 },
  name: { color: "#fff", fontSize: 22, fontWeight: "600" }, heading: { color: "#fff", fontSize: 18, marginTop: 22 },
  text: { color: "#fff", fontSize: 15 }, label: { color: "#bbb", fontSize: 13 }, pending: { color: "#f6c770", marginTop: 8 },
  section: { paddingVertical: 8 },
});

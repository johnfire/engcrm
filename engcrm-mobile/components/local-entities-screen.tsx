import { useMemo, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";

import { useLocalSnapshot } from "../hooks/useLocalSnapshot";
import { useStoredSort } from "../hooks/useStoredSort";
import { useTranslation } from "../i18n/I18nContext";
import { filterLocalEntities } from "../services/local-entity-filters";
import { projectLocalEntities, type LocalEntity } from "../services/local-entity-projection";
import { ORGANIZATION_SORTS, PERSON_SORTS } from "../services/listSortOptions";
import { useOffline } from "../services/offline-context";
import { useAdminRole } from "../services/use-admin-role";
import { stageLabelKey } from "../services/organizationState";
import { FilterPanel, ListSearchRow } from "./ListFilters";
import { LocalOfferChips } from "./LocalOfferChips";
import { OrganizationListControls } from "./OrganizationListControls";
import { PeopleListControls } from "./PeopleListControls";
import { ListAddButton } from "./add-business-button";

export function LocalEntitiesScreen({ kind }: { kind: "person" | "organization" }) {
  const { t } = useTranslation();
  const router = useRouter();
  const admin = useAdminRole();
  const { session, state, requestSync, retryOpen } = useOffline();
  const { snapshot, error } = useLocalSnapshot();
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [rating, setRating] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [suppressed, setSuppressed] = useState("");
  const [offer, setOffer] = useState("all");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const peopleSort = useStoredSort("people", PERSON_SORTS);
  const organizationSort = useStoredSort("organizations", ORGANIZATION_SORTS);
  const sorting = kind === "person" ? peopleSort : organizationSort;
  const items = useMemo(() => snapshot ? filterLocalEntities(projectLocalEntities(snapshot, kind, offer), {
    kind, offer, search, stage, status, rating, linkedin, suppressed, sort: sorting.sort.key, direction: sorting.sort.direction,
  }) : [], [snapshot, kind, offer, search, stage, status, rating, linkedin, suppressed, sorting.sort]);
  const activeFilters = [stage, status, rating, linkedin, suppressed, offer !== "all"].filter(Boolean).length;
  const reset = () => { setStage(""); setStatus(""); setRating(""); setLinkedin(""); setSuppressed(""); setOffer("all"); };
  const open = (item: LocalEntity) => router.push({ pathname: kind === "person" ? "/(drawer)/person-detail" : "/(drawer)/organization-detail",
    params: { sync_id: item.syncId } });
  return <View style={styles.container}>
    <ListSearchRow placeholder={t(kind === "person" ? "people.searchPlaceholder" : "organizations.searchPlaceholder")}
      search={search} onSearchChange={setSearch} onSubmit={() => {}} filtersOpen={filtersOpen}
      activeFilters={activeFilters} onToggleFilters={() => setFiltersOpen(!filtersOpen)} action={admin && <ListAddButton
        label={t(kind === "person" ? "recordForm.addPerson" : "businessForm.add")}
        onPress={() => router.push({ pathname: kind === "person" ? "/(drawer)/edit-person" : "/(drawer)/edit-organization",
          params: { offline_create: "1" } })} />} />
    <FilterPanel open={filtersOpen} activeFilters={activeFilters} onClear={reset}>
      <LocalOfferChips offer={offer} onChange={setOffer} />
      {kind === "person" ? <PeopleListControls stage={stage} rating={rating} linkedin={linkedin} sort={peopleSort.sort}
        onStageChange={setStage} onRatingChange={setRating} onLinkedinChange={setLinkedin} onSortChange={peopleSort.choose} />
        : <OrganizationListControls stage={stage} status={status} personalPriority={rating} linkedin={linkedin} suppressed={suppressed}
          sort={organizationSort.sort} onStageChange={setStage} onStatusChange={setStatus} onPriorityChange={setRating}
          onLinkedinChange={setLinkedin} onSuppressedChange={setSuppressed} onSortChange={organizationSort.choose} />}
    </FilterPanel>
    {!snapshot && state === "needs_auth" ? <Text style={styles.detail}>{t("offlineStatus.needsAuth")}</Text>
      : !snapshot && state === "error" ? <TouchableOpacity accessibilityRole="button" onPress={session ? requestSync : retryOpen}>
        <Text style={styles.detail}>{t("offlineStatus.error")} · {t("offlineStatus.retry")}</Text></TouchableOpacity>
        : error && !snapshot ? <Text style={styles.detail}>{t("common.couldntLoadRefresh")}</Text>
          : !snapshot || !sorting.ready ? <ActivityIndicator style={styles.loading} color="#7c6fff" />
            : <FlatList data={items} keyExtractor={(item) => item.syncId} contentContainerStyle={styles.list}
              onRefresh={requestSync} refreshing={false} renderItem={({ item }) => <TouchableOpacity style={styles.row}
                onPress={() => open(item)} accessibilityRole="button">
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.detail}>{[item.fields.title, item.fields.company, item.fields.city, item.fields.email].filter(Boolean).join(" · ")}</Text>
                {item.deals.map((deal) => typeof deal.fields.pipeline_stage === "string" && <Text key={deal.syncId} style={styles.detail}>
                  {t(stageLabelKey(deal.fields.pipeline_stage))}</Text>)}
                {(item.pendingCount > 0 || item.failedCount > 0) && <Text style={styles.pending}>
                  {t(item.failedCount > 0 ? "offlineDetail.failed" : "offlineDetail.pending")}</Text>}
              </TouchableOpacity>} ListEmptyComponent={<Text style={styles.detail}>{t(kind === "person" ? "people.empty" : "organizations.notFound")}</Text>} />}
  </View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" }, list: { padding: 16 }, loading: { flex: 1 },
  row: { backgroundColor: "#1a1a2e", borderRadius: 12, padding: 16, marginBottom: 10 },
  name: { color: "#fff", fontSize: 16, fontWeight: "600" }, detail: { color: "#bbb", marginTop: 6 },
  pending: { color: "#f6c770", marginTop: 6 },
});

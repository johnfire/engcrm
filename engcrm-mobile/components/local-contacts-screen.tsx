import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { useStoredSort } from "../hooks/useStoredSort";
import { useTranslation } from "../i18n/I18nContext";
import type { ContactKind } from "../services/contact-feed";
import { filterLocalContacts, projectLocalContacts, type LocalContact } from "../services/local-contact-projection";
import { readLocalWorkspace } from "../services/local-records";
import { useOffline } from "../services/offline-context";
import { CONTACT_SORTS } from "../services/listSortOptions";
import { stageLabelKey } from "../services/organizationState";
import { ContactFeedControls } from "./contact-feed-controls";
import { ChipRow, FilterChip } from "./FilterChips";
import { FilterPanel, ListSearchRow } from "./ListFilters";

type Snapshot = Awaited<ReturnType<typeof readLocalWorkspace>>;

function ContactRow({ contact, open }: { contact: LocalContact; open: (contact: LocalContact) => void }) {
  const { t } = useTranslation();
  return <View style={styles.row}>
    <TouchableOpacity onPress={() => open(contact)} accessibilityRole="button">
      <Text style={styles.name}>{contact.name}</Text>
      <Text style={styles.detail}>{[contact.fields.city, contact.fields.email, contact.fields.phone].filter(Boolean).join(" · ")}</Text>
      {(contact.pendingCount > 0 || contact.failedCount > 0) && <Text style={styles.pending}>
        {t(contact.failedCount > 0 ? "offlineDetail.failed" : "offlineDetail.pending")}</Text>}
      {contact.deals.map((deal) => typeof deal.fields.pipeline_stage === "string" &&
        <Text key={deal.syncId} style={styles.detail}>{t(stageLabelKey(deal.fields.pipeline_stage))}</Text>)}
      {contact.lastContact && <Text style={styles.detail}>{t("contactFeed.last_contact")}: {contact.lastContact}</Text>}
    </TouchableOpacity>
    {contact.people.map((person) => <TouchableOpacity key={person.syncId} onPress={() => open(person)} accessibilityRole="button"
      style={styles.person}><Text style={styles.name}>{person.name}</Text>
      {typeof person.fields.title === "string" && <Text style={styles.detail}>{person.fields.title}</Text>}
      {(person.pendingCount > 0 || person.failedCount > 0) && <Text style={styles.pending}>
        {t(person.failedCount > 0 ? "offlineDetail.failed" : "offlineDetail.pending")}</Text>}
    </TouchableOpacity>)}
  </View>;
}

export function LocalContactsScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { session, status, state, requestSync, retryOpen } = useOffline();
  const [loaded, setLoaded] = useState<{ database: object; snapshot: Snapshot } | null>(null);
  const snapshot = session && loaded?.database === session.database ? loaded.snapshot : null;
  const [error, setError] = useState(false);
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<ContactKind | "">("");
  const [stage, setStage] = useState("");
  const [offer, setOffer] = useState("all");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const { sort, ready, choose } = useStoredSort("contacts", CONTACT_SORTS);

  useFocusEffect(useCallback(() => {
    let active = true;
    if (session && status?.ready) {
      readLocalWorkspace(session.database).then((value) => { if (active) { setLoaded({ database: session.database, snapshot: value }); setError(false); } })
        .catch(() => { if (active) setError(true); });
    }
    return () => { active = false; };
  }, [session, status]));

  const offers = useMemo(() => {
    const found = new Map<string, string>();
    for (const deal of snapshot?.deal ?? []) {
      const slug = deal.fields.offer_slug, name = deal.fields.offer_name;
      if (typeof slug === "string") found.set(slug, typeof name === "string" ? name : slug);
    }
    return [...found.entries()];
  }, [snapshot]);
  const contacts = useMemo(() => snapshot ? filterLocalContacts(projectLocalContacts(snapshot, offer),
    { search, kind, stage, sort: sort.key, direction: sort.direction }) : [], [snapshot, offer, search, kind, stage, sort]);
  const activeFilters = [kind, stage, offer !== "all"].filter(Boolean).length;
  const open = (contact: LocalContact) => router.push({ pathname: contact.kind === "person" ? "/(drawer)/person-detail" : "/(drawer)/organization-detail",
    params: { sync_id: contact.syncId } });
  return <View style={styles.container}>
    <ListSearchRow placeholder={t("contactFeed.search")} search={search} onSearchChange={setSearch} onSubmit={() => {}}
      filtersOpen={filtersOpen} activeFilters={activeFilters} onToggleFilters={() => setFiltersOpen(!filtersOpen)} />
    <FilterPanel open={filtersOpen} activeFilters={activeFilters} onClear={() => { setKind(""); setStage(""); setOffer("all"); }}>
      <ChipRow label={t("offerFilter.label")}><FilterChip label={t("offerFilter.all")} isActive={offer === "all"} onPress={() => setOffer("all")} />
        {offers.map(([slug, name]) => <FilterChip key={slug} label={name} isActive={offer === slug} onPress={() => setOffer(slug)} />)}</ChipRow>
      <ContactFeedControls kind={kind} stage={stage} sort={sort} onKindChange={setKind} onStageChange={setStage} onSortChange={choose} />
    </FilterPanel>
    {!snapshot && state === "needs_auth" ? <Text style={styles.detail}>{t("offlineStatus.needsAuth")}</Text>
      : !snapshot && state === "error" ? <TouchableOpacity accessibilityRole="button" onPress={session ? requestSync : retryOpen}>
      <Text style={styles.detail}>{t("offlineStatus.error")} · {t("offlineStatus.retry")}</Text>
    </TouchableOpacity> : error && !snapshot ? <Text style={styles.detail}>{t("common.couldntLoadRefresh")}</Text>
      : !snapshot || !ready ? <ActivityIndicator style={styles.loading} color="#7c6fff" /> : <FlatList data={contacts}
      keyExtractor={(item) => `${item.kind}:${item.syncId}`} renderItem={({ item }) => <ContactRow contact={item} open={open} />}
      contentContainerStyle={styles.list} onRefresh={requestSync} refreshing={false}
      ListEmptyComponent={<Text style={styles.detail}>{error ? t("common.couldntLoadRefresh") : t("contactFeed.empty")}</Text>} />}
  </View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  list: { padding: 16 }, loading: { flex: 1 },
  row: { backgroundColor: "#1a1a2e", borderRadius: 12, padding: 16, marginBottom: 10 },
  name: { color: "#fff", fontSize: 16, fontWeight: "600" }, detail: { color: "#bbb", marginTop: 6 },
  person: { marginLeft: 16, paddingTop: 12 }, pending: { color: "#f6c770", marginTop: 6 },
});

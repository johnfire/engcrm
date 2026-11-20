import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { AddBusinessButton } from "../../components/add-business-button";
import { ContactCountsStrip } from "../../components/contact-counts";
import { ContactFeedRow } from "../../components/contact-feed-row";
import { ContactFeedControls } from "../../components/contact-feed-controls";
import { FilterPanel, ListSearchRow } from "../../components/ListFilters";
import { useTranslation } from "../../i18n/I18nContext";
import { OfferFilterChips } from "../../components/OfferFilterChips";
import { useOfferFilter } from "../../hooks/useOfferFilter";
import { ALL_OFFERS } from "../../services/deals";
import { CONTACT_FEED_PAGE_SIZE, ContactKind, contactKey, fetchContactFeed } from "../../services/contact-feed";
import { useStoredSort } from "../../hooks/useStoredSort";
import { CONTACT_SORTS } from "../../services/listSortOptions";
import { useAdminRole } from "../../services/use-admin-role";
import { usePagedList } from "../../services/usePagedList";

export default function ContactsScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const isAdmin = useAdminRole();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<ContactKind | "">("");
  const [stage, setStage] = useState("");
  const { sort, ready: sortReady, choose: chooseSort } = useStoredSort("contacts", CONTACT_SORTS);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const { offer, offers, choose: chooseOffer } = useOfferFilter();
  const activeFilters = [offer !== ALL_OFFERS, kind !== "", stage !== ""].filter(Boolean).length;
  const clearFilters = () => { chooseOffer(ALL_OFFERS); setKind(""); setStage(""); };
  // Nothing is requested until the remembered sort is known: no wasted fetch, no flash of the wrong order.
  const fetchPage = useCallback((page: number) => !sortReady ? Promise.resolve([]) :
    fetchContactFeed({ search, kind, stage, sort: sort.key, dir: sort.direction, page, offer }),
    [search, kind, stage, sort, sortReady, offer]);
  const { items, loading, loadingMore, error, reload, loadMore } = usePagedList(fetchPage, CONTACT_FEED_PAGE_SIZE, contactKey);
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));

  return (
    <View style={styles.container}>
      <ListSearchRow placeholder={t("contactFeed.search")} search={search} onSearchChange={setSearch} onSubmit={reload}
        filtersOpen={filtersOpen} activeFilters={activeFilters} onToggleFilters={() => setFiltersOpen(!filtersOpen)}
        action={<AddBusinessButton isAdmin={!!isAdmin} />} />
      <FilterPanel open={filtersOpen} activeFilters={activeFilters} onClear={clearFilters}>
        <ContactCountsStrip offer={offer} />
        <OfferFilterChips offer={offer} offers={offers} onChange={chooseOffer} />
        <ContactFeedControls kind={kind} stage={stage} sort={sort}
          onKindChange={setKind} onStageChange={setStage} onSortChange={chooseSort} />
      </FilterPanel>
      {error && <Text style={styles.message}>{t("common.couldntLoadRefresh")}</Text>}
      {loading || !sortReady ? <ActivityIndicator style={styles.loading} color="#7c6fff" /> : <FlatList
        data={items} keyExtractor={contactKey} contentContainerStyle={styles.list}
        renderItem={({ item: contact }) => <ContactFeedRow contact={contact} canEdit={!!isAdmin} showOffer={offer === ALL_OFFERS} onPress={() => router.push({
          pathname: contact.kind === "person" ? "/(drawer)/person-detail" : "/(drawer)/organization-detail",
          params: { id: String(contact.id) },
        })} />}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} tintColor="#7c6fff" />}
        onEndReached={loadMore} onEndReachedThreshold={0.5} keyboardShouldPersistTaps="handled"
        ListFooterComponent={loadingMore ? <ActivityIndicator color="#7c6fff" /> : null}
        ListEmptyComponent={!error ? <Text style={styles.message}>{t("contactFeed.empty")}</Text> : null}
      />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  list: { padding: 16 },
  loading: { flex: 1 },
  message: { color: "#bbb", textAlign: "center", padding: 20, fontSize: 15 },
});

import { useCallback, useEffect, useState } from "react";
import { View, FlatList, Text, StyleSheet, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import {
  fetchOrganizations,
  Organization,
  OrganizationSortKey,
  ORGANIZATIONS_PAGE_SIZE,
} from "../../services/api";
import { getRole } from "../../services/auth";
import { usePagedList } from "../../services/usePagedList";
import { OrganizationListControls } from "../../components/OrganizationListControls";
import { OrganizationRow } from "../../components/OrganizationRow";
import { FilterPanel, ListSearchRow } from "../../components/ListFilters";
import { ListAddButton } from "../../components/add-business-button";
import { useTranslation } from "../../i18n/I18nContext";
import { OfferFilterChips } from "../../components/OfferFilterChips";
import { useOfferFilter } from "../../hooks/useOfferFilter";
import { ALL_OFFERS } from "../../services/deals";

export default function OrganizationsScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [isAdmin, setIsAdmin] = useState(false);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [personalPriority, setPersonalPriority] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [suppressed, setSuppressed] = useState("");
  const [sort, setSort] = useState<OrganizationSortKey>("created_at");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const [filtersOpen, setFiltersOpen] = useState(false);

  const { offer, offers, choose: chooseOffer } = useOfferFilter();
  const activeFilters = [offer !== ALL_OFFERS, stage, status, personalPriority, linkedin, suppressed]
    .filter(Boolean).length;
  const clearFilters = () => {
    chooseOffer(ALL_OFFERS);
    setStage("");
    setStatus("");
    setPersonalPriority("");
    setLinkedin("");
    setSuppressed("");
  };

  const fetchPage = useCallback(
    (page: number): Promise<Organization[]> =>
      fetchOrganizations({
        search,
        stage,
        status,
        sort,
        dir,
        personal_priority: personalPriority,
        linkedin,
        suppressed,
        offer,
        page,
      }),
    [search, stage, status, sort, dir, personalPriority, linkedin, suppressed, offer],
  );
  const { items, loading, loadingMore, error, reload, loadMore } = usePagedList(
    fetchPage,
    ORGANIZATIONS_PAGE_SIZE,
  );

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useFocusEffect(
    useCallback(() => {
      reload();
    }, [reload]),
  );

  return (
    <View style={styles.container}>
      <ListSearchRow
        placeholder={t("organizations.searchPlaceholder")}
        search={search}
        onSearchChange={setSearch}
        onSubmit={reload}
        filtersOpen={filtersOpen}
        activeFilters={activeFilters}
        onToggleFilters={() => setFiltersOpen(!filtersOpen)}
        action={isAdmin && (
          <ListAddButton
            label={t("businessForm.add")}
            onPress={() => router.push({ pathname: "/(drawer)/edit-organization", params: {} })}
          />
        )}
      />
      <FilterPanel open={filtersOpen} activeFilters={activeFilters} onClear={clearFilters}>
        <OfferFilterChips offer={offer} offers={offers} onChange={chooseOffer} />
        <OrganizationListControls
          stage={stage}
          status={status}
          personalPriority={personalPriority}
          linkedin={linkedin}
          suppressed={suppressed}
          sort={sort}
          direction={dir}
          onStageChange={setStage}
          onStatusChange={setStatus}
          onPriorityChange={setPersonalPriority}
          onLinkedinChange={setLinkedin}
          onSuppressedChange={setSuppressed}
          onSortChange={(nextSort, nextDirection) => {
            setSort(nextSort);
            setDir(nextDirection);
          }}
        />
      </FilterPanel>
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(organization) => String(organization.id)}
          renderItem={({ item }) => (
            <OrganizationRow
              item={item}
              showOffer={offer === ALL_OFFERS}
              onPress={(id) =>
                router.push({
                  pathname: "/(drawer)/organization-detail",
                  params: { id },
                })
              }
            />
          )}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} tintColor="#7c6fff" />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={loadingMore ? <ActivityIndicator color="#7c6fff" style={styles.more} /> : null}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.empty}>
              {error ? t("common.couldntLoadRefresh") : t("organizations.notFound")}
            </Text>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  list: { padding: 16 },
  more: { marginVertical: 16 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

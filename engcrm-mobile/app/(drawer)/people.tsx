import { useCallback, useEffect, useState } from "react";
import {
  View,
  FlatList,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { fetchPeople, PEOPLE_PAGE_SIZE, Person } from "../../services/api";
import { SortChips } from "../../components/SortChips";
import { useStoredSort } from "../../hooks/useStoredSort";
import { PERSON_SORTS } from "../../services/listSortOptions";
import { getRole } from "../../services/auth";
import { PIPELINE_STAGES, stageLabelKey } from "../../services/organizationState";
import { usePagedList } from "../../services/usePagedList";
import { ChipRow, FilterChip } from "../../components/FilterChips";
import { FilterPanel, ListSearchRow } from "../../components/ListFilters";
import { ListAddButton } from "../../components/add-business-button";
import { useTranslation } from "../../i18n/I18nContext";
import { DealChips } from "../../components/DealChips";
import { OfferFilterChips } from "../../components/OfferFilterChips";
import { useOfferFilter } from "../../hooks/useOfferFilter";
import { ALL_OFFERS } from "../../services/deals";
import { linkedinLabel, openWebsite } from "../../services/webLinks";

// "" = any stage, "none" = people with no stage set, then the shared vocabulary.
const STAGE_FILTERS = ["", "none", ...PIPELINE_STAGES];

// My rating runs 1 (exceptional) .. 5 (minimal), so "or better" is that number or lower.
const RATING_LABELS = ["contactValue.exceptional", "contactValue.high", "contactValue.medium",
  "contactValue.low", "contactValue.minimal"];
const RATING_FILTERS: { value: string; label: (t: (key: string, vars?: Record<string, unknown>) => string) => string }[] = [
  { value: "", label: (t) => t("people.anyRating") },
  { value: "1", label: (t) => `1 ${t(RATING_LABELS[0])}` },
  { value: "2+", label: (t) => `2 ${t("people.ratingOrBetter", { label: t(RATING_LABELS[1]) })}` },
  { value: "3+", label: (t) => `3 ${t("people.ratingOrBetter", { label: t(RATING_LABELS[2]) })}` },
  { value: "unrated", label: (t) => t("people.unrated") },
];

export default function PeopleScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [isAdmin, setIsAdmin] = useState(false);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [rating, setRating] = useState("");
  const { sort, ready: sortReady, choose: chooseSort } = useStoredSort("people", PERSON_SORTS);

  const [filtersOpen, setFiltersOpen] = useState(false);

  const { offer, offers, choose: chooseOffer } = useOfferFilter();
  const activeFilters = [offer !== ALL_OFFERS, stage, linkedin, rating].filter(Boolean).length;
  const clearFilters = () => {
    chooseOffer(ALL_OFFERS);
    setStage("");
    setLinkedin("");
    setRating("");
  };

  const fetchPage = useCallback(
    (page: number): Promise<Person[]> =>
      // Nothing is requested until the remembered sort is known: no wasted fetch, no flash of the wrong order.
      !sortReady ? Promise.resolve([]) : fetchPeople({ search, sort: sort.key, dir: sort.direction, stage, linkedin, value_rating: rating, offer, page }),
    [search, sort, sortReady, stage, linkedin, rating, offer],
  );
  const { items, loading, loadingMore, error, reload, loadMore } = usePagedList(fetchPage, PEOPLE_PAGE_SIZE);

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
        placeholder={t("people.searchPlaceholder")}
        search={search}
        onSearchChange={setSearch}
        onSubmit={reload}
        filtersOpen={filtersOpen}
        activeFilters={activeFilters}
        onToggleFilters={() => setFiltersOpen(!filtersOpen)}
        action={isAdmin && (
          <ListAddButton
            label={t("recordForm.addPerson")}
            onPress={() => router.push({ pathname: "/(drawer)/edit-person", params: {} })}
          />
        )}
      />
      <FilterPanel open={filtersOpen} activeFilters={activeFilters} onClear={clearFilters}>
        <OfferFilterChips offer={offer} offers={offers} onChange={chooseOffer} />
        <ChipRow label={t("common.pipelineStage")}>
          {STAGE_FILTERS.map((filter) => (
            <FilterChip
              key={filter}
              label={
                filter === ""
                  ? t("organizations.allStages")
                  : filter === "none"
                    ? t("people.noStage")
                    : t(stageLabelKey(filter))
              }
              isActive={stage === filter}
              onPress={() => setStage(filter)}
            />
          ))}
        </ChipRow>
        <ChipRow label={t("people.ratingFilter")}>
          {RATING_FILTERS.map(({ value, label }) => (
            <FilterChip key={value || "any"} label={label(t)} isActive={rating === value} onPress={() => setRating(value)} />
          ))}
        </ChipRow>
        <ChipRow label={t("people.linkedinFilter")}>
          <FilterChip label={t("people.everyone")} isActive={linkedin === ""} onPress={() => setLinkedin("")} />
          <FilterChip label={t("people.linkedinOnly")} isActive={linkedin === "1"} onPress={() => setLinkedin("1")} />
          <FilterChip
            label={t("people.linkedinUnlinked")}
            isActive={linkedin === "unlinked"}
            onPress={() => setLinkedin("unlinked")}
          />
        </ChipRow>
        <SortChips options={PERSON_SORTS} sort={sort} onChoose={chooseSort} />
      </FilterPanel>

      {loading || !sortReady ? (
        <View style={styles.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(person) => String(person.id)}
          renderItem={({ item }) => (
            <PersonRow
              person={item}
              showOffer={offer === ALL_OFFERS}
              onPress={(id) => router.push({ pathname: "/(drawer)/person-detail", params: { id: String(id) } })}
            />
          )}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} tintColor="#7c6fff" />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={loadingMore ? <ActivityIndicator color="#7c6fff" style={styles.more} /> : null}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.empty}>{error ? t("common.couldntLoadRefresh") : t("people.empty")}</Text>
          }
        />
      )}
    </View>
  );
}

// A row opens the person; when they have a LinkedIn profile, its own button opens
// that straight away (in the LinkedIn app when installed, where Message is), so a
// list of candidates can be worked through without opening each record.
function PersonRow({ person, onPress, showOffer }: { person: Person; onPress: (id: number) => void; showOffer: boolean }) {
  const { t } = useTranslation();
  const subtitle = [person.title, person.company].filter(Boolean).join(" · ");
  const meta = [`#${person.id}`, person.city, person.email].filter(Boolean).join("  ·  ");
  // Its deals when the server sent them; an older server sent the Consulting stage alone.
  const shownStage = person.deals ? null : (person.pipeline_stage ?? null);
  const profile = linkedinLabel(person.linkedin_url);
  return (
    <TouchableOpacity style={styles.row} onPress={() => onPress(person.id)}>
      <View style={styles.line}>
        <Text style={styles.name} numberOfLines={1}>
          {person.name}
        </Text>
        {!!person.is_linkedin_contact && !profile && (
          <Text style={styles.linkedin}>{t("search.linkedinPerson")}</Text>
        )}
        {!!shownStage && <Text style={styles.stage}>{t(stageLabelKey(shownStage))}</Text>}
        {person.value_rating != null && (
          <Text style={styles.rating}>
            {t("people.ratingBadge", { rating: person.value_rating, label: t(RATING_LABELS[person.value_rating - 1]) })}
          </Text>
        )}
      </View>
      <DealChips deals={person.deals} showOffer={showOffer} />
      {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      {!!meta && <Text style={styles.meta}>{meta}</Text>}
      {!!profile && (
        <TouchableOpacity
          style={styles.profileButton}
          onPress={() => openWebsite(person.linkedin_url)}
          accessibilityRole="link"
          accessibilityLabel={t("people.openLinkedin", { name: person.name })}
          hitSlop={{ top: 6, bottom: 6 }}
        >
          <Text style={styles.profileIn}>in</Text>
          <Text style={styles.profileText} numberOfLines={1}>
            {profile} ↗
          </Text>
        </TouchableOpacity>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  list: { padding: 16 },
  more: { marginVertical: 16 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  row: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: "#ffffff12",
  },
  line: { alignItems: "center", flexDirection: "row", gap: 8 },
  name: { color: "#fff", flexShrink: 1, fontSize: 16, fontWeight: "600" },
  linkedin: {
    backgroundColor: "#0a66c2",
    borderRadius: 4,
    color: "#fff",
    fontSize: 11,
    fontWeight: "700",
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  stage: { color: "#7c6fff", fontSize: 12, fontWeight: "600" },
  rating: { color: "#e0b84a", fontSize: 12, fontWeight: "700" },
  profileButton: {
    alignItems: "center",
    alignSelf: "flex-start",
    borderColor: "#0a66c2",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    marginTop: 10,
    maxWidth: "100%",
    minHeight: 40,
    paddingHorizontal: 10,
  },
  profileIn: {
    backgroundColor: "#0a66c2",
    borderRadius: 3,
    color: "#fff",
    fontSize: 11,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  profileText: { color: "#5aa9f0", flexShrink: 1, fontSize: 13 },
  subtitle: { color: "#b9adff", fontSize: 13, marginTop: 3 },
  meta: { color: "#888", fontSize: 12, marginTop: 6 },
  empty: {
    color: "#555",
    textAlign: "center",
    marginTop: 60,
    fontSize: 15,
    lineHeight: 22,
  },
});

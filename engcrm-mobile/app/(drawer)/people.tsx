import { useCallback, useEffect, useState } from "react";
import {
  View,
  FlatList,
  TextInput,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { fetchPeople, PEOPLE_PAGE_SIZE, Person, PersonSortKey } from "../../services/api";
import { getRole } from "../../services/auth";
import { PIPELINE_STAGES, stageLabelKey } from "../../services/organizationState";
import { usePagedList } from "../../services/usePagedList";
import { ChipRow, FilterChip } from "../../components/FilterChips";
import { useTranslation } from "../../i18n/I18nContext";

const SORT_OPTIONS: { key: PersonSortKey; dir: "asc" | "desc"; labelKey: string }[] = [
  { key: "created_at", dir: "desc", labelKey: "common.sortNewest" },
  { key: "name", dir: "asc", labelKey: "common.sortAZ" },
  { key: "connected_on", dir: "desc", labelKey: "people.sortConnected" },
  { key: "company", dir: "asc", labelKey: "people.sortCompany" },
  { key: "city", dir: "asc", labelKey: "people.sortCity" },
];

// "" = any stage, "none" = people with no stage set, then the shared vocabulary.
const STAGE_FILTERS = ["", "none", ...PIPELINE_STAGES];

export default function PeopleScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [isAdmin, setIsAdmin] = useState(false);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [sort, setSort] = useState<PersonSortKey>("created_at");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const fetchPage = useCallback(
    (page: number): Promise<Person[]> => fetchPeople({ search, sort, dir, stage, linkedin, page }),
    [search, sort, dir, stage, linkedin],
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
      <View style={styles.searchRow}>
        <TextInput
          style={styles.search}
          placeholder={t("people.searchPlaceholder")}
          placeholderTextColor="#555"
          value={search}
          onChangeText={setSearch}
          onSubmitEditing={reload}
          returnKeyType="search"
          autoCapitalize="none"
          accessibilityLabel={t("people.searchPlaceholder")}
        />
        {isAdmin && (
          <TouchableOpacity
            style={styles.add}
            onPress={() => router.push({ pathname: "/(drawer)/edit-person", params: {} })}
            accessibilityRole="button"
            accessibilityLabel={t("recordForm.addPerson")}
          >
            <Text style={styles.addText}>+</Text>
          </TouchableOpacity>
        )}
      </View>

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
      <ChipRow label={t("people.linkedinFilter")}>
        <FilterChip label={t("people.everyone")} isActive={linkedin === ""} onPress={() => setLinkedin("")} />
        <FilterChip label={t("people.linkedinOnly")} isActive={linkedin === "1"} onPress={() => setLinkedin("1")} />
        <FilterChip
          label={t("people.linkedinUnlinked")}
          isActive={linkedin === "unlinked"}
          onPress={() => setLinkedin("unlinked")}
        />
      </ChipRow>
      <ChipRow label={t("common.sortBy")}>
        {SORT_OPTIONS.map((option) => (
          <FilterChip
            key={`${option.key}-${option.dir}`}
            label={t(option.labelKey)}
            isActive={sort === option.key && dir === option.dir}
            onPress={() => {
              setSort(option.key);
              setDir(option.dir);
            }}
          />
        ))}
      </ChipRow>

      {loading ? (
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

function PersonRow({ person, onPress }: { person: Person; onPress: (id: number) => void }) {
  const { t } = useTranslation();
  const subtitle = [person.title, person.company].filter(Boolean).join(" · ");
  const meta = [`#${person.id}`, person.city, person.email].join("  ·  ");
  const shownStage = person.pipeline_stage ?? null;
  return (
    <TouchableOpacity style={styles.row} onPress={() => onPress(person.id)}>
      <View style={styles.line}>
        <Text style={styles.name} numberOfLines={1}>
          {person.name}
        </Text>
        {!!person.is_linkedin_contact && <Text style={styles.linkedin}>{t("search.linkedinPerson")}</Text>}
        {!!shownStage && <Text style={styles.stage}>{t(stageLabelKey(shownStage))}</Text>}
      </View>
      {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      {!!meta && <Text style={styles.meta}>{meta}</Text>}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  searchRow: { alignItems: "center", flexDirection: "row", gap: 8, margin: 16, marginBottom: 8 },
  search: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    flex: 1,
    padding: 12,
    fontSize: 14,
  },
  add: {
    alignItems: "center",
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    justifyContent: "center",
    minHeight: 44,
    width: 44,
  },
  addText: { color: "#fff", fontSize: 24, fontWeight: "600", lineHeight: 28 },
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

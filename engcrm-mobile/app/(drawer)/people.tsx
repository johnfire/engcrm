import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  TextInput,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
  ScrollView,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { fetchPeople, Person, PersonSortKey } from "../../services/api";
import { useTranslation } from "../../i18n/I18nContext";

const SORT_OPTIONS: { key: PersonSortKey; dir: "asc" | "desc"; labelKey: string }[] = [
  { key: "created_at", dir: "desc", labelKey: "common.sortNewest" },
  { key: "name", dir: "asc", labelKey: "common.sortAZ" },
];

export default function PeopleScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<PersonSortKey>("created_at");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchPeople({ search, sort, dir }));
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [search, sort, dir]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.search}
        placeholder={t("people.searchPlaceholder")}
        placeholderTextColor="#555"
        value={search}
        onChangeText={setSearch}
        onSubmitEditing={load}
        returnKeyType="search"
        autoCapitalize="none"
      />
      <Text style={styles.sortLabel}>{t("common.sortBy")}</Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filters}
        contentContainerStyle={styles.filtersContent}
      >
        {SORT_OPTIONS.map((opt) => {
          const active = sort === opt.key && dir === opt.dir;
          return (
            <TouchableOpacity
              key={opt.key}
              style={[styles.chip, active && styles.chipActive]}
              onPress={() => {
                setSort(opt.key);
                setDir(opt.dir);
              }}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>
                {t(opt.labelKey)}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(person) => String(person.id)}
          renderItem={({ item }) => {
            const subtitle = [item.title, item.company]
              .filter(Boolean)
              .join(" · ");
            const meta = [item.city, item.email].filter(Boolean).join("  ·  ");
            return (
              <TouchableOpacity
                style={styles.row}
                onPress={() =>
                  router.push({
                    pathname: "/(drawer)/person-detail",
                    params: { id: String(item.id) },
                  })
                }
              >
                <Text style={styles.name}>{item.name}</Text>
                {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
                {!!meta && <Text style={styles.meta}>{meta}</Text>}
              </TouchableOpacity>
            );
          }}
          refreshControl={
            <RefreshControl
              refreshing={loading}
              onRefresh={load}
              tintColor="#7c6fff"
            />
          }
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.empty}>
              {loadError ? t("common.couldntLoadRefresh") : t("people.empty")}
            </Text>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  search: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    margin: 16,
    marginBottom: 8,
    padding: 12,
    fontSize: 14,
  },
  sortLabel: { color: "#666", fontSize: 11, marginHorizontal: 16, marginBottom: 4 },
  // flexGrow:0 keeps the horizontal chip bar from stretching in the column;
  // the contentContainer's vertical padding + centered alignment give the
  // chips room so their text isn't clipped top/bottom on Android.
  filters: { marginHorizontal: 16, marginBottom: 8, flexGrow: 0 },
  filtersContent: { gap: 8, alignItems: "center", paddingVertical: 6 },
  chip: {
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 6,
    minHeight: 32,
    justifyContent: "center",
    backgroundColor: "#ffffff10",
  },
  chipActive: { backgroundColor: "#7c6fff" },
  chipText: { color: "#888", fontSize: 12, fontWeight: "600", lineHeight: 16 },
  chipTextActive: { color: "#fff" },
  list: { padding: 16 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  row: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: "#ffffff12",
  },
  name: { color: "#fff", fontSize: 16, fontWeight: "600" },
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

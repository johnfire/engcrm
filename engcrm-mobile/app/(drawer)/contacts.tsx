import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  TextInput,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  ScrollView,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { fetchContacts, Contact, ContactSortKey } from "../../services/api";
import { ContactRow } from "../../components/ContactRow";
import { useTranslation } from "../../i18n/I18nContext";

const SORT_OPTIONS: { key: ContactSortKey; dir: "asc" | "desc"; labelKey: string }[] = [
  { key: "created_at", dir: "desc", labelKey: "common.sortNewest" },
  { key: "name", dir: "asc", labelKey: "common.sortAZ" },
  { key: "type", dir: "asc", labelKey: "common.sortIndustry" },
];

const STATUS_FILTERS = [
  "",
  "cold",
  "contacted",
  "meeting",
  "proposal",
  "accepted",
  "rejected",
  "dropped",
];
const STATUS_LABEL_KEYS: Record<string, string> = {
  "": "contacts.statusAll",
  cold: "contacts.statusCold",
  contacted: "contacts.statusContacted",
  meeting: "contacts.statusMeeting",
  proposal: "contacts.statusProposal",
  accepted: "contacts.statusAccepted",
  rejected: "contacts.statusRejected",
  dropped: "contacts.statusDropped",
};

export default function ContactsScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [items, setItems] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<ContactSortKey>("created_at");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchContacts({ search, status, sort, dir }));
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [search, status, sort, dir]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.search}
        placeholder={t("contacts.searchPlaceholder")}
        placeholderTextColor="#555"
        value={search}
        onChangeText={setSearch}
        onSubmitEditing={load}
        returnKeyType="search"
      />
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filters}
        contentContainerStyle={styles.filtersContent}
      >
        {STATUS_FILTERS.map((filter) => (
          <TouchableOpacity
            key={filter}
            style={[styles.chip, status === filter && styles.chipActive]}
            onPress={() => setStatus(filter)}
          >
            <Text style={[styles.chipText, status === filter && styles.chipTextActive]}>
              {t(STATUS_LABEL_KEYS[filter])}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
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
          keyExtractor={(contact) => String(contact.id)}
          renderItem={({ item }) => (
            <ContactRow
              item={item}
              onPress={(id) =>
                router.push({
                  pathname: "/(drawer)/contact-detail",
                  params: { id },
                })
              }
            />
          )}
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
              {loadError ? t("common.couldntLoadRefresh") : t("contacts.notFound")}
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
  // flexGrow:0 keeps the horizontal chip bar from stretching in the column;
  // the contentContainer's vertical padding + centered alignment give the
  // chips room so their text isn't clipped top/bottom on Android.
  filters: { marginHorizontal: 16, marginBottom: 8, flexGrow: 0 },
  filtersContent: { gap: 8, alignItems: "center", paddingVertical: 6 },
  sortLabel: { color: "#666", fontSize: 11, marginHorizontal: 16, marginBottom: 4 },
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
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

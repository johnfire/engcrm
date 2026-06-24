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
import { fetchContacts, Contact } from "../../services/api";
import { ContactRow } from "../../components/ContactRow";

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
const STATUS_LABELS: Record<string, string> = {
  "": "All",
  cold: "Cold",
  contacted: "Contacted",
  meeting: "Meeting",
  proposal: "Proposal",
  accepted: "Accepted",
  rejected: "Rejected",
  dropped: "Dropped",
};

export default function ContactsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchContacts({ search, status }));
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [search, status]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.search}
        placeholder="Search city, name, type..."
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
              {STATUS_LABELS[filter]}
            </Text>
          </TouchableOpacity>
        ))}
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
              {loadError ? "Couldn't load — pull down to refresh" : "No contacts found"}
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
  filters: { marginHorizontal: 16, marginBottom: 8 },
  filtersContent: { gap: 8 },
  chip: {
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: "#ffffff10",
  },
  chipActive: { backgroundColor: "#7c6fff" },
  chipText: { color: "#888", fontSize: 12, fontWeight: "600" },
  chipTextActive: { color: "#fff" },
  list: { padding: 16 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

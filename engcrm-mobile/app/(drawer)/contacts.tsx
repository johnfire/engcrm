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
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchContacts({ search, status }));
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
    <View style={s.container}>
      <TextInput
        style={s.search}
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
        style={s.filters}
        contentContainerStyle={s.filtersContent}
      >
        {STATUS_FILTERS.map((f) => (
          <TouchableOpacity
            key={f}
            style={[s.chip, status === f && s.chipActive]}
            onPress={() => setStatus(f)}
          >
            <Text style={[s.chipText, status === f && s.chipTextActive]}>
              {STATUS_LABELS[f]}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      {loading ? (
        <View style={s.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(c) => String(c.id)}
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
          contentContainerStyle={s.list}
          ListEmptyComponent={<Text style={s.empty}>No contacts found</Text>}
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
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

import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  Text,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { fetchInbox, classifyMessage, InboxMessage } from "../../services/api";
import { ClassifySheet } from "../../components/ClassifySheet";

const CLASSIFICATION_COLOR: Record<string, string> = {
  interested: "#22c55e",
  warm: "#84cc16",
  not_interested: "#ef4444",
  not_possible: "#f97316",
  opt_out: "#dc2626",
  bounce: "#888",
  other: "#888",
};

export default function InboxScreen() {
  const [items, setItems] = useState<InboxMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [classifyTarget, setClassifyTarget] = useState<InboxMessage | null>(
    null,
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchInbox());
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function handleClassify(classification: string) {
    if (!classifyTarget) return;
    await classifyMessage(classifyTarget.id, classification);
    setItems((prev) =>
      prev.map((m) =>
        m.id === classifyTarget.id ? { ...m, classification } : m,
      ),
    );
    setClassifyTarget(null);
  }

  if (loading)
    return (
      <View style={s.center}>
        <ActivityIndicator color="#7c6fff" />
      </View>
    );

  return (
    <View style={s.container}>
      <FlatList
        data={items}
        keyExtractor={(m) => String(m.id)}
        renderItem={({ item }) => {
          const color = item.classification
            ? (CLASSIFICATION_COLOR[item.classification] ?? "#888")
            : "#444";
          return (
            <View style={[s.item, { borderLeftColor: color }]}>
              <Text style={s.from}>{item.contact_name ?? item.from_email}</Text>
              <Text style={s.subject}>{item.subject}</Text>
              <Text style={s.body} numberOfLines={2}>
                {item.body}
              </Text>
              <TouchableOpacity
                style={[s.badge, { borderColor: color }]}
                onPress={() => setClassifyTarget(item)}
              >
                <Text style={[s.badgeText, { color }]}>
                  {item.classification ?? "Classify"}
                </Text>
              </TouchableOpacity>
            </View>
          );
        }}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={load}
            tintColor="#7c6fff"
          />
        }
        contentContainerStyle={s.list}
        ListEmptyComponent={<Text style={s.empty}>Inbox is empty</Text>}
      />
      <ClassifySheet
        visible={!!classifyTarget}
        onSelect={handleClassify}
        onCancel={() => setClassifyTarget(null)}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  list: { padding: 16 },
  center: {
    flex: 1,
    backgroundColor: "#0f0f23",
    justifyContent: "center",
    alignItems: "center",
  },
  item: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
    borderLeftWidth: 3,
  },
  from: { color: "#fff", fontSize: 13, fontWeight: "700", marginBottom: 2 },
  subject: { color: "#aaa", fontSize: 12, marginBottom: 6 },
  body: { color: "#666", fontSize: 12, lineHeight: 18, marginBottom: 10 },
  badge: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  badgeText: { fontSize: 11, fontWeight: "600" },
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

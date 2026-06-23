import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { listPendingCards, PendingCard, CaptureResult } from "../../services/api";

export default function CardQueueScreen() {
  const router = useRouter();
  const [items, setItems] = useState<PendingCard[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await listPendingCards());
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  function review(card: PendingCard) {
    // Rebuild a CaptureResult so the confirm screen works the same as a fresh scan.
    const capture: CaptureResult = {
      capture_id: card.id,
      is_card: true,
      confidence: card.confidence,
      fields: card.extracted || {},
      dup_suggestion: null, // backend re-checks dedup on save
      cost_usd: 0,
    };
    router.push({
      pathname: "/(drawer)/card-confirm",
      params: { data: JSON.stringify(capture) },
    });
  }

  return (
    <View style={s.container}>
      {loading ? (
        <View style={s.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(c) => String(c.id)}
          renderItem={({ item }) => {
            const f = item.extracted || {};
            const title = f.company || f.name || "Unread card";
            const sub = [f.name, f.email].filter(Boolean).join("  ·  ");
            return (
              <TouchableOpacity style={s.row} onPress={() => review(item)}>
                <Text style={s.rowTitle}>{title}</Text>
                {!!sub && <Text style={s.rowSub}>{sub}</Text>}
                <Text style={s.rowMeta}>
                  {typeof item.confidence === "number" ? `${item.confidence}%  ·  ` : ""}
                  {new Date(item.captured_at).toLocaleString()}
                </Text>
              </TouchableOpacity>
            );
          }}
          refreshControl={
            <RefreshControl refreshing={loading} onRefresh={load} tintColor="#7c6fff" />
          }
          contentContainerStyle={s.list}
          ListEmptyComponent={
            <Text style={s.empty}>
              No cards waiting for review.{"\n"}Scanned cards you don’t finish show up here.
            </Text>
          }
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  list: { padding: 16 },
  row: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: "#ffffff12",
  },
  rowTitle: { color: "#fff", fontSize: 16, fontWeight: "600" },
  rowSub: { color: "#aaa", fontSize: 13, marginTop: 3 },
  rowMeta: { color: "#666", fontSize: 11, marginTop: 6 },
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15, lineHeight: 22 },
});

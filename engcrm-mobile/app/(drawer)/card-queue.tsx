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
import { setHandoff } from "../../services/handoff";
import { useTranslation } from "../../i18n/I18nContext";

export default function CardQueueScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [items, setItems] = useState<PendingCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await listPendingCards());
      setLoadError(false);
    } catch {
      setLoadError(true);
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
    setHandoff("card", capture);
    router.push("/(drawer)/card-confirm");
  }

  return (
    <View style={styles.container}>
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(capture) => String(capture.id)}
          renderItem={({ item }) => {
            const fields = item.extracted || {};
            const title = fields.company || fields.name || t("cardQueue.unreadCard");
            const sub = [fields.name, fields.email].filter(Boolean).join("  ·  ");
            return (
              <TouchableOpacity style={styles.row} onPress={() => review(item)}>
                <Text style={styles.rowTitle}>{title}</Text>
                {!!sub && <Text style={styles.rowSub}>{sub}</Text>}
                <Text style={styles.rowMeta}>
                  {typeof item.confidence === "number" ? `${item.confidence}%  ·  ` : ""}
                  {new Date(item.captured_at).toLocaleString()}
                </Text>
              </TouchableOpacity>
            );
          }}
          refreshControl={
            <RefreshControl refreshing={loading} onRefresh={load} tintColor="#7c6fff" />
          }
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.empty}>
              {loadError ? t("common.couldntLoadRefresh") : t("cardQueue.emptyTitle")}
            </Text>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
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

import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { fetchActivity, AgentRun } from "../../services/api";

const STATUS_COLOR: Record<string, string> = {
  running: "#eab308",
  completed: "#22c55e",
  failed: "#ef4444",
};

export default function ActivityScreen() {
  const [items, setItems] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchActivity());
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  if (loading)
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#7c6fff" />
      </View>
    );

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        keyExtractor={(run) => String(run.id)}
        renderItem={({ item }) => {
          const color = STATUS_COLOR[item.status] ?? "#888";
          return (
            <View style={[styles.item, { borderLeftColor: color }]}>
              <Text style={styles.agent}>{item.agent_name}</Text>
              <Text style={[styles.status, { color }]}>{item.status}</Text>
              {item.summary && <Text style={styles.summary}>{item.summary}</Text>}
              <Text style={styles.time}>
                {new Date(item.started_at).toLocaleString()}
              </Text>
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
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {loadError ? "Couldn't load — pull down to refresh" : "No activity yet"}
          </Text>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
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
    marginBottom: 8,
    borderLeftWidth: 3,
  },
  agent: { color: "#fff", fontSize: 14, fontWeight: "700", marginBottom: 2 },
  status: { fontSize: 12, fontWeight: "600", marginBottom: 4 },
  summary: { color: "#888", fontSize: 12, marginBottom: 4 },
  time: { color: "#555", fontSize: 11 },
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

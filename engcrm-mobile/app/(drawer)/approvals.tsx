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
import {
  fetchApprovals,
  approveEmail,
  rejectEmail,
  Approval,
} from "../../services/api";
import { ApprovalCard } from "../../components/ApprovalCard";
import { RejectSheet } from "../../components/RejectSheet";

export default function ApprovalsScreen() {
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [rejectTarget, setRejectTarget] = useState<Approval | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchApprovals());
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function handleApprove(id: number) {
    await approveEmail(id);
    setItems((prev) => prev.filter((a) => a.id !== id));
  }

  async function handleReject(item: Approval) {
    setRejectTarget(item);
  }

  async function confirmReject(reason: string) {
    if (!rejectTarget) return;
    await rejectEmail(rejectTarget.id, reason);
    setItems((prev) => prev.filter((a) => a.id !== rejectTarget.id));
    setRejectTarget(null);
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
        keyExtractor={(a) => String(a.id)}
        renderItem={({ item }) => (
          <ApprovalCard
            item={item}
            onApprove={handleApprove}
            onReject={handleReject}
            onEdit={() => {}}
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
        ListEmptyComponent={<Text style={s.empty}>No pending approvals</Text>}
      />
      <RejectSheet
        visible={!!rejectTarget}
        venueName={
          rejectTarget ? `${rejectTarget.name}, ${rejectTarget.city}` : ""
        }
        onConfirm={confirmReject}
        onCancel={() => setRejectTarget(null)}
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
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

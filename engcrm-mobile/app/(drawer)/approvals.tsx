import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
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
import { useTranslation } from "../../i18n/I18nContext";

export default function ApprovalsScreen() {
  const { t } = useTranslation();
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<Approval | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchApprovals());
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

  async function handleApprove(id: number) {
    try {
      await approveEmail(id);
      setItems((prev) => prev.filter((approval) => approval.id !== id));
    } catch (error: any) {
      Alert.alert(
        t("approvals.couldntApproveTitle"),
        error?.response ? t("common.serverError", { status: error.response.status }) : error?.message || t("common.tryAgain"),
      );
    }
  }

  async function handleReject(item: Approval) {
    setRejectTarget(item);
  }

  async function confirmReject(reason: string) {
    if (!rejectTarget) return;
    try {
      await rejectEmail(rejectTarget.id, reason);
      setItems((prev) => prev.filter((approval) => approval.id !== rejectTarget.id));
      setRejectTarget(null);
    } catch (error: any) {
      Alert.alert(
        t("approvals.couldntRejectTitle"),
        error?.response ? t("common.serverError", { status: error.response.status }) : error?.message || t("common.tryAgain"),
      );
    }
  }

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
        keyExtractor={(approval) => String(approval.id)}
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
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {loadError ? t("common.couldntLoadRefresh") : t("approvals.empty")}
          </Text>
        }
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

const styles = StyleSheet.create({
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

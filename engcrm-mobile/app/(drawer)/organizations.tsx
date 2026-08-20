import { useState, useCallback } from "react";
import {
  View,
  FlatList,
  TextInput,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { fetchOrganizations, Organization, OrganizationSortKey } from "../../services/api";
import { OrganizationListControls } from "../../components/OrganizationListControls";
import { OrganizationRow } from "../../components/OrganizationRow";
import { useTranslation } from "../../i18n/I18nContext";

export default function OrganizationsScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [items, setItems] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [personalPriority, setPersonalPriority] = useState("");
  const [sort, setSort] = useState<OrganizationSortKey>("created_at");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(
        await fetchOrganizations({
          search,
          stage,
          status,
          sort,
          dir,
          personal_priority: personalPriority,
        }),
      );
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [search, stage, status, personalPriority, sort, dir]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.search}
        placeholder={t("organizations.searchPlaceholder")}
        placeholderTextColor="#555"
        value={search}
        onChangeText={setSearch}
        onSubmitEditing={load}
        returnKeyType="search"
      />
      <OrganizationListControls
        stage={stage}
        status={status}
        personalPriority={personalPriority}
        sort={sort}
        direction={dir}
        onStageChange={setStage}
        onStatusChange={setStatus}
        onPriorityChange={setPersonalPriority}
        onSortChange={(nextSort, nextDirection) => {
          setSort(nextSort);
          setDir(nextDirection);
        }}
      />
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(organization) => String(organization.id)}
          renderItem={({ item }) => (
            <OrganizationRow
              item={item}
              onPress={(id) =>
                router.push({
                  pathname: "/(drawer)/organization-detail",
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
              {loadError ? t("common.couldntLoadRefresh") : t("organizations.notFound")}
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
  list: { padding: 16 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

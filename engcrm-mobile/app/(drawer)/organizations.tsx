import { useCallback, useEffect, useState } from "react";
import {
  View,
  FlatList,
  TextInput,
  Text,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import {
  fetchOrganizations,
  Organization,
  OrganizationSortKey,
  ORGANIZATIONS_PAGE_SIZE,
} from "../../services/api";
import { getRole } from "../../services/auth";
import { usePagedList } from "../../services/usePagedList";
import { OrganizationListControls } from "../../components/OrganizationListControls";
import { OrganizationRow } from "../../components/OrganizationRow";
import { useTranslation } from "../../i18n/I18nContext";

export default function OrganizationsScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [isAdmin, setIsAdmin] = useState(false);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [personalPriority, setPersonalPriority] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [suppressed, setSuppressed] = useState("");
  const [sort, setSort] = useState<OrganizationSortKey>("created_at");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const fetchPage = useCallback(
    (page: number): Promise<Organization[]> =>
      fetchOrganizations({
        search,
        stage,
        status,
        sort,
        dir,
        personal_priority: personalPriority,
        linkedin,
        suppressed,
        page,
      }),
    [search, stage, status, sort, dir, personalPriority, linkedin, suppressed],
  );
  const { items, loading, loadingMore, error, reload, loadMore } = usePagedList(
    fetchPage,
    ORGANIZATIONS_PAGE_SIZE,
  );

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useFocusEffect(
    useCallback(() => {
      reload();
    }, [reload]),
  );

  return (
    <View style={styles.container}>
      <View style={styles.searchRow}>
        <TextInput
          style={styles.search}
          placeholder={t("organizations.searchPlaceholder")}
          placeholderTextColor="#555"
          value={search}
          onChangeText={setSearch}
          onSubmitEditing={reload}
          returnKeyType="search"
          accessibilityLabel={t("organizations.searchPlaceholder")}
        />
        {isAdmin && (
          <TouchableOpacity
            style={styles.add}
            onPress={() => router.push({ pathname: "/(drawer)/edit-organization", params: {} })}
            accessibilityRole="button"
            accessibilityLabel={t("recordForm.addOrganization")}
          >
            <Text style={styles.addText}>+</Text>
          </TouchableOpacity>
        )}
      </View>
      <OrganizationListControls
        stage={stage}
        status={status}
        personalPriority={personalPriority}
        linkedin={linkedin}
        suppressed={suppressed}
        sort={sort}
        direction={dir}
        onStageChange={setStage}
        onStatusChange={setStatus}
        onPriorityChange={setPersonalPriority}
        onLinkedinChange={setLinkedin}
        onSuppressedChange={setSuppressed}
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
          refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} tintColor="#7c6fff" />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={loadingMore ? <ActivityIndicator color="#7c6fff" style={styles.more} /> : null}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.empty}>
              {error ? t("common.couldntLoadRefresh") : t("organizations.notFound")}
            </Text>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  searchRow: { alignItems: "center", flexDirection: "row", gap: 8, margin: 16, marginBottom: 8 },
  search: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    flex: 1,
    padding: 12,
    fontSize: 14,
  },
  add: {
    alignItems: "center",
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    justifyContent: "center",
    minHeight: 44,
    width: 44,
  },
  addText: { color: "#fff", fontSize: 24, fontWeight: "600", lineHeight: 28 },
  list: { padding: 16 },
  more: { marginVertical: 16 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  empty: { color: "#555", textAlign: "center", marginTop: 60, fontSize: 15 },
});

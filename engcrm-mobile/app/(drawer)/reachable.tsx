import { useCallback } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { fetchReachable, REACHABLE_PAGE_SIZE, ReachableOrganization } from "../../services/api";
import { usePagedList } from "../../services/usePagedList";
import { useTranslation } from "../../i18n/I18nContext";

const fetchPage = async (page: number): Promise<ReachableOrganization[]> => (await fetchReachable(page)).rows;

/** The warm-intro work list: organizations that look like a fit and where you know
 *  someone on LinkedIn, best fit first. You write to these yourself, on LinkedIn —
 *  the outreach agent never emails them cold. */
export default function ReachableScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { items, loading, loadingMore, error, reload, loadMore } = usePagedList(fetchPage, REACHABLE_PAGE_SIZE);

  useFocusEffect(
    useCallback(() => {
      reload();
    }, [reload]),
  );

  return (
    <View style={styles.container}>
      <Text style={styles.intro}>{t("reachable.intro")}</Text>
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color="#7c6fff" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(organization) => String(organization.id)}
          renderItem={({ item }) => (
            <View style={styles.card}>
              <TouchableOpacity
                onPress={() =>
                  router.push({ pathname: "/(drawer)/organization-detail", params: { id: String(item.id) } })
                }
                accessibilityRole="button"
                accessibilityLabel={item.name}
              >
                <View style={styles.line}>
                  <Text style={styles.name} numberOfLines={1}>
                    {item.name}
                  </Text>
                  {item.fit_score !== null && <Text style={styles.score}>{item.fit_score}</Text>}
                </View>
                <Text style={styles.sub} numberOfLines={1}>
                  {[item.city, item.type].filter(Boolean).join(" · ")}
                </Text>
              </TouchableOpacity>
              {item.people.map((person) => (
                <TouchableOpacity
                  key={person.id}
                  style={styles.person}
                  onPress={() =>
                    router.push({ pathname: "/(drawer)/person-detail", params: { id: String(person.id) } })
                  }
                  accessibilityRole="button"
                  accessibilityLabel={person.name}
                >
                  <Text style={styles.personName}>{person.name}</Text>
                  {!!person.title && (
                    <Text style={styles.personTitle} numberOfLines={1}>
                      {person.title}
                    </Text>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          )}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} tintColor="#7c6fff" />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={loadingMore ? <ActivityIndicator color="#7c6fff" style={styles.more} /> : null}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.empty}>{error ? t("common.couldntLoadRefresh") : t("reachable.empty")}</Text>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  intro: { color: "#888", fontSize: 13, lineHeight: 18, margin: 16, marginBottom: 4 },
  list: { padding: 16 },
  more: { marginVertical: 16 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  card: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff12",
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 10,
    padding: 16,
  },
  line: { alignItems: "center", flexDirection: "row", gap: 8, justifyContent: "space-between" },
  name: { color: "#fff", flexShrink: 1, fontSize: 16, fontWeight: "600" },
  score: { color: "#22c55e", fontSize: 14, fontWeight: "700" },
  sub: { color: "#888", fontSize: 13, marginTop: 3 },
  person: { borderTopColor: "#ffffff12", borderTopWidth: 1, marginTop: 10, paddingTop: 10 },
  personName: { color: "#b9adff", fontSize: 14, fontWeight: "600" },
  personTitle: { color: "#999", fontSize: 12, marginTop: 2 },
  empty: { color: "#555", fontSize: 15, lineHeight: 22, marginTop: 60, textAlign: "center" },
});

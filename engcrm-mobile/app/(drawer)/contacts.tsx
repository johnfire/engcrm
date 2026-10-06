import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { AddBusinessButton } from "../../components/add-business-button";
import { ContactFeedRow } from "../../components/contact-feed-row";
import { ContactFeedControls } from "../../components/contact-feed-controls";
import { useTranslation } from "../../i18n/I18nContext";
import { CONTACT_FEED_PAGE_SIZE, ContactKind, ContactSort, contactKey, fetchContactFeed } from "../../services/contact-feed";
import { useAdminRole } from "../../services/use-admin-role";
import { usePagedList } from "../../services/usePagedList";

export default function ContactsScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const isAdmin = useAdminRole();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<ContactKind | "">("");
  const [stage, setStage] = useState("");
  const [sort, setSort] = useState<ContactSort>("last_contact");
  const fetchPage = useCallback((page: number) => fetchContactFeed({ search, kind, stage, sort, page }),
    [search, kind, stage, sort]);
  const { items, loading, loadingMore, error, reload, loadMore } = usePagedList(fetchPage, CONTACT_FEED_PAGE_SIZE, contactKey);
  useFocusEffect(useCallback(() => { void reload(); }, [reload]));

  return (
    <View style={styles.container}>
      <AddBusinessButton isAdmin={!!isAdmin} />
      <ContactFeedControls search={search} kind={kind} stage={stage} sort={sort}
        onSearchChange={setSearch} onKindChange={setKind} onStageChange={setStage} onSortChange={setSort} onSubmit={reload} />
      {error && <Text style={styles.message}>{t("common.couldntLoadRefresh")}</Text>}
      {loading ? <ActivityIndicator style={styles.loading} color="#7c6fff" /> : <FlatList
        data={items} keyExtractor={contactKey} contentContainerStyle={styles.list}
        renderItem={({ item: contact }) => <ContactFeedRow contact={contact} canEdit={!!isAdmin} onPress={() => router.push({
          pathname: contact.kind === "person" ? "/(drawer)/person-detail" : "/(drawer)/organization-detail",
          params: { id: String(contact.id) },
        })} />}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} tintColor="#7c6fff" />}
        onEndReached={loadMore} onEndReachedThreshold={0.5} keyboardShouldPersistTaps="handled"
        ListFooterComponent={loadingMore ? <ActivityIndicator color="#7c6fff" /> : null}
        ListEmptyComponent={!error ? <Text style={styles.message}>{t("contactFeed.empty")}</Text> : null}
      />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  list: { padding: 16 },
  loading: { flex: 1 },
  message: { color: "#bbb", textAlign: "center", padding: 20, fontSize: 15 },
});

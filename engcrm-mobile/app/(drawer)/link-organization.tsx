import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { fetchOrganizations, Organization, setPersonOrganization } from "../../services/api";
import { getRole } from "../../services/auth";
import { notifyChanged, personKey } from "../../services/refreshBus";
import { useTranslation } from "../../i18n/I18nContext";

/**
 * Link a person to the organization they work at, as the web's "Link / change" page
 * does: search by name or city (starting from the company LinkedIn names, when there
 * is one) and tap Link. Admin only.
 */
export default function LinkOrganizationScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useLocalSearchParams<{ id: string; name?: string; q?: string; current?: string }>();
  const personId = Number(params.id);
  const current = params.current ? Number(params.current) : null;
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [query, setQuery] = useState(params.q ?? "");
  const [results, setResults] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(false);
  const [linking, setLinking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  // Search a moment after typing stops; a newer search replaces an older one.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const term = query.trim();
    if (!term) return; // an empty box shows nothing (see `shown`)
    let stale = false;
    timer.current = setTimeout(() => {
      setLoading(true);
      fetchOrganizations({ search: term, offer: "all" })
        .then((found) => {
          if (!stale) setResults(found);
        })
        .catch(() => {
          if (!stale) setResults([]);
        })
        .finally(() => {
          if (!stale) setLoading(false);
        });
    }, 300);
    return () => {
      stale = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [query]);

  async function link(organizationId: number) {
    setLinking(organizationId);
    setError(null);
    try {
      await setPersonOrganization(personId, organizationId);
      notifyChanged(personKey(personId));
      if (router.canGoBack()) router.back();
      else router.replace({ pathname: "/(drawer)/person-detail", params: { id: String(personId) } });
    } catch (err: any) {
      setError(err?.response?.data?.detail || t("recordForm.saveFailed"));
      setLinking(null);
    }
  }

  const shown = query.trim() ? results : [];

  if (isAdmin === false) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{t("recordForm.adminOnly")}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {!!params.name && <Text style={styles.subject}>{params.name}</Text>}
      <TextInput
        style={styles.input}
        value={query}
        onChangeText={setQuery}
        placeholder={t("personLink.searchPlaceholder")}
        placeholderTextColor="#555"
        autoFocus
        autoCorrect={false}
        accessibilityLabel={t("common.search")}
      />
      {!!error && <Text style={styles.error}>{error}</Text>}
      {loading ? (
        <ActivityIndicator color="#7c6fff" style={styles.loading} />
      ) : (
        <FlatList
          data={shown}
          keyExtractor={(item) => String(item.id)}
          keyboardShouldPersistTaps="handled"
          ListEmptyComponent={query.trim() ? <Text style={styles.muted}>{t("personLink.noResults")}</Text> : null}
          renderItem={({ item }) => {
            const isCurrent = item.id === current;
            return (
              <View style={styles.row}>
                <View style={styles.rowText}>
                  <Text style={styles.name}>{item.name}</Text>
                  {!!item.city && <Text style={styles.city}>{item.city}</Text>}
                </View>
                <TouchableOpacity
                  style={[styles.link, (isCurrent || linking !== null) && styles.linkDisabled]}
                  onPress={() => link(item.id)}
                  disabled={isCurrent || linking !== null}
                  accessibilityRole="button"
                  accessibilityLabel={`${t("personLink.link")} ${item.name}`}
                  accessibilityState={{ disabled: isCurrent || linking !== null, busy: linking === item.id }}
                >
                  {linking === item.id ? (
                    <ActivityIndicator color="#fff" size="small" />
                  ) : (
                    <Text style={styles.linkText}>{t("personLink.link")}</Text>
                  )}
                </TouchableOpacity>
              </View>
            );
          }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: "#0f0f23", flex: 1, padding: 16 },
  center: { alignItems: "center", backgroundColor: "#0f0f23", flex: 1, justifyContent: "center", padding: 24 },
  muted: { color: "#888", fontSize: 14, marginTop: 12, textAlign: "center" },
  subject: { color: "#fff", fontSize: 18, fontWeight: "700", marginBottom: 10 },
  input: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff20",
    borderRadius: 10,
    borderWidth: 1,
    color: "#fff",
    fontSize: 16,
    marginBottom: 8,
    minHeight: 48,
    paddingHorizontal: 14,
  },
  error: { color: "#ef8a8a", fontSize: 13, marginBottom: 8 },
  loading: { marginTop: 20 },
  row: {
    alignItems: "center",
    borderBottomColor: "#ffffff10",
    borderBottomWidth: 1,
    flexDirection: "row",
    gap: 10,
    paddingVertical: 10,
  },
  rowText: { flex: 1 },
  name: { color: "#fff", fontSize: 15 },
  city: { color: "#888", fontSize: 12, marginTop: 2 },
  link: {
    alignItems: "center",
    backgroundColor: "#7c6fff",
    borderRadius: 8,
    justifyContent: "center",
    minHeight: 36,
    minWidth: 70,
    paddingHorizontal: 12,
  },
  linkDisabled: { opacity: 0.4 },
  linkText: { color: "#fff", fontSize: 14, fontWeight: "700" },
});

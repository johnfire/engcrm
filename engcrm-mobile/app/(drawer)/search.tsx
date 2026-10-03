import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  SectionList,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useRouter } from "expo-router";

import { getRole } from "../../services/auth";
import { searchAll, SearchOrganization, SearchPerson, SearchResults } from "../../services/api";
import { stageLabelKey } from "../../services/organizationState";
import { useTranslation } from "../../i18n/I18nContext";

const DEBOUNCE_MS = 300;
const MIN_CHARS = 2;

type Row =
  | { kind: "organization"; item: SearchOrganization }
  | { kind: "person"; item: SearchPerson };

/** Find anyone or any company, fast: the front door of the app. */
export default function SearchScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const [text, setText] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const latest = useRef(0); // an older, slower answer must never overwrite a newer one
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Searching is driven by typing (an event), not by an effect watching state.
  function onChange(next: string) {
    setText(next);
    if (timer.current) clearTimeout(timer.current);
    const query = next.trim();
    const ticket = ++latest.current;
    if (query.length < MIN_CHARS) {
      setResults(null);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    timer.current = setTimeout(() => {
      searchAll(query)
        .then((found) => {
          if (ticket !== latest.current) return;
          setResults(found);
          setFailed(false);
        })
        .catch(() => {
          if (ticket !== latest.current) return;
          setFailed(true);
        })
        .finally(() => {
          if (ticket === latest.current) setLoading(false);
        });
    }, DEBOUNCE_MS);
  }

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useEffect(
    () => () => {
      // Leaving the screen: no pending search, and no answer may land afterwards.
      if (timer.current) clearTimeout(timer.current);
      latest.current += 1;
    },
    [],
  );

  const sections = results
    ? [
        {
          key: "organizations",
          title: t("search.organizations"),
          data: results.organizations.map((item): Row => ({ kind: "organization", item })),
        },
        {
          key: "people",
          title: t("search.people"),
          data: results.people.map((item): Row => ({ kind: "person", item })),
        },
      ].filter((section) => section.data.length > 0)
    : [];

  function open(row: Row) {
    router.push({
      pathname: row.kind === "organization" ? "/(drawer)/organization-detail" : "/(drawer)/person-detail",
      params: { id: String(row.item.id) },
    });
  }

  const hasQuery = text.trim().length >= MIN_CHARS;

  // Look first, then add: the add rows appear under the results so that the
  // company or person is not created twice. The server checks as well.
  function add(kind: "organization" | "person") {
    router.push({
      pathname: kind === "organization" ? "/(drawer)/edit-organization" : "/(drawer)/edit-person",
      params: { name: text.trim() },
    });
  }

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        autoFocus
        value={text}
        onChangeText={onChange}
        placeholder={t("search.placeholder")}
        placeholderTextColor="#666"
        returnKeyType="search"
        autoCapitalize="none"
        autoCorrect={false}
        clearButtonMode="while-editing"
        accessibilityLabel={t("search.placeholder")}
      />

      {loading && (
        <View style={styles.status}>
          <ActivityIndicator color="#7c6fff" size="small" />
        </View>
      )}
      {failed && !loading && <Text style={styles.error}>{t("search.failed")}</Text>}
      {!hasQuery && <Text style={styles.hint}>{t("search.hint")}</Text>}
      {hasQuery && !loading && !failed && results && sections.length === 0 && (
        <Text style={styles.hint}>{t("search.nothing", { query: results.query })}</Text>
      )}

      <SectionList
        sections={sections}
        keyboardShouldPersistTaps="handled"
        ListFooterComponent={
          isAdmin && hasQuery && !loading ? (
            <View style={styles.addBox}>
              <Text style={styles.addTitle}>{t("search.addTitle", { query: text.trim() })}</Text>
              <TouchableOpacity style={styles.addButton} onPress={() => add("organization")} accessibilityRole="button">
                <Text style={styles.addText}>{t("search.addOrganization")}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.addButton} onPress={() => add("person")} accessibilityRole="button">
                <Text style={styles.addText}>{t("search.addPerson")}</Text>
              </TouchableOpacity>
            </View>
          ) : null
        }
        keyExtractor={(row) => `${row.kind}-${row.item.id}`}
        renderSectionHeader={({ section }) => <Text style={styles.sectionTitle}>{section.title}</Text>}
        renderItem={({ item: row }) => (
          <TouchableOpacity style={styles.row} onPress={() => open(row)} accessibilityRole="button">
            {row.kind === "organization" ? <OrganizationResult org={row.item} /> : <PersonResult person={row.item} />}
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

function OrganizationResult({ org }: { org: SearchOrganization }) {
  const { t } = useTranslation();
  const place = [org.city, org.country].filter(Boolean).join(", ");
  return (
    <>
      <View style={styles.line}>
        <Text style={styles.name} numberOfLines={1}>
          {org.name}
        </Text>
        {org.linkedin_connection_count > 0 && (
          <Text style={styles.linkedin}>{t("search.linkedinCount", { count: org.linkedin_connection_count })}</Text>
        )}
      </View>
      <Text style={styles.sub} numberOfLines={1}>
        {[place, org.type].filter(Boolean).join(" · ")}
      </Text>
      <Text style={styles.stage}>{t(stageLabelKey(org.pipeline_stage))}</Text>
    </>
  );
}

function PersonResult({ person }: { person: SearchPerson }) {
  const { t } = useTranslation();
  const stage = person.pipeline_stage ?? person.company_pipeline_stage;
  return (
    <>
      <View style={styles.line}>
        <Text style={styles.name} numberOfLines={1}>
          {person.name}
        </Text>
        {person.is_linkedin_contact && <Text style={styles.linkedin}>{t("search.linkedinPerson")}</Text>}
      </View>
      <Text style={styles.sub} numberOfLines={1}>
        {[person.title, person.company].filter(Boolean).join(" · ")}
      </Text>
      {!!stage && <Text style={styles.stage}>{t(stageLabelKey(stage))}</Text>}
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", paddingHorizontal: 16, paddingTop: 12 },
  input: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff25",
    borderRadius: 10,
    borderWidth: 1,
    color: "#fff",
    fontSize: 17,
    minHeight: 48,
    paddingHorizontal: 14,
  },
  status: { alignItems: "center", marginTop: 12 },
  hint: { color: "#777", fontSize: 14, marginTop: 20, textAlign: "center" },
  error: { color: "#ef8a8a", fontSize: 14, marginTop: 16, textAlign: "center" },
  sectionTitle: {
    backgroundColor: "#0f0f23",
    color: "#888",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    marginTop: 18,
    paddingBottom: 6,
    textTransform: "uppercase",
  },
  addBox: { marginBottom: 40, marginTop: 24 },
  addTitle: { color: "#888", fontSize: 13, marginBottom: 8 },
  addButton: {
    alignItems: "center",
    borderColor: "#7c6fff",
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: "center",
    marginBottom: 8,
    minHeight: 46,
  },
  addText: { color: "#b9b2ff", fontSize: 15, fontWeight: "600" },
  row: { borderBottomColor: "#ffffff15", borderBottomWidth: 1, paddingVertical: 12 },
  line: { alignItems: "center", flexDirection: "row", gap: 8 },
  name: { color: "#fff", flexShrink: 1, fontSize: 16, fontWeight: "600" },
  linkedin: {
    backgroundColor: "#0a66c2",
    borderRadius: 4,
    color: "#fff",
    fontSize: 11,
    fontWeight: "700",
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  sub: { color: "#999", fontSize: 13, marginTop: 3 },
  stage: { color: "#7c6fff", fontSize: 12, fontWeight: "600", marginTop: 3 },
});

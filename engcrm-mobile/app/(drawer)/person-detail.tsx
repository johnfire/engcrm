import { useState, useEffect } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Linking,
  TouchableOpacity,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { fetchPerson, Person } from "../../services/api";
import { openWebsite, browsableUrl } from "../../services/webLinks";
import { useTranslation } from "../../i18n/I18nContext";
import { PersonNotesLog } from "../../components/PersonNotesLog";

export default function PersonDetailScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [person, setPerson] = useState<Person | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    fetchPerson(Number(id))
      .then((loaded) => {
        setPerson(loaded);
        setLoadError(false);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading)
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#7c6fff" />
      </View>
    );
  if (!person)
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>
          {loadError ? t("personDetail.couldntLoad") : t("personDetail.notFound")}
        </Text>
      </View>
    );

  const role = [person.title, person.company].filter(Boolean).join(" · ");
  const place = [person.city, person.country].filter(Boolean).join(", ");

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.name}>{person.name}</Text>
      {!!role && <Text style={styles.sub}>{role}</Text>}
      {!!place && <Text style={styles.sub}>{place}</Text>}

      {person.email && (
        <TouchableOpacity
          onPress={() => Linking.openURL(`mailto:${person.email}`)}
        >
          <Text style={styles.link}>{person.email}</Text>
        </TouchableOpacity>
      )}
      {person.phone && (
        <TouchableOpacity onPress={() => Linking.openURL(`tel:${person.phone}`)}>
          <Text style={styles.link}>{person.phone}</Text>
        </TouchableOpacity>
      )}
      {person.website &&
        (browsableUrl(person.website) ? (
          <TouchableOpacity
            accessibilityRole="link"
            onPress={() => openWebsite(person.website)}
          >
            <Text style={styles.link}>{person.website}</Text>
          </TouchableOpacity>
        ) : (
          <Text style={styles.fieldText}>{person.website}</Text>
        ))}

      {person.met_at && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("personDetail.metAt")}</Text>
          <Text style={styles.fieldText}>{person.met_at}</Text>
        </View>
      )}

      {person.notes && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("common.notes")}</Text>
          <Text style={styles.fieldText}>{person.notes}</Text>
        </View>
      )}

      <PersonNotesLog personId={person.id} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  content: { padding: 20 },
  center: {
    flex: 1,
    backgroundColor: "#0f0f23",
    justifyContent: "center",
    alignItems: "center",
  },
  name: { color: "#fff", fontSize: 22, fontWeight: "700", marginBottom: 4 },
  sub: { color: "#888", fontSize: 14, marginBottom: 8 },
  link: {
    color: "#7c6fff",
    fontSize: 14,
    marginBottom: 8,
    textDecorationLine: "underline",
  },
  section: { marginTop: 20 },
  sectionTitle: {
    color: "#888",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    marginBottom: 8,
    textTransform: "uppercase",
  },
  fieldText: { color: "#ccc", fontSize: 14, lineHeight: 22 },
  empty: { color: "#555" },
});

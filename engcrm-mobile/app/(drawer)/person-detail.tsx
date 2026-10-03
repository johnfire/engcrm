import { useState, useEffect } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Linking,
  TouchableOpacity,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { deletePerson, fetchPerson, Person, updatePersonStage } from "../../services/api";
import { PipelineStage } from "../../services/organizationState";
import { getRole } from "../../services/auth";
import { openWebsite, browsableUrl } from "../../services/webLinks";
import { useTranslation } from "../../i18n/I18nContext";
import { PersonNotesLog } from "../../components/PersonNotesLog";
import { PersonStagePicker } from "../../components/PersonStagePicker";

export default function PersonDetailScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [person, setPerson] = useState<Person | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const router = useRouter();
  const [isAdmin, setIsAdmin] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(false);

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useEffect(() => {
    fetchPerson(Number(id))
      .then((loaded) => {
        setPerson(loaded);
        setLoadError(false);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, [id]);

  function confirmDelete() {
    Alert.alert(t("personDetail.deleteConfirm"), undefined, [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("personDetail.delete"),
        style: "destructive",
        onPress: async () => {
          setDeleting(true);
          setDeleteError(false);
          try {
            await deletePerson(Number(id));
            if (router.canGoBack()) router.back();
            else router.replace("/people");
          } catch {
            setDeleteError(true);
            setDeleting(false);
          }
        },
      },
    ]);
  }

  async function saveStage(stage: PipelineStage | null) {
    const stored = await updatePersonStage(Number(id), stage);
    setPerson((current) => (current ? { ...current, pipeline_stage: stored.pipeline_stage } : current));
  }

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

      {isAdmin && (
        <PersonStagePicker
          key={`stage-${person.id}`}
          stage={person.pipeline_stage ?? null}
          organizationStage={person.company_pipeline_stage ?? null}
          onSave={saveStage}
        />
      )}

      <PersonNotesLog personId={person.id} />

      {isAdmin && (
        <View style={styles.section}>
          <TouchableOpacity
            style={[styles.deleteButton, deleting && styles.deleteButtonDisabled]}
            onPress={confirmDelete}
            disabled={deleting}
            accessibilityRole="button"
            accessibilityState={{ disabled: deleting, busy: deleting }}
          >
            <Text style={styles.deleteButtonText}>{t("personDetail.delete")}</Text>
          </TouchableOpacity>
          {deleteError && <Text style={styles.deleteError}>{t("personDetail.deleteFailed")}</Text>}
        </View>
      )}
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
  deleteButton: {
    borderColor: "#ff6b6b",
    borderWidth: 1,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
  },
  deleteButtonDisabled: { opacity: 0.5 },
  deleteButtonText: { color: "#ff6b6b", fontSize: 14, fontWeight: "700" },
  deleteError: { color: "#ff6b6b", fontSize: 13, marginTop: 8 },
});

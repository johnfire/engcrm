import { useState, useEffect, useCallback } from "react";
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
import { deletePerson, fetchPerson, Person, updatePersonStage, updatePersonValueRating } from "../../services/api";
import { PipelineStage } from "../../services/organizationState";
import { getRole } from "../../services/auth";
import { onChanged, personKey } from "../../services/refreshBus";
import { openWebsite, browsableUrl, linkedinLabel } from "../../services/webLinks";
import { useTranslation } from "../../i18n/I18nContext";
import { PersonNotesLog } from "../../components/PersonNotesLog";
import { PersonNextStep } from "../../components/PersonNextStep";
import { PersonalPrioritySelector } from "../../components/PersonalPrioritySelector";
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

  const load = useCallback(
    () =>
      fetchPerson(Number(id))
        .then((loaded) => {
          setPerson(loaded);
          setLoadError(false);
        })
        .catch(() => setLoadError(true))
        .finally(() => setLoading(false)),
    [id],
  );

  useEffect(() => {
    load();
    return onChanged(personKey(Number(id)), () => {
      load();
    });
  }, [id, load]);

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

  async function saveRating(rating: number | null) {
    const stored = await updatePersonValueRating(Number(id), rating);
    setPerson((current) => (current ? { ...current, value_rating: stored } : current));
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

      <PersonalPrioritySelector
        key={`rating-${person.id}`}
        kind="person"
        priority={person.value_rating ?? null}
        onSave={saveRating}
      />

      <PersonNextStep
        key={`next-${person.id}-${person.next_step ?? ""}-${person.next_step_date ?? ""}`}
        personId={person.id}
        step={person.next_step ?? null}
        date={person.next_step_date ?? null}
        canEdit={isAdmin}
        onSaved={(step, date) =>
          setPerson((current) => (current ? { ...current, next_step: step, next_step_date: date } : current))
        }
      />

      {!!linkedinLabel(person.linkedin_url) && (
        <TouchableOpacity
          style={styles.linkedinButton}
          accessibilityRole="link"
          accessibilityLabel={t("people.openLinkedin", { name: person.name })}
          onPress={() => openWebsite(person.linkedin_url)}
        >
          <Text style={styles.linkedinIn}>in</Text>
          <Text style={styles.linkedinText} numberOfLines={1}>
            {linkedinLabel(person.linkedin_url)} ↗
          </Text>
        </TouchableOpacity>
      )}

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
        <TouchableOpacity
          style={styles.logButton}
          onPress={() =>
            router.push({
              pathname: "/(drawer)/log-meeting",
              params: { kind: "person", id: String(person.id), name: person.name },
            })
          }
          accessibilityRole="button"
        >
          <Text style={styles.logButtonText}>{t("meeting.logButton")}</Text>
        </TouchableOpacity>
      )}

      {isAdmin && (
        <TouchableOpacity
          style={styles.secondaryButton}
          onPress={() => router.push({ pathname: "/(drawer)/edit-person", params: { id: String(person.id) } })}
          accessibilityRole="button"
        >
          <Text style={styles.secondaryButtonText}>{t("recordForm.edit")}</Text>
        </TouchableOpacity>
      )}

      {isAdmin && (
        <PersonStagePicker
          key={`stage-${person.id}-${person.pipeline_stage ?? "none"}`}
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
  linkedinButton: {
    alignItems: "center",
    alignSelf: "flex-start",
    borderColor: "#0a66c2",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    marginBottom: 8,
    marginTop: 2,
    maxWidth: "100%",
    minHeight: 44,
    paddingHorizontal: 12,
  },
  linkedinIn: {
    backgroundColor: "#0a66c2",
    borderRadius: 3,
    color: "#fff",
    fontSize: 12,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  linkedinText: { color: "#5aa9f0", flexShrink: 1, fontSize: 14 },
  logButton: {
    alignItems: "center",
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    marginTop: 16,
    minHeight: 48,
    justifyContent: "center",
  },
  logButtonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  secondaryButton: {
    alignItems: "center",
    borderColor: "#7c6fff",
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: 10,
    minHeight: 46,
  },
  secondaryButtonText: { color: "#b9b2ff", fontSize: 14, fontWeight: "600" },
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

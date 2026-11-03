import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Text, View } from "react-native";

import { deletePersonNote, fetchPersonNotes, PersonInteraction } from "../services/api";
import { onChanged, personKey } from "../services/refreshBus";
import { useTranslation } from "../i18n/I18nContext";
import { formatDayTime } from "../services/dates";
import { ActivityEntry } from "./ActivityEntry";

// A person's history: every logged activity, newest first, each deletable. New
// entries are written on the Log activity screen (one form for everything, as on
// the web); this list reloads when that screen saves.
export function PersonNotesLog({ personId }: { personId: number }) {
  const { t } = useTranslation();
  const [notes, setNotes] = useState<PersonInteraction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    return fetchPersonNotes(personId)
      .then((loaded) => {
        setNotes(loaded);
        setError(null);
      })
      .catch(() => setError(t("personDetail.notes.loadFailed")));
  }, [personId, t]);

  useEffect(() => {
    reload().finally(() => setLoading(false));
    return onChanged(personKey(personId), () => {
      reload();
    });
  }, [personId, reload]);

  function confirmDelete(note: PersonInteraction) {
    Alert.alert(t("personDetail.notes.deleteConfirm"), undefined, [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("personDetail.notes.delete"),
        style: "destructive",
        onPress: () => {
          setNotes((prev) => prev.filter((n) => n.id !== note.id));
          deletePersonNote(personId, note.id).catch(() => reload());
        },
      },
    ]);
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t("personDetail.notes.title")}</Text>
      {!!error && <Text style={styles.error}>{error}</Text>}
      {loading ? (
        <ActivityIndicator color="#7c6fff" style={{ marginTop: 16 }} />
      ) : notes.length === 0 ? (
        <Text style={styles.empty}>{t("personDetail.notes.empty")}</Text>
      ) : (
        notes.map((note) => (
          <ActivityEntry
            key={note.id}
            owner="person"
            entry={{
              when: formatDayTime(note.occurred_at),
              method: note.method,
              durationMinutes: note.duration_minutes,
              offer: note.offer,
              text: note.note,
              attitude: note.attitude,
              myRead: note.my_read,
            }}
            onDelete={() => confirmDelete(note)}
            deleteLabel={t("personDetail.notes.delete")}
          />
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 20 },
  title: {
    color: "#888",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    marginBottom: 8,
    textTransform: "uppercase",
  },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
  empty: { color: "#555", fontSize: 13, marginTop: 12 },
});

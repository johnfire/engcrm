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
import { fetchContact, ContactDetail } from "../../services/api";

export default function ContactDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [contact, setContact] = useState<ContactDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    fetchContact(Number(id))
      .then((loaded) => {
        setContact(loaded);
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
  if (!contact)
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>
          {loadError ? "Couldn't load — check your connection" : "Contact not found"}
        </Text>
      </View>
    );

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.name}>{contact.name}</Text>
      <Text style={styles.sub}>
        {contact.city}, {contact.country} · {contact.type}
      </Text>
      <View style={styles.statusRow}>
        <Text style={styles.statusBadge}>{contact.status}</Text>
        {contact.fit_score !== null && (
          <Text style={styles.score}>Score: {contact.fit_score}</Text>
        )}
      </View>

      {contact.email && (
        <TouchableOpacity
          onPress={() => Linking.openURL(`mailto:${contact.email}`)}
        >
          <Text style={styles.link}>{contact.email}</Text>
        </TouchableOpacity>
      )}
      {contact.website && (
        <TouchableOpacity onPress={() => Linking.openURL(contact.website!)}>
          <Text style={styles.link}>{contact.website}</Text>
        </TouchableOpacity>
      )}
      {contact.phone && <Text style={styles.field}>{contact.phone}</Text>}
      {contact.notes && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Notes</Text>
          <Text style={styles.fieldText}>{contact.notes}</Text>
        </View>
      )}

      {contact.interactions.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>History</Text>
          {contact.interactions.map((interaction, index) => (
            <View key={index} style={styles.interaction}>
              <Text style={styles.interactionType}>
                {[interaction.method, interaction.direction]
                  .filter(Boolean)
                  .join(" · ") || "Interaction"}
              </Text>
              <Text style={styles.interactionDate}>
                {new Date(interaction.interaction_date).toLocaleDateString()}
              </Text>
              {interaction.summary && (
                <Text style={styles.interactionNotes}>{interaction.summary}</Text>
              )}
              {interaction.outcome && (
                <Text style={styles.interactionOutcome}>{interaction.outcome}</Text>
              )}
            </View>
          ))}
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
  sub: { color: "#888", fontSize: 14, marginBottom: 12 },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 16,
  },
  statusBadge: {
    backgroundColor: "#7c6fff25",
    color: "#7c6fff",
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    fontSize: 12,
    fontWeight: "700",
  },
  score: { color: "#888", fontSize: 13 },
  link: {
    color: "#7c6fff",
    fontSize: 14,
    marginBottom: 8,
    textDecorationLine: "underline",
  },
  field: { color: "#ccc", fontSize: 14, marginBottom: 8 },
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
  interaction: {
    backgroundColor: "#1a1a2e",
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  interactionType: {
    color: "#7c6fff",
    fontSize: 12,
    fontWeight: "700",
    marginBottom: 2,
  },
  interactionDate: { color: "#666", fontSize: 11, marginBottom: 4 },
  interactionNotes: { color: "#aaa", fontSize: 13 },
  interactionOutcome: {
    color: "#7c6fff",
    fontSize: 12,
    fontWeight: "600",
    marginTop: 4,
  },
  empty: { color: "#555" },
});

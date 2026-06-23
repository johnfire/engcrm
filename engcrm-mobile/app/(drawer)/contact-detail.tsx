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

  useEffect(() => {
    fetchContact(Number(id))
      .then(setContact)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading)
    return (
      <View style={s.center}>
        <ActivityIndicator color="#7c6fff" />
      </View>
    );
  if (!contact)
    return (
      <View style={s.center}>
        <Text style={s.empty}>Contact not found</Text>
      </View>
    );

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>
      <Text style={s.name}>{contact.name}</Text>
      <Text style={s.sub}>
        {contact.city}, {contact.country} · {contact.type}
      </Text>
      <View style={s.statusRow}>
        <Text style={s.statusBadge}>{contact.status}</Text>
        {contact.fit_score !== null && (
          <Text style={s.score}>Score: {contact.fit_score}</Text>
        )}
      </View>

      {contact.email && (
        <TouchableOpacity
          onPress={() => Linking.openURL(`mailto:${contact.email}`)}
        >
          <Text style={s.link}>{contact.email}</Text>
        </TouchableOpacity>
      )}
      {contact.website && (
        <TouchableOpacity onPress={() => Linking.openURL(contact.website!)}>
          <Text style={s.link}>{contact.website}</Text>
        </TouchableOpacity>
      )}
      {contact.phone && <Text style={s.field}>{contact.phone}</Text>}
      {contact.notes && (
        <View style={s.section}>
          <Text style={s.sectionTitle}>Notes</Text>
          <Text style={s.fieldText}>{contact.notes}</Text>
        </View>
      )}

      {contact.interactions.length > 0 && (
        <View style={s.section}>
          <Text style={s.sectionTitle}>History</Text>
          {contact.interactions.map((interaction, i) => (
            <View key={i} style={s.interaction}>
              <Text style={s.interactionType}>
                {[interaction.method, interaction.direction]
                  .filter(Boolean)
                  .join(" · ") || "Interaction"}
              </Text>
              <Text style={s.interactionDate}>
                {new Date(interaction.interaction_date).toLocaleDateString()}
              </Text>
              {interaction.summary && (
                <Text style={s.interactionNotes}>{interaction.summary}</Text>
              )}
              {interaction.outcome && (
                <Text style={s.interactionOutcome}>{interaction.outcome}</Text>
              )}
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
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

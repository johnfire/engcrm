import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Organization } from "../services/api";

interface Props {
  item: Organization;
  onPress: (id: number) => void;
}

function scoreBadgeColor(score: number | null) {
  if (!score) return "#444";
  if (score >= 80) return "#22c55e";
  if (score >= 60) return "#eab308";
  return "#888";
}

export function OrganizationRow({ item, onPress }: Props) {
  const color = scoreBadgeColor(item.fit_score);
  return (
    <TouchableOpacity style={styles.row} onPress={() => onPress(item.id)}>
      <View style={styles.info}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.sub}>
          {item.city} · {item.type}
        </Text>
      </View>
      <View style={styles.badges}>
        {(item.personal_priority ?? null) !== null && (
          <View style={styles.priorityBadge}>
            <Text style={styles.priorityBadgeText}>P{item.personal_priority}</Text>
          </View>
        )}
        {item.fit_score !== null && (
          <View
            style={[
              styles.badge,
              { backgroundColor: color + "25", borderColor: color + "80" },
            ]}
          >
            <Text style={[styles.badgeText, { color }]}>{item.fit_score}</Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
  },
  info: { flex: 1 },
  badges: { alignItems: "center", flexDirection: "row", gap: 6 },
  name: { color: "#fff", fontSize: 14, fontWeight: "600", marginBottom: 2 },
  sub: { color: "#888", fontSize: 12 },
  badge: {
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1,
  },
  badgeText: { fontSize: 12, fontWeight: "700" },
  priorityBadge: {
    backgroundColor: "#7c6fff25",
    borderColor: "#7c6fff80",
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  priorityBadgeText: { color: "#aaa3ff", fontSize: 12, fontWeight: "700" },
});

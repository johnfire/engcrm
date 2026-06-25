import { View, Text, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { ResearchCity, ResearchLevel } from "../services/api";

/**
 * One city's scan-status row on the Research screen — the mobile equivalent of a
 * single row in the web Research table. Shows the city, its region, a chip per
 * scan level (green = complete, amber = partial, dim = not run), and the
 * emailed/contacts totals. Tapping a level chip reveals the same detail the web
 * page exposes as a hover tooltip (last run date, contacts found, emailed).
 *
 * Every field is treated as possibly missing so a malformed row renders a
 * placeholder instead of crashing the screen.
 */

function statusOf(scan: ResearchLevel["scan"]): "complete" | "partial" | "none" {
  if (scan && scan.complete) return "complete";
  if (scan) return "partial";
  return "none";
}

const SYMBOL = { complete: "●", partial: "◐", none: "○" } as const;

function levelDetail(entry: ResearchLevel): string {
  const scan = entry.scan;
  const lastRun = scan?.last_run_at ? scan.last_run_at.slice(0, 10) : "—";
  const found = scan?.contacts_found ?? 0;
  const emailedLine = entry.emailed > 0 ? `\n${entry.emailed} emailed` : "";
  if (scan && scan.complete) {
    return `Complete — last run ${lastRun}, ${found} found${emailedLine}`;
  }
  if (scan) {
    return `Partial — more to scan.\nLast run ${lastRun}, ${found} so far${emailedLine}`;
  }
  return "Not yet run";
}

export function ResearchCityCard({
  city,
  levels,
  levelLabels,
}: {
  city: ResearchCity;
  levels: number[];
  levelLabels: Record<string, string>;
}) {
  const byLevel = new Map<number, ResearchLevel>(
    (city.levels ?? []).map((entry) => [entry.level, entry]),
  );

  function showDetail(level: number, entry: ResearchLevel) {
    const label = levelLabels[String(level)] ?? "";
    Alert.alert(`L${level}${label ? ` — ${label}` : ""}`, levelDetail(entry));
  }

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <Text style={styles.city} numberOfLines={1}>
          {city.city || "—"}
        </Text>
        <Text style={styles.region} numberOfLines={1}>
          {city.region || city.country || "—"}
        </Text>
      </View>

      <View style={styles.chipRow}>
        {levels.map((level) => {
          const entry =
            byLevel.get(level) ?? ({ level, scan: null, emailed: 0 } as ResearchLevel);
          const status = statusOf(entry.scan);
          const chipStyle =
            status === "complete"
              ? styles.complete
              : status === "partial"
                ? styles.partial
                : styles.none;
          const textStyle =
            status === "complete"
              ? styles.completeText
              : status === "partial"
                ? styles.partialText
                : styles.noneText;
          return (
            <TouchableOpacity
              key={level}
              style={[styles.chip, chipStyle]}
              onPress={() => showDetail(level, entry)}
            >
              <Text style={[styles.chipText, textStyle]}>
                {SYMBOL[status]} {level}
              </Text>
              {entry.emailed > 0 && (
                <Text style={styles.emailedBadge}>{entry.emailed}</Text>
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerItem}>
          <Text style={styles.footerNum}>{city.emailed_total ?? 0}</Text> sent
        </Text>
        <Text style={styles.footerItem}>
          <Text style={styles.footerNum}>{city.total_contacts ?? 0}</Text> contacts
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: "#ffffff12",
  },
  head: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  city: { color: "#fff", fontSize: 16, fontWeight: "700", flex: 1 },
  region: { color: "#888", fontSize: 12, maxWidth: "45%", textAlign: "right" },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 12 },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 9,
    paddingVertical: 6,
    borderRadius: 8,
    minWidth: 44,
    justifyContent: "center",
  },
  chipText: { fontSize: 13, fontWeight: "700" },
  complete: { backgroundColor: "#173a27" },
  completeText: { color: "#6ee7a0" },
  partial: { backgroundColor: "#3a2f12" },
  partialText: { color: "#eab308" },
  none: { backgroundColor: "#ffffff0d" },
  noneText: { color: "#666" },
  emailedBadge: {
    color: "#b9adff",
    fontSize: 10,
    fontWeight: "700",
    marginLeft: 4,
  },
  footer: {
    flexDirection: "row",
    gap: 18,
    marginTop: 12,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: "#ffffff10",
  },
  footerItem: { color: "#888", fontSize: 12 },
  footerNum: { color: "#fff", fontWeight: "700" },
});

import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { ResearchCityCard } from "./ResearchCityCard";
import { ResearchOverview } from "../services/api";
import { useTranslation } from "../i18n/I18nContext";

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value ?? 0}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

type Props = {
  error: string | null;
  loading: boolean;
  overview: ResearchOverview | null;
};

export function ResearchOverviewPanel({ error, loading, overview }: Props) {
  const { t } = useTranslation();
  if (loading && !overview) return <ActivityIndicator color="#7c6fff" style={styles.loader} />;
  if (error) return <Text style={styles.statusError}>{error}</Text>;
  if (!overview) return null;
  const cities = overview.cities ?? [];
  return (
    <>
      <View style={styles.statsRow}>
        <Stat value={overview.total} label={t("researchOverview.cities")} />
        <Stat value={overview.level1_done} label={t("researchOverview.l1Done")} />
        <Stat value={overview.unscanned} label={t("researchOverview.unscanned")} />
        <Stat value={overview.totals?.emailed ?? 0} label={t("researchOverview.emailed")} />
      </View>
      {cities.length === 0 ? <Text style={styles.empty}>{t("researchOverview.empty")}</Text> : cities.map((city) => (
        <ResearchCityCard key={city.id ?? city.city} city={city} levels={overview.levels ?? []} levelLabels={overview.level_labels ?? {}} />
      ))}
      {cities.length > 0 && <Text style={styles.totalsLine}>{t("researchOverview.total")} <Text style={styles.totalsNum}>{overview.totals?.emailed ?? 0}</Text> {t("researchOverview.emailed")} · <Text style={styles.totalsNum}>{overview.totals?.organizations ?? 0}</Text> {t("researchOverview.organizations")}</Text>}
      <View style={styles.legend}>
        <Text style={styles.legendLine}>{t("researchOverview.legend")}</Text>
        {(overview.levels ?? []).map((level) => <Text key={level} style={styles.legendLabel}>L{level}: {overview.level_labels?.[String(level)] ?? "—"}</Text>)}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  loader: { marginVertical: 24 },
  statusError: { color: "#ef8a8a", fontSize: 14, marginVertical: 16 },
  statsRow: { flexDirection: "row", gap: 10, marginBottom: 16 },
  stat: { flex: 1, backgroundColor: "#1a1a2e", borderRadius: 10, paddingVertical: 12, alignItems: "center" },
  statValue: { color: "#fff", fontSize: 20, fontWeight: "700" },
  statLabel: { color: "#888", fontSize: 11, marginTop: 2 },
  empty: { color: "#777", textAlign: "center", marginVertical: 24, fontSize: 14 },
  totalsLine: { color: "#aaa", fontSize: 13, textAlign: "right", marginBottom: 12 },
  totalsNum: { color: "#fff", fontWeight: "700" },
  legend: { marginTop: 8 }, legendLine: { color: "#888", fontSize: 12, marginBottom: 8 },
  legendLabel: { color: "#666", fontSize: 11, lineHeight: 17 },
});

import { useCallback, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useFocusEffect } from "expo-router";
import {
  runPipelineStage,
  fetchResearchOverview,
  ResearchOverview,
} from "../../services/api";
import { ResearchCityCard } from "../../components/ResearchCityCard";

const LEVELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const COUNTRIES = [
  { code: "DE", label: "Germany" },
  { code: "AT", label: "Austria" },
];

// Per-city stages, in pipeline order. Followup + Run-all are rendered separately.
const STAGES = [
  { key: "research", label: "1 · Research" },
  { key: "scout", label: "2 · Scout" },
  { key: "enrichment", label: "3 · Enrich" },
];

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value ?? 0}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

export default function PipelineScreen() {
  const [city, setCity] = useState("");
  const [level, setLevel] = useState(1);
  const [country, setCountry] = useState("DE");
  const [busy, setBusy] = useState<string | null>(null);

  const [overview, setOverview] = useState<ResearchOverview | null>(null);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true);
    setOverviewError(null);
    try {
      setOverview(await fetchResearchOverview());
    } catch (caught: any) {
      setOverviewError(
        caught?.response
          ? `Couldn't load status (server error ${caught.response.status}).`
          : caught?.message || "Couldn't load research status.",
      );
    } finally {
      setLoadingOverview(false);
    }
  }, []);

  // Refresh the status table whenever the screen regains focus (e.g. after a
  // scan queued elsewhere finishes) and on pull-to-refresh.
  useFocusEffect(
    useCallback(() => {
      loadOverview();
    }, [loadOverview]),
  );

  async function run(stage: string, label: string, needsCity = true) {
    if (needsCity && !city.trim()) {
      Alert.alert("City required", "Enter a city first.");
      return;
    }
    setBusy(stage);
    try {
      await runPipelineStage(stage, { city: city.trim(), level, country });
      Alert.alert(
        "Queued",
        `${label} started${needsCity ? ` for ${city.trim()}` : ""}. Watch the Activity screen for progress.`,
      );
    } catch (error: any) {
      Alert.alert(
        "Couldn't start",
        error?.response
          ? `Server error (${error.response.status}).`
          : error?.message || "Try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  const disabled = busy !== null;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={loadingOverview}
          onRefresh={loadOverview}
          tintColor="#7c6fff"
        />
      }
    >
      <Text style={styles.sectionTitle}>Pipeline status</Text>
      {loadingOverview && !overview ? (
        <ActivityIndicator color="#7c6fff" style={{ marginVertical: 24 }} />
      ) : overviewError ? (
        <Text style={styles.statusError}>{overviewError}</Text>
      ) : overview ? (
        <>
          <View style={styles.statsRow}>
            <Stat value={overview.total} label="cities" />
            <Stat value={overview.level1_done} label="L1 done" />
            <Stat value={overview.unscanned} label="unscanned" />
            <Stat value={overview.totals?.emailed ?? 0} label="emailed" />
          </View>

          {(overview.cities ?? []).length === 0 ? (
            <Text style={styles.empty}>
              No cities yet. Run a stage below to start scanning.
            </Text>
          ) : (
            (overview.cities ?? []).map((city) => (
              <ResearchCityCard
                key={city.id ?? city.city}
                city={city}
                levels={overview.levels ?? []}
                levelLabels={overview.level_labels ?? {}}
              />
            ))
          )}

          {(overview.cities ?? []).length > 0 && (
            <Text style={styles.totalsLine}>
              Total: <Text style={styles.totalsNum}>{overview.totals?.emailed ?? 0}</Text>{" "}
              emailed · <Text style={styles.totalsNum}>{overview.totals?.contacts ?? 0}</Text>{" "}
              contacts
            </Text>
          )}

          <View style={styles.legend}>
            <Text style={styles.legendLine}>
              ● complete &nbsp; ◐ partial (more to scan) &nbsp; ○ not run
            </Text>
            {(overview.levels ?? []).map((level) => (
              <Text key={level} style={styles.legendLabel}>
                L{level}: {overview.level_labels?.[String(level)] ?? "—"}
              </Text>
            ))}
          </View>
        </>
      ) : null}

      <View style={styles.divider} />

      <Text style={styles.label}>City</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. München"
        placeholderTextColor="#555"
        value={city}
        onChangeText={setCity}
        autoCapitalize="words"
      />

      <Text style={styles.label}>Level</Text>
      <View style={styles.row}>
        {LEVELS.map((levelOption) => (
          <TouchableOpacity
            key={levelOption}
            style={[styles.levelBtn, level === levelOption && styles.levelBtnActive]}
            onPress={() => setLevel(levelOption)}
          >
            <Text
              style={[styles.levelText, level === levelOption && styles.levelTextActive]}
            >
              {levelOption}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.label}>Country</Text>
      <View style={styles.row}>
        {COUNTRIES.map((countryOption) => (
          <TouchableOpacity
            key={countryOption.code}
            style={[
              styles.countryBtn,
              country === countryOption.code && styles.levelBtnActive,
            ]}
            onPress={() => setCountry(countryOption.code)}
          >
            <Text
              style={[
                styles.levelText,
                country === countryOption.code && styles.levelTextActive,
              ]}
            >
              {countryOption.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.label}>Run a stage</Text>
      {STAGES.map((stage) => (
        <TouchableOpacity
          key={stage.key}
          style={[styles.stageBtn, busy === stage.key && styles.btnBusy]}
          onPress={() => run(stage.key, stage.label)}
          disabled={disabled}
        >
          {busy === stage.key ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.stageText}>{stage.label}</Text>
          )}
        </TouchableOpacity>
      ))}

      <TouchableOpacity
        style={[styles.allBtn, busy === "all" && styles.btnBusy]}
        onPress={() => run("all", "Full pipeline")}
        disabled={disabled}
      >
        {busy === "all" ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.allText}>▶ Run all (research → enrich)</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.stageBtn, busy === "outreach" && styles.btnBusy]}
        onPress={() => run("outreach", "Outreach")}
        disabled={disabled}
      >
        {busy === "outreach" ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.stageText}>Outreach (draft emails)</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.followupBtn, busy === "followup" && styles.btnBusy]}
        onPress={() => run("followup", "Followup", false)}
        disabled={disabled}
      >
        {busy === "followup" ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.followupText}>Run Followup (all cities)</Text>
        )}
      </TouchableOpacity>

      <Text style={styles.hint}>
        Each stage runs in the background and appears on the Activity screen.
        Stages build on each other — research finds leads, scout scores them,
        enrich fills in details, outreach drafts emails for approval.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  content: { padding: 24, paddingBottom: 48 },
  sectionTitle: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 14,
  },
  statusError: { color: "#ef8a8a", fontSize: 14, marginVertical: 16 },
  statsRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 16,
  },
  stat: {
    flex: 1,
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
  },
  statValue: { color: "#fff", fontSize: 20, fontWeight: "700" },
  statLabel: { color: "#888", fontSize: 11, marginTop: 2 },
  empty: { color: "#777", textAlign: "center", marginVertical: 24, fontSize: 14 },
  totalsLine: {
    color: "#aaa",
    fontSize: 13,
    textAlign: "right",
    marginBottom: 12,
  },
  totalsNum: { color: "#fff", fontWeight: "700" },
  legend: { marginTop: 8 },
  legendLine: { color: "#888", fontSize: 12, marginBottom: 8 },
  legendLabel: { color: "#666", fontSize: 11, lineHeight: 17 },
  divider: {
    height: 1,
    backgroundColor: "#ffffff14",
    marginVertical: 24,
  },
  label: {
    color: "#888",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: 10,
    marginTop: 20,
  },
  input: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    padding: 14,
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  row: { flexDirection: "row", gap: 10, flexWrap: "wrap" },
  levelBtn: {
    backgroundColor: "#ffffff10",
    borderRadius: 10,
    width: 48,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  levelBtnActive: { backgroundColor: "#7c6fff" },
  levelText: { color: "#888", fontSize: 16, fontWeight: "700" },
  levelTextActive: { color: "#fff" },
  countryBtn: {
    backgroundColor: "#ffffff10",
    borderRadius: 10,
    paddingHorizontal: 20,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  stageBtn: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginBottom: 10,
    borderWidth: 1,
    borderColor: "#7c6fff55",
  },
  stageText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  btnBusy: { opacity: 0.6 },
  allBtn: {
    backgroundColor: "#7c6fff",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 8,
  },
  allText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  followupBtn: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 10,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  followupText: { color: "#ccc", fontSize: 15, fontWeight: "600" },
  hint: {
    color: "#555",
    fontSize: 12,
    textAlign: "center",
    marginTop: 24,
    lineHeight: 18,
  },
});

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
import { useFocusEffect, useRouter } from "expo-router";
import {
  runPipelineStage,
  fetchResearchOverview,
  CityCandidate,
  ResearchOverview,
} from "../../services/api";
import { ResearchOverviewPanel } from "../../components/ResearchOverviewPanel";
import { useTranslation } from "../../i18n/I18nContext";

const LEVELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

// Per-city stages, in pipeline order. Followup + Run-all are rendered separately.
const STAGE_KEYS = [
  { key: "research", labelKey: "research.stageResearch" },
  { key: "scout", labelKey: "research.stageScout" },
  { key: "enrichment", labelKey: "research.stageEnrich" },
];

export default function PipelineScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const COUNTRIES = [
    { code: "DE", label: t("research.countryGermany") },
    { code: "AT", label: t("research.countryAustria") },
  ];
  const [city, setCity] = useState("");
  const [level, setLevel] = useState(1);
  const [country, setCountry] = useState("DE");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{
    stage: string;
    label: string;
    typed: string;
    candidates: CityCandidate[];
  } | null>(null);

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
          ? t("research.couldntLoadStatusServer", { status: caught.response.status })
          : caught?.message || t("research.couldntLoadStatus"),
      );
    } finally {
      setLoadingOverview(false);
    }
  }, [t]);

  // Refresh the status table whenever the screen regains focus (e.g. after a
  // scan queued elsewhere finishes) and on pull-to-refresh.
  useFocusEffect(
    useCallback(() => {
      loadOverview();
    }, [loadOverview]),
  );

  async function run(stage: string, label: string, needsCity = true, cityOverride?: string) {
    const chosen = (cityOverride ?? city).trim();
    if (needsCity && !chosen) {
      Alert.alert(t("research.cityRequiredTitle"), t("research.cityRequiredMessage"));
      return;
    }
    setBusy(stage);
    setConfirm(null);
    try {
      const result = await runPipelineStage(stage, {
        city: needsCity ? chosen : "",
        level,
        country,
        confirmed: cityOverride !== undefined,
      });
      if (result.status === "needs_confirmation") {
        setConfirm({ stage, label, typed: result.typed, candidates: result.candidates });
        return;
      }
      if (cityOverride !== undefined) setCity(chosen);
      Alert.alert(
        t("research.queuedTitle"),
        t("research.queuedMessage", { label, forCity: needsCity ? ` for ${chosen}` : "" }),
      );
    } catch (error: any) {
      Alert.alert(
        t("research.couldntStartTitle"),
        error?.response ? t("common.serverError", { status: error.response.status }) : error?.message || t("common.tryAgain"),
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
      <Text style={styles.sectionTitle}>{t("research.pipelineStatus")}</Text>
      <ResearchOverviewPanel error={overviewError} loading={loadingOverview} overview={overview} />

      <View style={styles.divider} />

      <TouchableOpacity
        style={styles.areaScanBtn}
        onPress={() => router.push("/(drawer)/area-scan")}
      >
        <Text style={styles.areaScanText}>{t("research.scanAnArea")}</Text>
      </TouchableOpacity>

      <View style={styles.divider} />

      <Text style={styles.label}>{t("research.city")}</Text>
      <TextInput
        style={styles.input}
        placeholder={t("research.cityPlaceholder")}
        placeholderTextColor="#555"
        value={city}
        onChangeText={(text) => {
          setCity(text);
          setConfirm(null);
        }}
        autoCapitalize="words"
      />

      {confirm && (
        <View style={styles.confirmBox} testID="city-confirm">
          <Text style={styles.confirmTitle}>
            {confirm.candidates.length
              ? t("research.confirmTitle", { typed: confirm.typed })
              : t("research.confirmNoMatch", { typed: confirm.typed })}
          </Text>
          {confirm.candidates.map((candidate) => (
            <TouchableOpacity
              key={`${candidate.name}-${candidate.state}`}
              style={styles.confirmBtn}
              onPress={() => run(confirm.stage, confirm.label, true, candidate.name)}
            >
              <Text style={styles.confirmBtnText}>
                {candidate.state ? `${candidate.name} · ${candidate.state}` : candidate.name}
              </Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity
            style={styles.confirmBtn}
            onPress={() => run(confirm.stage, confirm.label, true, confirm.typed)}
          >
            <Text style={styles.confirmBtnText}>{t("research.useAsTyped", { typed: confirm.typed })}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setConfirm(null)}>
            <Text style={styles.confirmCancel}>{t("common.cancel")}</Text>
          </TouchableOpacity>
        </View>
      )}

      <Text style={styles.label}>{t("research.level")}</Text>
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

      <Text style={styles.label}>{t("research.country")}</Text>
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

      <Text style={styles.label}>{t("research.runAStage")}</Text>
      {STAGE_KEYS.map((stage) => (
        <TouchableOpacity
          key={stage.key}
          style={[styles.stageBtn, busy === stage.key && styles.btnBusy]}
          onPress={() => run(stage.key, t(stage.labelKey))}
          disabled={disabled}
        >
          {busy === stage.key ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.stageText}>{t(stage.labelKey)}</Text>
          )}
        </TouchableOpacity>
      ))}

      <TouchableOpacity
        style={[styles.allBtn, busy === "all" && styles.btnBusy]}
        onPress={() => run("all", t("research.fullPipeline"))}
        disabled={disabled}
      >
        {busy === "all" ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.allText}>{t("research.runAll")}</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.stageBtn, busy === "outreach" && styles.btnBusy]}
        onPress={() => run("outreach", t("research.outreach"))}
        disabled={disabled}
      >
        {busy === "outreach" ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.stageText}>{t("research.outreachDraft")}</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.followupBtn, busy === "opportunity" && styles.btnBusy]}
        onPress={() => run("opportunity", t("research.opportunity"), false)}
        disabled={disabled}
      >
        {busy === "opportunity" ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.followupText}>{t("research.runOpportunityAllCities")}</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.followupBtn, busy === "followup" && styles.btnBusy]}
        onPress={() => run("followup", t("research.followup"), false)}
        disabled={disabled}
      >
        {busy === "followup" ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.followupText}>{t("research.runFollowupAllCities")}</Text>
        )}
      </TouchableOpacity>

      <Text style={styles.hint}>{t("research.hint")}</Text>
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
  divider: {
    height: 1,
    backgroundColor: "#ffffff14",
    marginVertical: 24,
  },
  areaScanBtn: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#7c6fff55",
  },
  areaScanText: { color: "#fff", fontSize: 16, fontWeight: "600" },
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
  confirmBox: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 14,
    marginTop: 12,
    borderWidth: 1,
    borderColor: "#7c6fff55",
    gap: 8,
  },
  confirmTitle: { color: "#fff", fontSize: 14, fontWeight: "600" },
  confirmBtn: {
    backgroundColor: "#ffffff10",
    borderRadius: 10,
    padding: 12,
  },
  confirmBtnText: { color: "#fff", fontSize: 15 },
  confirmCancel: { color: "#888", fontSize: 14, textAlign: "center", paddingTop: 4 },
  hint: {
    color: "#555",
    fontSize: 12,
    textAlign: "center",
    marginTop: 24,
    lineHeight: 18,
  },
});

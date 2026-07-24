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
import {
  fetchContact,
  runOpportunityAnalysis,
  ContactDetail,
  OpportunityAnalysis,
} from "../../services/api";
import { getRole } from "../../services/auth";
import { useTranslation } from "../../i18n/I18nContext";

export default function ContactDetailScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [contact, setContact] = useState<ContactDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [analysis, setAnalysis] = useState<OpportunityAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState(false);

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useEffect(() => {
    fetchContact(Number(id))
      .then((loaded) => {
        setContact(loaded);
        setAnalysis(loaded.opportunity_analysis);
        setLoadError(false);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleRunAnalysis() {
    setAnalyzing(true);
    setAnalysisError(false);
    try {
      setAnalysis(await runOpportunityAnalysis(Number(id)));
    } catch {
      setAnalysisError(true);
    } finally {
      setAnalyzing(false);
    }
  }

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
          {loadError ? t("contactDetail.couldntLoad") : t("contactDetail.notFound")}
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
          <Text style={styles.score}>{t("contactDetail.score", { score: contact.fit_score })}</Text>
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
          <Text style={styles.sectionTitle}>{t("common.notes")}</Text>
          <Text style={styles.fieldText}>{contact.notes}</Text>
        </View>
      )}

      <OpportunityAnalysisSection
        analysis={analysis}
        isAdmin={isAdmin}
        analyzing={analyzing}
        analysisError={analysisError}
        onRun={handleRunAnalysis}
      />

      {contact.interactions.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("contactDetail.history")}</Text>
          {contact.interactions.map((interaction, index) => (
            <View key={index} style={styles.interaction}>
              <Text style={styles.interactionType}>
                {[interaction.method, interaction.direction]
                  .filter(Boolean)
                  .join(" · ") || t("contactDetail.interaction")}
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

// The explainable opportunity assessment: scores, reasoning, recommended
// services, evidence, discovery questions, and the suggested first step —
// display parity with the web contact-detail page. Admins get a button to
// run (or re-run) the analysis; it's synchronous and can take a moment.
function OpportunityAnalysisSection({
  analysis,
  isAdmin,
  analyzing,
  analysisError,
  onRun,
}: {
  analysis: OpportunityAnalysis | null;
  isAdmin: boolean;
  analyzing: boolean;
  analysisError: boolean;
  onRun: () => void;
}) {
  const { t } = useTranslation();

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{t("contactDetail.opportunityAnalysis")}</Text>

      {analysis ? (
        <View style={styles.analysisCard}>
          {analysis.analysis_date && (
            <Text style={styles.analysisDate}>
              {t("contactDetail.analyzedOn")}{" "}
              {new Date(analysis.analysis_date).toLocaleDateString()}
            </Text>
          )}
          <View style={styles.scoreGrid}>
            <ScoreChip label={t("contactDetail.opportunityScore")} value={analysis.opportunity_score} />
            <ScoreChip label={t("contactDetail.confidenceScore")} value={analysis.confidence_score} />
            <ScoreChip label={t("contactDetail.outreachPriority")} value={analysis.priority_score} />
          </View>

          {!!analysis.fit_reasoning && (
            <Text style={styles.analysisBody}>{analysis.fit_reasoning}</Text>
          )}

          {analysis.recommended_services.length > 0 && (
            <View style={styles.analysisBlock}>
              <Text style={styles.analysisHeading}>
                {t("contactDetail.recommendedServices")}
              </Text>
              {analysis.recommended_services.map((service, index) => (
                <View key={index} style={styles.serviceCard}>
                  <Text style={styles.serviceName}>{service.service}</Text>
                  {!!service.outcome && (
                    <Text style={styles.serviceOutcome}>{service.outcome}</Text>
                  )}
                  {!!service.rationale && (
                    <Text style={styles.serviceRationale}>{service.rationale}</Text>
                  )}
                </View>
              ))}
            </View>
          )}

          {analysis.evidence.length > 0 && (
            <BulletBlock title={t("contactDetail.evidence")} items={analysis.evidence} />
          )}
          {analysis.discovery_questions.length > 0 && (
            <BulletBlock
              title={t("contactDetail.discoveryQuestions")}
              items={analysis.discovery_questions}
            />
          )}

          {!!analysis.suggested_approach && (
            <View style={styles.analysisBlock}>
              <Text style={styles.analysisHeading}>
                {t("contactDetail.suggestedApproach")}
              </Text>
              <Text style={styles.analysisBody}>{analysis.suggested_approach}</Text>
            </View>
          )}
        </View>
      ) : (
        <Text style={styles.analysisEmpty}>
          {t("contactDetail.noOpportunityAnalysis")}
        </Text>
      )}

      {isAdmin && (
        <>
          <Text style={styles.analysisHint}>
            {t("contactDetail.analyseThisContactHint")}
          </Text>
          <TouchableOpacity
            style={[styles.analyseButton, analyzing && styles.analyseButtonDisabled]}
            onPress={onRun}
            disabled={analyzing}
            accessibilityRole="button"
            accessibilityState={{ disabled: analyzing, busy: analyzing }}
          >
            {analyzing && <ActivityIndicator color="#fff" size="small" />}
            <Text style={styles.analyseButtonText}>
              {analyzing
                ? t("contactDetail.opportunityAnalysisWorking")
                : analysis
                  ? t("contactDetail.reRunOpportunityAnalysis")
                  : t("contactDetail.runOpportunityAnalysis")}
            </Text>
          </TouchableOpacity>
          {analysisError && (
            <Text style={styles.analysisErrorText}>
              {t("contactDetail.opportunityAnalysisFailed")}
            </Text>
          )}
        </>
      )}
    </View>
  );
}

function ScoreChip({ label, value }: { label: string; value: number | null }) {
  return (
    <View style={styles.scoreChip}>
      <Text style={styles.scoreChipLabel}>{label}</Text>
      <Text style={styles.scoreChipValue}>{value ?? "—"}/100</Text>
    </View>
  );
}

function BulletBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <View style={styles.analysisBlock}>
      <Text style={styles.analysisHeading}>{title}</Text>
      {items.map((item, index) => (
        <View key={index} style={styles.bulletRow}>
          <Text style={styles.bullet}>•</Text>
          <Text style={styles.bulletText}>{item}</Text>
        </View>
      ))}
    </View>
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

  // --- Opportunity analysis ---
  analysisCard: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    padding: 14,
    borderWidth: 1,
    borderColor: "#7c6fff30",
  },
  analysisDate: { color: "#666", fontSize: 11, marginBottom: 10 },
  scoreGrid: { flexDirection: "row", gap: 8, marginBottom: 12 },
  scoreChip: {
    flex: 1,
    backgroundColor: "#7c6fff15",
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 6,
    alignItems: "center",
  },
  scoreChipLabel: {
    color: "#9a90ff",
    fontSize: 10,
    fontWeight: "600",
    marginBottom: 4,
    textAlign: "center",
  },
  scoreChipValue: { color: "#fff", fontSize: 15, fontWeight: "700" },
  analysisBody: { color: "#ccc", fontSize: 14, lineHeight: 21 },
  analysisBlock: { marginTop: 14 },
  analysisHeading: {
    color: "#9a90ff",
    fontSize: 12,
    fontWeight: "700",
    marginBottom: 6,
  },
  serviceCard: {
    backgroundColor: "#0f0f23",
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
  },
  serviceName: { color: "#fff", fontSize: 14, fontWeight: "700", marginBottom: 2 },
  serviceOutcome: { color: "#ccc", fontSize: 13, lineHeight: 19 },
  serviceRationale: { color: "#888", fontSize: 12, marginTop: 4, lineHeight: 18 },
  bulletRow: { flexDirection: "row", marginBottom: 4, paddingRight: 4 },
  bullet: { color: "#7c6fff", fontSize: 14, marginRight: 8, lineHeight: 20 },
  bulletText: { color: "#ccc", fontSize: 13, lineHeight: 20, flex: 1 },
  analysisEmpty: { color: "#666", fontSize: 13, fontStyle: "italic" },
  analysisHint: { color: "#777", fontSize: 12, lineHeight: 18, marginTop: 14 },
  analyseButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 16,
    marginTop: 10,
  },
  analyseButtonDisabled: { backgroundColor: "#4b459a" },
  analyseButtonText: { color: "#fff", fontSize: 14, fontWeight: "700" },
  analysisErrorText: { color: "#ff6b6b", fontSize: 13, marginTop: 8 },
});

import { StyleSheet, Text, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { PIPELINE_STAGES, PipelineStage, stageLabelKey } from "../services/organizationState";

interface StageTone {
  backgroundColor: string;
  borderColor: string;
  color: string;
  borderStyle?: "solid" | "dashed";
}

const STAGE_TONES: Record<PipelineStage, StageTone> = {
  candidate: { backgroundColor: "#d1d5db20", borderColor: "#9ca3af", color: "#d1d5db" },
  suspect: { backgroundColor: "#7c6fff26", borderColor: "#7c6fff", color: "#aaa3ff" },
  nibble: { backgroundColor: "#2dd4bf20", borderColor: "#2dd4bf", color: "#5eead4" },
  prospect: { backgroundColor: "#2a2600", borderColor: "#ffeb3b", color: "#ffeb3b" },
  opportunity: { backgroundColor: "#f59e0b20", borderColor: "#f59e0b", color: "#fbbf24" },
  customer: { backgroundColor: "#22c55e20", borderColor: "#22c55e", color: "#4ade80" },
  not_now: {
    backgroundColor: "#94a3b812",
    borderColor: "#94a3b8",
    borderStyle: "dashed",
    color: "#cbd5e1",
  },
  not_in_pipeline: { backgroundColor: "#6b728018", borderColor: "#6b7280", color: "#cbd5e1" },
};

const UNKNOWN_STAGE_TONE: StageTone = {
  backgroundColor: "#6b728018",
  borderColor: "#6b7280",
  color: "#cbd5e1",
};

function isPipelineStage(stage: string): stage is PipelineStage {
  return (PIPELINE_STAGES as readonly string[]).includes(stage);
}

export function PipelineStageBadge({ stage, offer }: { stage: string; offer?: string }) {
  const { t } = useTranslation();
  const stageLabel = t(stageLabelKey(stage));
  const visibleLabel = offer ? `${offer} · ${stageLabel}` : stageLabel;
  const accessibleValue = offer ? `${offer}, ${stageLabel}` : stageLabel;
  const tone = isPipelineStage(stage) ? STAGE_TONES[stage] : UNKNOWN_STAGE_TONE;

  return (
    <View
      accessible
      accessibilityLabel={`${t("common.pipelineStage")}: ${accessibleValue}`}
      accessibilityRole="text"
      style={[styles.badge, tone]}
    >
      <Text style={[styles.label, { color: tone.color }]}>{visibleLabel}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: "flex-start",
    borderRadius: 7,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  label: { fontSize: 12, fontWeight: "700" },
});

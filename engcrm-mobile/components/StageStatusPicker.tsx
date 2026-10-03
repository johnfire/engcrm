import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import {
  OrganizationStatus,
  PIPELINE_STAGES,
  PipelineStage,
  STATUSES,
  TYPICAL_STATUSES_BY_STAGE,
  isTypicalPair,
  stageLabelKey,
  statusLabelKey,
} from "../services/organizationState";

export interface StageStatusChange {
  pipeline_stage?: PipelineStage;
  status?: OrganizationStatus;
}

interface Props {
  stage: PipelineStage;
  status: OrganizationStatus;
  /** Sends only what changed. Throw (reject) to signal failure; the picker reverts. */
  onSave: (change: StageStatusChange) => Promise<void>;
}

/** Status choices for a stage: the ones that normally go with it first. */
export function orderedStatuses(stage: PipelineStage): OrganizationStatus[] {
  const usual = TYPICAL_STATUSES_BY_STAGE[stage];
  return [...usual, ...STATUSES.filter((status) => !usual.includes(status))];
}

/**
 * Two rows of chips — where the organization is in the pipeline, and what is going
 * on with it — and one Save. Picking a different stage also picks the status that
 * normally goes with it (shown, and changeable), so a typical move is two taps:
 * the stage, then Save. An unusual pairing is allowed and only marked.
 */
export function StageStatusPicker({ stage, status, onSave }: Props) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState({ stage, status });
  const [draft, setDraft] = useState({ stage, status });
  const [isSaving, setIsSaving] = useState(false);
  const [hasError, setHasError] = useState(false);

  const changed = draft.stage !== saved.stage || draft.status !== saved.status;
  const unusual = !isTypicalPair(draft.stage, draft.status);

  function pickStage(next: PipelineStage) {
    if (next === draft.stage) return;
    // Keep the status if it still fits the new stage; otherwise offer the usual one.
    const keeps = TYPICAL_STATUSES_BY_STAGE[next].includes(draft.status);
    setDraft({ stage: next, status: keeps ? draft.status : TYPICAL_STATUSES_BY_STAGE[next][0] });
    setHasError(false);
  }

  function pickStatus(next: OrganizationStatus) {
    setDraft({ ...draft, status: next });
    setHasError(false);
  }

  async function save() {
    const change: StageStatusChange = {};
    if (draft.stage !== saved.stage) change.pipeline_stage = draft.stage;
    if (draft.status !== saved.status) change.status = draft.status;
    setIsSaving(true);
    setHasError(false);
    try {
      await onSave(change);
      setSaved(draft);
    } catch {
      setDraft(saved);
      setHasError(true);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t("stageStatus.title")}</Text>

      <Text style={styles.label}>{t("stageStatus.stage")}</Text>
      <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("stageStatus.stage")}>
        {PIPELINE_STAGES.map((value) => (
          <Chip
            key={value}
            label={t(stageLabelKey(value))}
            selected={draft.stage === value}
            disabled={isSaving}
            onPress={() => pickStage(value)}
          />
        ))}
      </View>

      <Text style={styles.label}>{t("stageStatus.status")}</Text>
      <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("stageStatus.status")}>
        {orderedStatuses(draft.stage).map((value) => (
          <Chip
            key={value}
            label={t(statusLabelKey(value))}
            selected={draft.status === value}
            usual={TYPICAL_STATUSES_BY_STAGE[draft.stage].includes(value)}
            disabled={isSaving}
            onPress={() => pickStatus(value)}
          />
        ))}
      </View>

      {unusual && (
        <Text style={styles.hint} accessibilityLiveRegion="polite">
          {t("stageStatus.unusual")}
        </Text>
      )}

      {(changed || isSaving) && (
        <TouchableOpacity
          style={[styles.save, isSaving && styles.saveDisabled]}
          onPress={save}
          disabled={isSaving}
          accessibilityRole="button"
          accessibilityState={{ disabled: isSaving, busy: isSaving }}
        >
          {isSaving ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.saveText}>{t("stageStatus.save")}</Text>
          )}
        </TouchableOpacity>
      )}
      {hasError && (
        <Text style={styles.error} accessibilityLiveRegion="assertive">
          {t("stageStatus.saveFailed")}
        </Text>
      )}
    </View>
  );
}

export function Chip({
  label,
  selected,
  usual,
  disabled,
  onPress,
}: {
  label: string;
  selected: boolean;
  usual?: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      style={[styles.choice, usual && styles.choiceUsual, selected && styles.choiceSelected]}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="radio"
      accessibilityLabel={label}
      accessibilityState={{ selected, disabled: !!disabled }}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: "#1a1a2e", borderRadius: 10, marginTop: 16, padding: 14 },
  title: { color: "#fff", fontSize: 13, fontWeight: "700" },
  label: {
    color: "#888",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
    marginTop: 12,
    textTransform: "uppercase",
  },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 8 },
  choice: {
    backgroundColor: "#ffffff10",
    borderColor: "#ffffff25",
    borderRadius: 16,
    borderWidth: 1,
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  choiceUsual: { borderColor: "#7c6fff88" },
  choiceSelected: { backgroundColor: "#7c6fff", borderColor: "#aaa3ff" },
  choiceText: { color: "#aaa", fontSize: 13, fontWeight: "600" },
  choiceTextSelected: { color: "#fff" },
  hint: { color: "#e0b050", fontSize: 12, marginTop: 10 },
  save: {
    alignItems: "center",
    backgroundColor: "#7c6fff",
    borderRadius: 10,
    marginTop: 14,
    minHeight: 44,
    justifyContent: "center",
  },
  saveDisabled: { opacity: 0.6 },
  saveText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
});

import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { PIPELINE_STAGES, PipelineStage, stageLabelKey } from "../services/organizationState";
import { Chip } from "./StageStatusPicker";

interface Props {
  stage: PipelineStage | null;
  /** Saves a stage (null clears it). Reject to signal failure; the picker reverts. */
  onSave: (stage: PipelineStage | null) => Promise<void>;
  /** The organization's own stage, shown beside it for context when the person is linked. */
  organizationStage?: PipelineStage | null;
}

/** A person's stage tag: one tap on a stage saves it. */
export function PersonStagePicker({ stage, onSave, organizationStage }: Props) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState<PipelineStage | null>(stage);
  const [isSaving, setIsSaving] = useState(false);
  const [hasError, setHasError] = useState(false);

  async function choose(next: PipelineStage | null) {
    if (next === current) return;
    const previous = current;
    setCurrent(next);
    setIsSaving(true);
    setHasError(false);
    try {
      await onSave(next);
    } catch {
      setCurrent(previous);
      setHasError(true);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t("personStage.title")}</Text>
      <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("personStage.title")}>
        {PIPELINE_STAGES.map((value) => (
          <Chip
            key={value}
            label={t(stageLabelKey(value))}
            selected={current === value}
            disabled={isSaving}
            onPress={() => choose(value)}
          />
        ))}
      </View>
      <TouchableOpacity
        onPress={() => choose(null)}
        disabled={isSaving || current === null}
        accessibilityRole="button"
        accessibilityState={{ disabled: isSaving || current === null }}
      >
        <Text style={[styles.clear, (isSaving || current === null) && styles.clearDisabled]}>
          {t("personStage.clear")}
        </Text>
      </TouchableOpacity>
      {!!organizationStage && (
        <Text style={styles.hint}>
          {t("personStage.organization", { stage: t(stageLabelKey(organizationStage)) })}
        </Text>
      )}
      {isSaving && (
        <View style={styles.status} accessibilityLiveRegion="polite">
          <ActivityIndicator color="#7c6fff" size="small" />
        </View>
      )}
      {hasError && (
        <Text style={styles.error} accessibilityLiveRegion="assertive">
          {t("personStage.saveFailed")}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: "#1a1a2e", borderRadius: 10, marginTop: 16, padding: 14 },
  title: { color: "#fff", fontSize: 13, fontWeight: "700" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 10 },
  clear: { color: "#aaa3ff", fontSize: 12, marginTop: 12 },
  clearDisabled: { color: "#555" },
  hint: { color: "#888", fontSize: 12, marginTop: 10 },
  status: { alignItems: "flex-start", marginTop: 8 },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
});

import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "../i18n/I18nContext";
import { PIPELINE_STAGES, PipelineStage, stageLabelKey } from "../services/organizationState";
import { Chip } from "./StageStatusPicker";

interface Props {
  stage: PipelineStage;
  disabled: boolean;
  onChange: (stage: PipelineStage) => void;
}

export function BusinessStagePicker({ stage, disabled, onChange }: Props) {
  const { t } = useTranslation();
  return <View style={styles.container}>
    <Text style={styles.label}>{t("businessForm.stage")}</Text>
    <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("businessForm.stage")}>
      {PIPELINE_STAGES.map((choice) => <Chip key={choice} label={t(stageLabelKey(choice))}
        selected={stage === choice} disabled={disabled} onPress={() => onChange(choice)} />)}
    </View>
  </View>;
}

const styles = StyleSheet.create({
  container: { marginTop: 16 },
  label: { color: "#fff", fontSize: 15, fontWeight: "600" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
});

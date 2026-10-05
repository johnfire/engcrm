import { useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { useTranslation } from "../i18n/I18nContext";

// The same private 1–5 rating serves organizations ("personal priority") and
// people ("my rating" of them as a contact); only the words differ. 1 is the best.
const VOCABULARY = {
  organization: {
    title: "personalPriority.title",
    hint: "personalPriority.privateHint",
    clear: "personalPriority.clear",
    labels: ["personalPriority.best", "personalPriority.high", "personalPriority.medium",
      "personalPriority.low", "personalPriority.notNow"],
  },
  person: {
    title: "contactValue.title",
    hint: "contactValue.privateHint",
    clear: "contactValue.clear",
    labels: ["contactValue.exceptional", "contactValue.high", "contactValue.medium",
      "contactValue.low", "contactValue.minimal"],
  },
};

interface Props {
  priority: number | null;
  onSave: (priority: number | null) => Promise<void>;
  kind?: keyof typeof VOCABULARY;
}

export function PersonalPrioritySelector({ priority, onSave, kind = "organization" }: Props) {
  const { t } = useTranslation();
  const words = VOCABULARY[kind];
  const PRIORITIES = words.labels.map((labelKey, index) => ({ value: index + 1, labelKey }));
  const [selectedPriority, setSelectedPriority] = useState(priority);
  const [isSaving, setIsSaving] = useState(false);
  const [hasSaveError, setHasSaveError] = useState(false);

  async function selectPriority(nextPriority: number | null) {
    const previousPriority = selectedPriority;
    setSelectedPriority(nextPriority);
    setIsSaving(true);
    setHasSaveError(false);
    try {
      await onSave(nextPriority);
    } catch {
      setSelectedPriority(previousPriority);
      setHasSaveError(true);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t(words.title)}</Text>
      <Text style={styles.hint}>{t(words.hint)}</Text>
      <View
        style={styles.choices}
        accessibilityRole="radiogroup"
        accessibilityLabel={t(words.title)}
      >
        {PRIORITIES.map(({ value, labelKey }) => {
          const isSelected = selectedPriority === value;
          return (
            <TouchableOpacity
              key={value}
              style={[styles.choice, isSelected && styles.choiceSelected]}
              onPress={() => selectPriority(value)}
              disabled={isSaving}
              accessibilityRole="radio"
              accessibilityLabel={`${value} ${t(labelKey)}`}
              accessibilityState={{
                selected: isSelected,
                disabled: isSaving,
                busy: isSaving,
              }}
            >
              <Text style={[styles.choiceText, isSelected && styles.choiceTextSelected]}>
                {value} {t(labelKey)}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <TouchableOpacity
        onPress={() => selectPriority(null)}
        disabled={isSaving || selectedPriority === null}
        accessibilityRole="button"
        accessibilityState={{ disabled: isSaving || selectedPriority === null }}
      >
        <Text
          style={[
            styles.clear,
            (isSaving || selectedPriority === null) && styles.clearDisabled,
          ]}
        >
          {t(words.clear)}
        </Text>
      </TouchableOpacity>
      {isSaving && (
        <View style={styles.status} accessibilityLiveRegion="polite">
          <ActivityIndicator color="#7c6fff" size="small" />
          <Text style={styles.hint}>{t("personalPriority.saving")}</Text>
        </View>
      )}
      {hasSaveError && (
        <Text style={styles.error} accessibilityLiveRegion="assertive">
          {t("personalPriority.saveFailed")}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    marginTop: 16,
    padding: 14,
  },
  title: { color: "#fff", fontSize: 13, fontWeight: "700" },
  hint: { color: "#888", fontSize: 12, marginTop: 3 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 12 },
  choice: {
    backgroundColor: "#ffffff10",
    borderColor: "#ffffff25",
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  choiceSelected: { backgroundColor: "#7c6fff", borderColor: "#aaa3ff" },
  choiceText: { color: "#aaa", fontSize: 12, fontWeight: "600" },
  choiceTextSelected: { color: "#fff" },
  clear: { color: "#aaa3ff", fontSize: 12, marginTop: 12 },
  clearDisabled: { color: "#555" },
  status: { alignItems: "center", flexDirection: "row", gap: 7, marginTop: 8 },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
});

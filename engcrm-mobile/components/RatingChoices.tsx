import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { Tone, TONE_COLOURS } from "../services/ratingTones";

export type RatingChoice = {
  value: number;
  label: string; // shown on the chip
  accessibilityLabel: string;
  tone: Tone;
};

interface Props {
  choices: RatingChoice[];
  value: number | null;
  onSave: (value: number | null) => Promise<void>;
  groupLabel: string;
  clearLabelKey: string;
  savingKey: string;
  saveFailedKey: string;
}

/**
 * One private rating as a row of coloured chips plus "Clear": shows the pick at once,
 * saves it, and puts the old one back (and says so) if the save fails. The priority,
 * my rating of a person, and each of the two value ratings are all one of these.
 */
export function RatingChoices({
  choices,
  value,
  onSave,
  groupLabel,
  clearLabelKey,
  savingKey,
  saveFailedKey,
}: Props) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState(value);
  const [isSaving, setIsSaving] = useState(false);
  const [hasSaveError, setHasSaveError] = useState(false);

  async function select(next: number | null) {
    const previous = selected;
    setSelected(next);
    setIsSaving(true);
    setHasSaveError(false);
    try {
      await onSave(next);
    } catch {
      setSelected(previous);
      setHasSaveError(true);
    } finally {
      setIsSaving(false);
    }
  }

  const clearDisabled = isSaving || selected === null;
  return (
    <View>
      <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={groupLabel}>
        {choices.map((choice) => {
          const isSelected = selected === choice.value;
          const colours = TONE_COLOURS[choice.tone];
          return (
            <TouchableOpacity
              key={choice.value}
              style={[
                styles.choice,
                { borderColor: colours.line },
                isSelected && { backgroundColor: colours.fill },
              ]}
              onPress={() => select(choice.value)}
              disabled={isSaving}
              accessibilityRole="radio"
              accessibilityLabel={choice.accessibilityLabel}
              accessibilityState={{ selected: isSelected, disabled: isSaving, busy: isSaving }}
            >
              <Text style={[styles.choiceText, isSelected && { color: colours.text, fontWeight: "700" }]}>
                {choice.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <TouchableOpacity
        onPress={() => select(null)}
        disabled={clearDisabled}
        accessibilityRole="button"
        accessibilityState={{ disabled: clearDisabled }}
      >
        <Text style={[styles.clear, clearDisabled && styles.clearDisabled]}>{t(clearLabelKey)}</Text>
      </TouchableOpacity>
      {isSaving && (
        <View style={styles.status} accessibilityLiveRegion="polite">
          <ActivityIndicator color="#7c6fff" size="small" />
          <Text style={styles.hint}>{t(savingKey)}</Text>
        </View>
      )}
      {hasSaveError && (
        <Text style={styles.error} accessibilityLiveRegion="assertive">
          {t(saveFailedKey)}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 10 },
  choice: {
    backgroundColor: "#ffffff10",
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  choiceText: { color: "#ccc", fontSize: 12, fontWeight: "600" },
  clear: { color: "#aaa3ff", fontSize: 12, marginTop: 10 },
  clearDisabled: { color: "#555" },
  hint: { color: "#888", fontSize: 12 },
  status: { alignItems: "center", flexDirection: "row", gap: 7, marginTop: 8 },
  error: { color: "#ef8a8a", fontSize: 12, marginTop: 8 },
});

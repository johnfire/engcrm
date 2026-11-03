import { StyleSheet, Text, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { PRIORITY_TONE } from "../services/ratingTones";
import { RatingChoices } from "./RatingChoices";

// The same private rating serves organizations ("personal priority", 1–6) and people
// ("my rating" of them as a contact, 1–5); only the words differ. 1 is the best.
const VOCABULARY = {
  organization: {
    title: "personalPriority.title",
    hint: "personalPriority.privateHint",
    clear: "personalPriority.clear",
    labels: ["personalPriority.best", "personalPriority.high", "personalPriority.medium",
      "personalPriority.low", "personalPriority.notNow", "personalPriority.forgetIt"],
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
  const choices = words.labels.map((labelKey, index) => {
    const value = index + 1;
    const label = `${value} ${t(labelKey)}`;
    return { value, label, accessibilityLabel: label, tone: PRIORITY_TONE[value] };
  });

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t(words.title)}</Text>
      <Text style={styles.hint}>{t(words.hint)}</Text>
      <RatingChoices
        choices={choices}
        value={priority}
        onSave={onSave}
        groupLabel={t(words.title)}
        clearLabelKey={words.clear}
        savingKey="personalPriority.saving"
        saveFailedKey="personalPriority.saveFailed"
      />
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
});

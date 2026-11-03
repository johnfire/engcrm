import { StyleSheet, Text, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { ValueHorizon } from "../services/api";
import { VALUE_TONE } from "../services/ratingTones";
import { RatingChoices } from "./RatingChoices";

const ROWS: { horizon: ValueHorizon; titleKey: string }[] = [
  { horizon: "short-term", titleKey: "valueRating.shortTerm" },
  { horizon: "long-term", titleKey: "valueRating.longTerm" },
];

interface Props {
  shortTerm: number | null;
  longTerm: number | null;
  onSave: (horizon: ValueHorizon, value: number | null) => Promise<void>;
}

/** My private short- and long-term value of an organization or person: High, Medium, Low, Zero. */
export function ValueRatings({ shortTerm, longTerm, onSave }: Props) {
  const { t } = useTranslation();
  const current = { "short-term": shortTerm, "long-term": longTerm };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{t("valueRating.title")}</Text>
      <Text style={styles.hint}>{t("valueRating.privateHint")}</Text>
      {ROWS.map(({ horizon, titleKey }) => {
        const rowTitle = t(titleKey);
        const choices = [3, 2, 1, 0].map((value) => ({
          value,
          label: t(`valueRating.level${value}`),
          accessibilityLabel: `${rowTitle}: ${t(`valueRating.level${value}`)}`,
          tone: VALUE_TONE[value],
        }));
        return (
          <View key={horizon} style={styles.row}>
            <Text style={styles.rowTitle}>{rowTitle}</Text>
            <RatingChoices
              choices={choices}
              value={current[horizon]}
              onSave={(value) => onSave(horizon, value)}
              groupLabel={rowTitle}
              clearLabelKey="valueRating.clear"
              savingKey="valueRating.saving"
              saveFailedKey="valueRating.saveFailed"
            />
          </View>
        );
      })}
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
  row: { marginTop: 14 },
  rowTitle: { color: "#ccc", fontSize: 12, fontWeight: "600" },
});

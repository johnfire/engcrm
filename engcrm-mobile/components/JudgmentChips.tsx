import { StyleSheet, Text, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { toggled } from "../services/judgments";
import { Chip } from "./StageStatusPicker";

/** One judgment (their attitude, or my read of them): any number of chips. */
export function JudgmentChips<T extends string>({
  labelKey,
  valuePrefix,
  values,
  picked,
  onChange,
  disabled,
}: {
  labelKey: string;
  valuePrefix: string; // i18n prefix for each value's label, e.g. "myRead."
  values: readonly T[];
  picked: T[];
  onChange: (next: T[]) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <View style={styles.block}>
      <Text style={styles.label}>{t(labelKey)}</Text>
      <View style={styles.choices} accessibilityLabel={t(labelKey)}>
        {values.map((value) => (
          <Chip
            key={value}
            role="checkbox"
            label={t(valuePrefix + value)}
            selected={picked.includes(value)}
            disabled={disabled}
            onPress={() => onChange(toggled(picked, value, values))}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  block: { marginTop: 18 },
  label: { color: "#888", fontSize: 11, fontWeight: "700", letterSpacing: 1, marginBottom: 8, textTransform: "uppercase" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
});

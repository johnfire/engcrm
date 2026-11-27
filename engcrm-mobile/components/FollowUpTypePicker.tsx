// Commitment (someone expects something from me) or check-in (I plan to get back in
// touch). Every new next step or promise needs one: without it the server keeps it in
// Review, off the Follow-ups list.
import { StyleProp, StyleSheet, View, ViewStyle } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { FOLLOW_UP_TYPES, type FollowUpType } from "../services/followUps";
import { Chip } from "./StageStatusPicker";

type Props = {
  value: FollowUpType | null;
  onChange: (type: FollowUpType) => void;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function FollowUpTypePicker({ value, onChange, disabled, style }: Props) {
  const { t } = useTranslation();
  return (
    <View style={[styles.choices, style]} accessibilityRole="radiogroup" accessibilityLabel={t("followUp.type")}>
      {FOLLOW_UP_TYPES.map((type) => (
        <Chip key={type} label={t(`followUp.${type}`)} selected={value === type} disabled={disabled}
          onPress={() => onChange(type)} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
});

// Pick one offer: whose pipeline a new organization or person goes into, or what
// a logged note was about (with "General" for a note about nothing in particular).
import { StyleSheet, Text, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { GENERAL, Offer } from "../services/deals";
import { Chip } from "./StageStatusPicker";

export function OfferPicker({ offers, value, onChange, label, withGeneral = false, disabled = false }: {
  offers: Offer[];
  value: string;
  onChange: (slug: string) => void;
  label: string;
  withGeneral?: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  if (!offers.length) return null; // offline: the server applies its own default
  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={label}>
        {withGeneral && (
          <Chip label={t("logOffer.general")} selected={value === GENERAL} disabled={disabled} onPress={() => onChange(GENERAL)} />
        )}
        {offers.map((offer) => (
          <Chip key={offer.slug} label={offer.name} selected={value === offer.slug} disabled={disabled}
            onPress={() => onChange(offer.slug)} />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 16 },
  label: { color: "#fff", fontSize: 15, fontWeight: "600" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
});

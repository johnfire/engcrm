// A list row's deals: each offer's stage, named by its offer when the list shows
// every offer (one offer's list needs no name).
import { StyleSheet, Text, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { DealChip } from "../services/deals";
import { stageLabelKey } from "../services/organizationState";

export function DealChips({ deals, showOffer }: { deals: DealChip[] | undefined; showOffer: boolean }) {
  const { t } = useTranslation();
  if (!deals?.length) return null;
  return (
    <View style={styles.row}>
      {deals.map((deal) => (
        <Text key={deal.id} style={styles.chip}>
          {showOffer ? `${deal.offer}: ` : ""}
          {t(stageLabelKey(deal.stage))}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  chip: { color: "#b9adff", fontSize: 12, fontWeight: "600" },
});

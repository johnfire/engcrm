// A list row's deals: each offer's stage, named by its offer when the list shows
// every offer (one offer's list needs no name).
import { StyleSheet, View } from "react-native";

import { DealChip } from "../services/deals";
import { PipelineStageBadge } from "./pipeline-stage-badge";

export function DealChips({ deals, showOffer, fallbackStage }: {
  deals: DealChip[] | undefined;
  showOffer: boolean;
  fallbackStage?: string | null;
}) {
  if (!deals?.length) {
    if (!fallbackStage) return null;
    return (
      <View style={styles.row}>
        <PipelineStageBadge stage={fallbackStage} />
      </View>
    );
  }
  return (
    <View style={styles.row}>
      {deals.map((deal) => (
        <PipelineStageBadge key={deal.id} stage={deal.stage} offer={showOffer ? deal.offer : undefined} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
});

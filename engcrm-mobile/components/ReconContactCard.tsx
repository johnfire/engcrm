import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { ReconContact } from "../services/api";
import { useTranslation } from "../i18n/I18nContext";

function formatDistance(meters: number): string {
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`;
}

type Props = { contact: ReconContact; onCall: () => void; onNavigate: () => void; onScan: () => void };

export function ReconContactCard({ contact, onCall, onNavigate, onScan }: Props) {
  const { t } = useTranslation();
  const meta = [contact.type, contact.city].filter(Boolean).join(" · ");
  return <View style={styles.row}>
    <View style={styles.rowHead}><Text style={styles.name}>{contact.name}</Text><Text style={styles.distance}>{formatDistance(contact.distance_m)}</Text></View>
    <View style={styles.metaRow}>
      {!!meta && <Text style={styles.meta}>{meta}</Text>}
      {contact.rating != null && <Text style={styles.rating}>★ {contact.rating}</Text>}
      {contact.fit_score != null && <Text style={styles.fit}>{t("recon.fitScore", { score: contact.fit_score })}</Text>}
      {!!contact.status && <Text style={styles.status}>{contact.status}</Text>}
    </View>
    <View style={styles.actions}>
      <Button label={t("recon.call")} onPress={onCall} /><Button label={t("recon.navigate")} onPress={onNavigate} /><Button label={t("recon.scanCard")} onPress={onScan} />
    </View>
  </View>;
}

function Button({ label, onPress }: { label: string; onPress: () => void }) {
  return <TouchableOpacity style={styles.action} onPress={onPress}><Text style={styles.actionText}>{label}</Text></TouchableOpacity>;
}

const styles = StyleSheet.create({
  row: { backgroundColor: "#1a1a2e", borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: "#ffffff12" },
  rowHead: { flexDirection: "row", justifyContent: "space-between", gap: 8 }, name: { color: "#fff", fontSize: 16, fontWeight: "600", flex: 1 }, distance: { color: "#b9adff", fontSize: 13, fontWeight: "600" },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 5, flexWrap: "wrap" }, meta: { color: "#888", fontSize: 12 }, rating: { color: "#f0c040", fontSize: 12 },
  fit: { color: "#aaa", fontSize: 12, backgroundColor: "#ffffff10", paddingHorizontal: 7, borderRadius: 10 }, status: { color: "#777", fontSize: 12 },
  actions: { flexDirection: "row", gap: 8, marginTop: 12 }, action: { flex: 1, paddingVertical: 9, borderRadius: 8, alignItems: "center", borderWidth: 1, borderColor: "#7c6fff55" }, actionText: { color: "#fff", fontSize: 13, fontWeight: "600" },
});

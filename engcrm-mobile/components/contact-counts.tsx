import { useCallback, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { useTranslation } from "../i18n/I18nContext";
import { ContactCounts, fetchContactCounts } from "../services/contact-feed";

// People and organizations actually contacted: this month, and since the business began.
// A failed load just hides the strip — the contact list below must keep working.
export function ContactCountsStrip() {
  const { t } = useTranslation();
  const [counts, setCounts] = useState<ContactCounts | null>(null);
  useFocusEffect(useCallback(() => {
    let active = true;
    fetchContactCounts().then((loaded) => { if (active) setCounts(loaded); }).catch(() => { if (active) setCounts(null); });
    return () => { active = false; };
  }, []));
  if (!counts) return null;
  const line = (totals: ContactCounts["month"]) =>
    `${t("contactFeed.countPeople", { count: totals.people })} · ${t("contactFeed.countOrganizations", { count: totals.organizations })}`;
  return (
    <View style={styles.box} accessibilityLabel={t("contactFeed.counts")}>
      <View style={styles.cell}>
        <Text style={styles.label}>{t("contactFeed.countMonth")}</Text>
        <Text style={styles.value}>{line(counts.month)}</Text>
      </View>
      <View style={styles.cell}>
        <Text style={styles.label}>{t("contactFeed.countSince", { date: counts.business_start })}</Text>
        <Text style={styles.value}>{line(counts.since_start)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { flexDirection: "row", gap: 12, paddingHorizontal: 16, paddingTop: 12 },
  cell: { flex: 1, backgroundColor: "#1a1a2e", borderRadius: 10, padding: 10 },
  label: { color: "#888", fontSize: 11 },
  value: { color: "#fff", fontSize: 14, fontWeight: "600", marginTop: 2 },
});

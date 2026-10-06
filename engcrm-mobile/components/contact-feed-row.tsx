import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { ContactEntry } from "../services/contact-feed";
import { stageLabelKey } from "../services/organizationState";
import { useTranslation } from "../i18n/I18nContext";

export function ContactFeedRow({ contact, onPress }: {
  contact: ContactEntry; onPress: () => void;
}) {
  const { t } = useTranslation();
  const subtitle = [contact.description, contact.company].filter(Boolean).join(" · ");
  const details = [contact.city, contact.email, contact.phone].filter(Boolean).join(" · ");
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} accessibilityRole="button"
      accessibilityLabel={`${t(`contactFeed.${contact.kind}`)}: ${contact.name}`}>
      <View style={styles.heading}>
        <Text style={styles.name}>{contact.name}</Text>
        <Text style={styles.kind}>{t(`contactFeed.${contact.kind}`)}</Text>
      </View>
      {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      {!!details && <Text style={styles.details}>{details}</Text>}
      <View style={styles.heading}>
        {!!contact.pipeline_stage && <Text style={styles.stage}>{t(stageLabelKey(contact.pipeline_stage))}</Text>}
        {!!contact.created_at && <Text style={styles.date}>{contact.created_at.slice(0, 10)}</Text>}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: { backgroundColor: "#1a1a2e", borderRadius: 12, padding: 16, marginBottom: 10 },
  heading: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  name: { color: "#fff", flex: 1, fontSize: 16, fontWeight: "600" },
  kind: { color: "#c5bdff", fontSize: 12, backgroundColor: "#302953", padding: 5, borderRadius: 6 },
  subtitle: { color: "#b9adff", fontSize: 13, marginTop: 4 },
  details: { color: "#bbb", fontSize: 12, marginTop: 6 },
  stage: { color: "#b9adff", fontSize: 12, marginTop: 6 },
  date: { color: "#bbb", fontSize: 12, marginTop: 6, marginLeft: "auto" },
});

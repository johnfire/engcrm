import { useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { ContactPerson } from "../services/contact-feed";
import { useTranslation } from "../i18n/I18nContext";
import { ContactDateLink } from "./contact-date-link";

export function ContactGroupPeople({ people, canEdit }: { people: ContactPerson[]; canEdit: boolean }) {
  const [isExpanded, setExpanded] = useState(false);
  const { t } = useTranslation();
  const router = useRouter();
  if (!people.length) return null;
  return <View style={styles.group}>
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ expanded: isExpanded }}
      style={styles.toggle} onPress={() => setExpanded(!isExpanded)}>
      <Text style={styles.link}>{t("contactFeed.people", { count: people.length })} {isExpanded ? "▴" : "▾"}</Text>
    </TouchableOpacity>
    {isExpanded && people.map((person) => <View key={person.id} style={styles.person}>
      <TouchableOpacity accessibilityRole="button" accessibilityLabel={`${t("contactFeed.person")}: ${person.name}`}
        onPress={() => router.push({ pathname: "/(drawer)/person-detail", params: { id: String(person.id) } })}>
        <Text style={styles.link}>{person.name}</Text>
        {!!person.description && <Text style={styles.details}>{person.description}</Text>}
        <Text style={styles.details}>{[person.email, person.phone].filter(Boolean).join(" · ")}</Text>
        <Text style={styles.details}>{t("contactFeed.last_contact")}: {person.last_contact}</Text>
      </TouchableOpacity>
      {canEdit && <ContactDateLink kind="person" id={person.id} />}
    </View>)}
  </View>;
}

const styles = StyleSheet.create({
  group: { marginTop: 8, borderTopWidth: 1, borderTopColor: "#403956" },
  toggle: { minHeight: 44, justifyContent: "center" },
  person: { paddingVertical: 8, paddingLeft: 12, borderLeftWidth: 2, borderLeftColor: "#8174bb" },
  link: { color: "#c5bdff", fontSize: 14 },
  details: { color: "#bbb", fontSize: 12, marginTop: 4 },
});

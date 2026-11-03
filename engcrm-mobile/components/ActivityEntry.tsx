import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { methodLabelKey } from "../services/activityTypes";
import { formatDay } from "../services/dates";

export type ActivityEntryData = {
  when: string; // already formatted
  method: string | null;
  durationMinutes?: number | null;
  offer?: string | null;
  direction?: string | null;
  text: string | null; // what happened
  attitude?: string[] | null;
  myRead?: string[] | null;
  materialsLeft?: string | null;
  outcome?: string | null;
  nextAction?: string | null;
  nextActionDate?: string | null;
};

interface Props {
  entry: ActivityEntryData;
  owner: "organization" | "person";
  /** Shown as a Delete link when given. */
  onDelete?: () => void;
  deleteLabel?: string;
}

/**
 * One logged activity, as the web's history tables show it: when, what kind · how long ·
 * which offer, what happened, their attitude and my read of them, materials left, and
 * (organizations) the outcome and what was agreed next. The same row on both screens.
 */
export function ActivityEntry({ entry, owner, onDelete, deleteLabel }: Props) {
  const { t } = useTranslation();
  const labelKey = methodLabelKey(entry.method, owner);
  const kind = [
    labelKey ? t(labelKey) : null,
    typeof entry.durationMinutes === "number" ? t("activity.minutes", { minutes: entry.durationMinutes }) : null,
    entry.offer || null,
    entry.direction || null,
  ].filter(Boolean).join(" · ");
  const judgments = [
    entry.attitude?.length
      ? `${t("judgment.attitude")}: ${entry.attitude.map((v) => t(`impression.${v}`)).join(", ")}`
      : null,
    entry.myRead?.length
      ? `${t("judgment.myRead")}: ${entry.myRead.map((v) => t(`myRead.${v}`)).join(", ")}`
      : null,
    entry.materialsLeft ? `${t("organizationBrief.materialsLeft")}: ${entry.materialsLeft}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <View style={styles.entry}>
      <View style={styles.head}>
        <Text style={styles.when}>{entry.when}</Text>
        {!!kind && <Text style={styles.kind}>{kind}</Text>}
        {onDelete && (
          <TouchableOpacity onPress={onDelete} accessibilityRole="button">
            <Text style={styles.delete}>{deleteLabel}</Text>
          </TouchableOpacity>
        )}
      </View>
      {!!entry.text && <Text style={styles.text}>{entry.text}</Text>}
      {!!judgments && <Text style={styles.details}>{judgments}</Text>}
      {!!entry.outcome && <Text style={styles.outcome}>{entry.outcome}</Text>}
      {(!!entry.nextAction || !!entry.nextActionDate) && (
        <Text style={styles.next}>
          {entry.nextActionDate
            ? t("meeting.followUpDue", { date: formatDay(entry.nextActionDate) })
            : ""}
          {entry.nextActionDate && entry.nextAction ? " — " : ""}
          {entry.nextAction ?? ""}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  entry: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    marginBottom: 8,
    padding: 12,
  },
  head: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 8 },
  when: { color: "#888", fontSize: 12 },
  kind: { color: "#b9b2ff", flexShrink: 1, fontSize: 12, fontWeight: "600" },
  delete: { color: "#ff6b6b", fontSize: 12, marginLeft: "auto" },
  text: { color: "#ddd", fontSize: 14, lineHeight: 20, marginTop: 6 },
  details: { color: "#999", fontSize: 12, marginTop: 4 },
  outcome: { color: "#aaa", fontSize: 12, fontStyle: "italic", marginTop: 4 },
  next: { color: "#e3c443", fontSize: 12, marginTop: 4 },
});

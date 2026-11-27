// What happens next on a deal: its open follow-ups (or, from an older server and
// offline, the one next step) and — for an admin — an editor that only ever adds one
// (words, type, a quick "when") and "Done" for the earliest. Every change is also
// written to the owner's log on the server, so the log below refreshes too.
import { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from "react-native";
import { setPersonNextStep } from "../services/api";
import { FOLLOW_UPS, dateInDays, followUpDate, type FollowUpType } from "../services/followUps";
import { notifyChanged, personKey } from "../services/refreshBus";
import { useTranslation } from "../i18n/I18nContext";
import type { FollowUp } from "../services/deals";
import { Chip } from "./StageStatusPicker";
import { FollowUpTypePicker } from "./FollowUpTypePicker";
import { formatDay } from "../services/dates";

type Saved = { next_step: string | null; next_step_date: string | null };

type Props = {
  personId?: number;
  step: string | null;
  date: string | null;
  canEdit: boolean;
  onSaved: (step: string | null, date: string | null) => void;
  /** Where the step is stored. Defaults to the person's Consulting deal; a deal
   *  card passes its own deal's. A blank step marks the earliest done (type null). */
  save?: (step: string | null, date: string | null, type: FollowUpType | null) => Promise<Saved>;
  /** The deal's open follow-ups, earliest first; without any, `step` and `date` show. */
  followUps?: FollowUp[];
  /** False where "Done" could complete something other than what is shown. */
  canComplete?: boolean;
};

export function PersonNextStep({ personId, step, date, canEdit, onSaved, save: store, followUps = [],
  canComplete = true }: Props) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [when, setWhen] = useState("none");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [type, setType] = useState<FollowUpType | null>(null);
  const [typeMissing, setTypeMissing] = useState(false);
  const shown = followUps.length
    ? followUps.map((item) => ({ key: String(item.id), text: item.task_text, date: item.due_date, type: item.task_type }))
    : step ? [{ key: "step", text: step, date, type: null }] : [];

  async function save(nextText: string, nextDate: string | null) {
    const next = nextText.trim() || null;
    // A new step needs its type; "Done" (blank words) needs none.
    if (next && !type) {
      setTypeMissing(true);
      return;
    }
    setSaving(true);
    setFailed(false);
    try {
      const write = store ?? ((s: string | null, d: string | null, chosen: FollowUpType | null) => {
        if (personId === undefined) throw new Error("A person identity is required");
        return chosen ? setPersonNextStep(personId, s, d, chosen) : setPersonNextStep(personId, s, d);
      });
      const stored = await write(next, next ? nextDate : null, next ? type : null);
      setType(null); // the next one is asked afresh
      setText("");
      setWhen("none");
      onSaved(stored.next_step, stored.next_step_date);
      if (personId !== undefined) notifyChanged(personKey(personId));
      setEditing(false);
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  const chosenDate = followUpDate(when);
  const blank = !text.trim();

  return (
    <View style={styles.box}>
      <Text style={styles.title}>{t("nextStep.title")}</Text>
      {shown.map((item, index) => {
        const overdue = !!item.date && item.date < dateInDays(0);
        const due = item.date
          ? `${t("nextStep.due", { date: formatDay(item.date) })}${overdue ? ` · ${t("nextStep.overdue")}` : ""}`
          : "";
        const detail = [item.type ? t(`followUp.${item.type}`) : "", due].filter(Boolean).join(" · ");
        return (
          <View key={item.key} style={index > 0 && styles.next}>
            <Text style={styles.step}>{item.text}</Text>
            {!!detail && <Text style={[styles.due, overdue && styles.overdue]}>{detail}</Text>}
            {index === 0 && canEdit && canComplete && !editing && (
              <TouchableOpacity accessibilityRole="button" onPress={() => save("", null)} disabled={saving}>
                <Text style={styles.action}>✓ {t("nextStep.done")}</Text>
              </TouchableOpacity>
            )}
          </View>
        );
      })}
      {shown.length === 0 && <Text style={styles.none}>{t("nextStep.none")}</Text>}

      {canEdit && !editing && (
        <View style={styles.actions}>
          <TouchableOpacity accessibilityRole="button" onPress={() => setEditing(true)} disabled={saving}>
            <Text style={styles.action}>{t("nextStep.add")}</Text>
          </TouchableOpacity>
        </View>
      )}

      {canEdit && editing && (
        <View style={styles.editor}>
          <TextInput
            style={styles.input}
            value={text}
            onChangeText={setText}
            placeholder={t("nextStep.placeholder")}
            placeholderTextColor="#666"
            maxLength={500}
            editable={!saving}
            accessibilityLabel={t("nextStep.label")}
          />
          {!blank && (
            <FollowUpTypePicker style={styles.type} value={type} disabled={saving}
              onChange={(chosen) => { setType(chosen); setTypeMissing(false); }} />
          )}
          <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("nextStep.dateLabel")}>
            {FOLLOW_UPS.map(({ id, labelKey }) => (
              <Chip key={id} label={t(labelKey)} selected={when === id} disabled={saving} onPress={() => setWhen(id)} />
            ))}
          </View>
          {!!chosenDate && <Text style={styles.due}>{t("nextStep.due", { date: formatDay(chosenDate) })}</Text>}
          <View style={styles.actions}>
            <TouchableOpacity
              accessibilityRole="button"
              style={[styles.saveButton, blank && styles.disabled]}
              onPress={() => { if (!blank) void save(text, chosenDate); }}
              disabled={saving || blank}
              accessibilityState={{ disabled: saving || blank }}
            >
              <Text style={styles.saveText}>{t("nextStep.save")}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityRole="button" disabled={saving}
              onPress={() => { setEditing(false); setTypeMissing(false); }}>
              <Text style={styles.action}>{t("common.cancel")}</Text>
            </TouchableOpacity>
          </View>
          {typeMissing && <Text style={styles.error}>{t("followUp.typeNeeded")}</Text>}
        </View>
      )}
      {failed && <Text style={styles.error}>{t("nextStep.saveFailed")}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { backgroundColor: "#1a1a2e", borderRadius: 10, padding: 14, marginTop: 16 },
  title: { color: "#888", fontSize: 11, fontWeight: "700", letterSpacing: 1, marginBottom: 6, textTransform: "uppercase" },
  step: { color: "#fff", fontSize: 15, fontWeight: "600" },
  none: { color: "#666", fontSize: 14 },
  due: { color: "#aaa", fontSize: 13, marginTop: 4 },
  overdue: { color: "#d98a3d", fontWeight: "700" },
  actions: { flexDirection: "row", alignItems: "center", columnGap: 18, marginTop: 10 },
  action: { color: "#7c6fff", fontSize: 14, fontWeight: "600", paddingVertical: 6 },
  editor: { marginTop: 10 },
  input: { backgroundColor: "#0f0f23", borderColor: "#333", borderWidth: 1, borderRadius: 8, color: "#fff", padding: 10 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 10 },
  type: { marginTop: 10 },
  saveButton: { backgroundColor: "#7c6fff", borderRadius: 8, paddingHorizontal: 16, paddingVertical: 9 },
  saveText: { color: "#fff", fontWeight: "700" },
  disabled: { opacity: 0.4 },
  next: { borderTopColor: "#ffffff15", borderTopWidth: 1, marginTop: 10, paddingTop: 10 },
  error: { color: "#ff6b6b", fontSize: 13, marginTop: 8 },
});

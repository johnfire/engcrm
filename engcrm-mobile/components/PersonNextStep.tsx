// What happens next with a person: the current step and its due date, and — for an
// admin — a small editor (words, a quick "when", Save, Done). Every change is also
// written to the person's note log on the server, so the log below refreshes too.
import { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from "react-native";
import { setPersonNextStep } from "../services/api";
import { FOLLOW_UPS, dateInDays, followUpDate } from "../services/followUps";
import { notifyChanged, personKey } from "../services/refreshBus";
import { useTranslation } from "../i18n/I18nContext";
import { Chip } from "./StageStatusPicker";

type Props = {
  personId: number;
  step: string | null;
  date: string | null;
  canEdit: boolean;
  onSaved: (step: string | null, date: string | null) => void;
};

export function PersonNextStep({ personId, step, date, canEdit, onSaved }: Props) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(step ?? "");
  const [when, setWhen] = useState(date ? "keep" : "none");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const overdue = !!date && date < dateInDays(0);

  async function save(nextText: string, nextDate: string | null) {
    setSaving(true);
    setFailed(false);
    try {
      const stored = await setPersonNextStep(personId, nextText.trim() || null, nextText.trim() ? nextDate : null);
      onSaved(stored.next_step, stored.next_step_date);
      notifyChanged(personKey(personId));
      setEditing(false);
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  const chosenDate = when === "keep" ? date : followUpDate(when);

  return (
    <View style={styles.box}>
      <Text style={styles.title}>{t("nextStep.title")}</Text>
      {step ? (
        <>
          <Text style={styles.step}>{step}</Text>
          {!!date && (
            <Text style={[styles.due, overdue && styles.overdue]}>
              {t("nextStep.due", { date })}
              {overdue ? ` · ${t("nextStep.overdue")}` : ""}
            </Text>
          )}
        </>
      ) : (
        <Text style={styles.none}>{t("nextStep.none")}</Text>
      )}

      {canEdit && !editing && (
        <View style={styles.actions}>
          <TouchableOpacity accessibilityRole="button" onPress={() => setEditing(true)} disabled={saving}>
            <Text style={styles.action}>{step ? t("nextStep.change") : t("nextStep.add")}</Text>
          </TouchableOpacity>
          {!!step && (
            <TouchableOpacity accessibilityRole="button" onPress={() => save("", null)} disabled={saving}>
              <Text style={styles.action}>✓ {t("nextStep.done")}</Text>
            </TouchableOpacity>
          )}
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
          <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("nextStep.dateLabel")}>
            {!!date && (
              <Chip label={t("nextStep.keepDate", { date })} selected={when === "keep"} onPress={() => setWhen("keep")} />
            )}
            {FOLLOW_UPS.map(({ id, labelKey }) => (
              <Chip key={id} label={t(labelKey)} selected={when === id} disabled={saving} onPress={() => setWhen(id)} />
            ))}
          </View>
          {!!chosenDate && <Text style={styles.due}>{t("nextStep.due", { date: chosenDate })}</Text>}
          <View style={styles.actions}>
            <TouchableOpacity
              accessibilityRole="button"
              style={styles.saveButton}
              onPress={() => save(text, chosenDate)}
              disabled={saving}
            >
              <Text style={styles.saveText}>{t("nextStep.save")}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityRole="button" onPress={() => setEditing(false)} disabled={saving}>
              <Text style={styles.action}>{t("common.cancel")}</Text>
            </TouchableOpacity>
          </View>
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
  saveButton: { backgroundColor: "#7c6fff", borderRadius: 8, paddingHorizontal: 16, paddingVertical: 9 },
  saveText: { color: "#fff", fontWeight: "700" },
  error: { color: "#ff6b6b", fontSize: 13, marginTop: 8 },
});

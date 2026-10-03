import { ReactNode, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

import { useTranslation } from "../i18n/I18nContext";

export interface FieldDef {
  key: string;
  labelKey: string;
  maxLength: number;
  keyboard?: "default" | "email-address" | "phone-pad" | "url";
  multiline?: boolean;
  required?: boolean;
  /** Typed in capitals (a two-letter country code). */
  capitals?: boolean;
}

export type Values = Record<string, string>;

/** The fields whose trimmed value differs from the baseline. */
export function changedFields(fields: FieldDef[], values: Values, baseline: Values): Values {
  const changed: Values = {};
  for (const { key } of fields) {
    const now = (values[key] ?? "").trim();
    if (now !== (baseline[key] ?? "").trim()) changed[key] = now;
  }
  return changed;
}

/** A translation key for what is wrong with one field's value, or null. The server
 *  checks the same things; checking here gives the message instantly and in the
 *  user's language. */
export function fieldProblem(field: FieldDef, raw: string): string | null {
  const value = raw.trim();
  if (field.required && !value) return "recordForm.required";
  if (field.key === "country" && value && !/^[A-Za-z]{2}$/.test(value)) return "recordForm.countryInvalid";
  if (field.keyboard === "email-address" && value && (!value.includes("@") || /\s/.test(value))) {
    return "recordForm.emailInvalid";
  }
  return null;
}

interface Props {
  fields: FieldDef[];
  /** What the record holds now; an edit sends only fields that differ from this. */
  baseline: Values;
  /** Starting text, when it should differ from the baseline (a name carried over from Search). */
  start?: Values;
  saving: boolean;
  submitLabel: string;
  error?: string | null;
  /** The form has changes that are not text fields (a switch beside the form). */
  extraChange?: boolean;
  onSubmit: (changed: Values) => void;
  children?: ReactNode;
}

/** The fields of one record plus a Save button. Saving is allowed only when
 *  something changed, and only after every field passes its own check. */
export function RecordForm({
  fields,
  baseline,
  start,
  saving,
  submitLabel,
  error,
  extraChange,
  onSubmit,
  children,
}: Props) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Values>({ ...baseline, ...start });
  const [problems, setProblems] = useState<Record<string, string>>({});

  const changed = changedFields(fields, values, baseline);
  const canSave = !saving && (Object.keys(changed).length > 0 || !!extraChange);

  function set(key: string, text: string) {
    setValues((previous) => ({ ...previous, [key]: text }));
    if (problems[key]) setProblems((previous) => ({ ...previous, [key]: "" }));
  }

  function submit() {
    const found: Record<string, string> = {};
    // Only what is being saved is checked: an untouched legacy value (a country
    // written out in full, say) must not block an unrelated edit.
    for (const field of fields) {
      if (!(field.key in changed) && !field.required) continue;
      const problem = fieldProblem(field, values[field.key] ?? "");
      if (problem) found[field.key] = problem;
    }
    setProblems(found);
    if (Object.keys(found).length > 0) return;
    onSubmit(changed);
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView style={styles.flex} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {fields.map((field) => (
          <View key={field.key} style={styles.field}>
            <Text style={styles.label}>
              {t(field.labelKey)}
              {field.required ? " *" : ""}
            </Text>
            <TextInput
              style={[styles.input, field.multiline && styles.multiline, !!problems[field.key] && styles.inputBad]}
              value={values[field.key] ?? ""}
              onChangeText={(text) => set(field.key, text)}
              maxLength={field.maxLength}
              editable={!saving}
              multiline={field.multiline}
              keyboardType={field.keyboard ?? "default"}
              autoCapitalize={field.capitals ? "characters" : field.keyboard && field.keyboard !== "default" ? "none" : "sentences"}
              autoCorrect={false}
              placeholderTextColor="#555"
              accessibilityLabel={t(field.labelKey)}
            />
            {!!problems[field.key] && <Text style={styles.problem}>{t(problems[field.key])}</Text>}
          </View>
        ))}
        {children}
        {!!error && (
          <Text style={styles.error} accessibilityLiveRegion="assertive">
            {error}
          </Text>
        )}
      </ScrollView>
      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.save, !canSave && styles.saveDisabled]}
          onPress={submit}
          disabled={!canSave}
          accessibilityRole="button"
          accessibilityState={{ disabled: !canSave, busy: saving }}
        >
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{submitLabel}</Text>}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { padding: 20, paddingBottom: 30 },
  field: { marginBottom: 14 },
  label: { color: "#888", fontSize: 12, marginBottom: 4, marginLeft: 2 },
  input: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff20",
    borderRadius: 10,
    borderWidth: 1,
    color: "#fff",
    fontSize: 16,
    minHeight: 48,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  multiline: { minHeight: 110, textAlignVertical: "top" },
  inputBad: { borderColor: "#ef8a8a" },
  problem: { color: "#ef8a8a", fontSize: 12, marginLeft: 2, marginTop: 4 },
  error: { color: "#ef8a8a", fontSize: 13, marginTop: 6 },
  footer: { backgroundColor: "#0f0f23", borderTopColor: "#ffffff15", borderTopWidth: 1, padding: 14 },
  save: { alignItems: "center", backgroundColor: "#7c6fff", borderRadius: 12, justifyContent: "center", minHeight: 54 },
  saveDisabled: { opacity: 0.4 },
  saveText: { color: "#fff", fontSize: 17, fontWeight: "700" },
});

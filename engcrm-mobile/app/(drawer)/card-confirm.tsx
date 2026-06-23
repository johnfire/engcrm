import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { confirmCard, discardCard, CaptureResult, CardFields } from "../../services/api";

function Field({
  label,
  value,
  onChange,
  keyboardType,
  multiline,
}: {
  label: string;
  value?: string | null;
  onChange: (v: string) => void;
  keyboardType?: "default" | "email-address" | "phone-pad" | "url";
  multiline?: boolean;
}) {
  const noCaps = keyboardType === "email-address" || keyboardType === "url";
  return (
    <View style={s.field}>
      <Text style={s.label}>{label}</Text>
      <TextInput
        style={[s.input, multiline && s.inputMultiline]}
        value={value ?? ""}
        onChangeText={onChange}
        placeholderTextColor="#555"
        autoCapitalize={noCaps ? "none" : "sentences"}
        autoCorrect={false}
        keyboardType={keyboardType ?? "default"}
        multiline={multiline}
      />
    </View>
  );
}

export default function CardConfirmScreen() {
  const router = useRouter();
  const { data } = useLocalSearchParams<{ data: string }>();
  const capture: CaptureResult = JSON.parse(data || "{}");
  const dup = capture.dup_suggestion;

  const [fields, setFields] = useState<CardFields>(capture.fields || {});
  const [linkDup, setLinkDup] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = (k: keyof CardFields) => (v: string) => setFields((f) => ({ ...f, [k]: v }));

  async function save() {
    setSaving(true);
    try {
      await confirmCard(capture.capture_id, fields, linkDup && dup ? dup.id : null);
      Alert.alert(
        linkDup ? "Linked" : "Lead saved",
        "Enrichment is running in the background — you’ll get a notification when it’s ready.",
        [{ text: "OK", onPress: () => router.replace("/(drawer)/capture") }],
      );
    } catch (e: any) {
      Alert.alert("Couldn't save", String(e?.message || "Try again."));
    } finally {
      setSaving(false);
    }
  }

  async function discard() {
    try {
      await discardCard(capture.capture_id);
    } catch {
      // best-effort; the capture row stays pending if this fails
    }
    router.replace("/(drawer)/capture");
  }

  return (
    <KeyboardAvoidingView
      style={s.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        {dup && (
          <View style={s.dupBanner}>
            <Text style={s.dupTitle}>⚠ Possible duplicate</Text>
            <Text style={s.dupText}>
              {dup.name}
              {dup.city ? ` — ${dup.city}` : ""}
              {dup.email ? `\n${dup.email}` : ""}
            </Text>
            <View style={s.dupActions}>
              <TouchableOpacity
                style={[s.dupBtn, !linkDup && s.dupBtnActive]}
                onPress={() => setLinkDup(false)}
              >
                <Text style={[s.dupBtnText, !linkDup && s.dupBtnTextActive]}>Create new</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.dupBtn, linkDup && s.dupBtnActive]}
                onPress={() => setLinkDup(true)}
              >
                <Text style={[s.dupBtnText, linkDup && s.dupBtnTextActive]}>Link to existing</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {typeof capture.confidence === "number" && (
          <Text style={s.confidence}>Read confidence: {capture.confidence}%</Text>
        )}

        <Field label="Company" value={fields.company} onChange={set("company")} />
        <Field label="Name" value={fields.name} onChange={set("name")} />
        <Field label="Title" value={fields.title} onChange={set("title")} />
        <Field label="Email" value={fields.email} onChange={set("email")} keyboardType="email-address" />
        <Field label="Phone" value={fields.phone} onChange={set("phone")} keyboardType="phone-pad" />
        <Field label="Mobile" value={fields.mobile} onChange={set("mobile")} keyboardType="phone-pad" />
        <Field label="Website" value={fields.website} onChange={set("website")} keyboardType="url" />
        <Field label="Address" value={fields.address} onChange={set("address")} />
        <Field label="City" value={fields.city} onChange={set("city")} />
        <Field label="Country" value={fields.country} onChange={set("country")} />
        <Field label="Industry" value={fields.industry} onChange={set("industry")} />
        <Field label="Note" value={fields.note} onChange={set("note")} multiline />

        <TouchableOpacity style={s.save} onPress={save} disabled={saving}>
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={s.saveText}>{linkDup ? "Link to existing lead" : "Save lead"}</Text>
          )}
        </TouchableOpacity>
        <View style={s.row}>
          <TouchableOpacity style={s.retake} onPress={() => router.replace("/(drawer)/capture")}>
            <Text style={s.retakeText}>Retake</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.discardBtn} onPress={discard}>
            <Text style={s.discardText}>Discard</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" },
  content: { padding: 16, paddingBottom: 48 },
  dupBanner: {
    backgroundColor: "#3a2e10",
    borderColor: "#a07b1e",
    borderWidth: 1,
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
  },
  dupTitle: { color: "#f0c040", fontWeight: "700", marginBottom: 4 },
  dupText: { color: "#ddd", fontSize: 14, marginBottom: 10 },
  dupActions: { flexDirection: "row", gap: 8 },
  dupBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: "#ffffff10",
    alignItems: "center",
  },
  dupBtnActive: { backgroundColor: "#7c6fff" },
  dupBtnText: { color: "#aaa", fontSize: 13, fontWeight: "600" },
  dupBtnTextActive: { color: "#fff" },
  confidence: { color: "#666", fontSize: 12, marginBottom: 12, textAlign: "right" },
  field: { marginBottom: 12 },
  label: { color: "#888", fontSize: 12, marginBottom: 4, marginLeft: 2 },
  input: {
    backgroundColor: "#1a1a2e",
    color: "#fff",
    borderRadius: 10,
    padding: 14,
    fontSize: 15,
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  inputMultiline: { minHeight: 70, textAlignVertical: "top" },
  save: {
    backgroundColor: "#7c6fff",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 8,
  },
  saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  row: { flexDirection: "row", gap: 12, marginTop: 12 },
  retake: {
    flex: 1,
    padding: 14,
    borderRadius: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#ffffff20",
  },
  retakeText: { color: "#ccc", fontSize: 15 },
  discardBtn: { flex: 1, padding: 14, borderRadius: 10, alignItems: "center" },
  discardText: { color: "#ef4444", fontSize: 15 },
});

import { useEffect, useRef, useState } from "react";
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
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  addOrganizationNote,
  addPersonNote,
  setPersonNextStep,
  fetchOrganization,
  fetchPerson,
  MeetingMethod,
  OrganizationDetail,
  Person,
  transcribeOrganizationNote,
  transcribePersonNote,
  updateOrganizationState,
  updatePersonStage,
} from "../../services/api";
import { getRole } from "../../services/auth";
import { clearDraft, loadDraft, saveDraft } from "../../services/drafts";
import { notifyChanged, organizationKey, personKey } from "../../services/refreshBus";
import { useVoiceDictation } from "../../services/useVoiceDictation";
import { PipelineStage } from "../../services/organizationState";
import { useTranslation } from "../../i18n/I18nContext";
import { Chip, StageStatusChange, StageStatusPicker } from "../../components/StageStatusPicker";
import { dateInDays, FOLLOW_UPS, followUpDate } from "../../services/followUps";
import { PersonStagePicker } from "../../components/PersonStagePicker";

const METHODS: { value: MeetingMethod; labelKey: string }[] = [
  { value: "in_person", labelKey: "meeting.methodVisit" },
  { value: "meeting", labelKey: "meeting.methodMeeting" },
  { value: "phone", labelKey: "meeting.methodCall" },
  { value: "video", labelKey: "meeting.methodVideo" },
  { value: "email", labelKey: "meeting.methodEmail" },
  { value: "other", labelKey: "meeting.methodOther" },
];

// People keep their own, older note vocabulary for the first types.
const PERSON_METHOD: Record<MeetingMethod, string> = {
  in_person: "visit",
  meeting: "meeting",
  phone: "call",
  video: "video",
  email: "email",
  other: "other",
};

/** Typed minutes as a number, null when blank or not a whole number 0–1440. */
export function typedMinutes(text: string): number | null {
  if (!/^\d{1,4}$/.test(text.trim())) return null;
  const minutes = Number(text.trim());
  return minutes <= 1440 ? minutes : null;
}

// Kept importable from here for the screen's tests.
export { dateInDays, FOLLOW_UPS };

type Kind = "organization" | "person";

/**
 * Log a meeting, call or visit in one screen: dictate or type, optionally set a follow-up
 * and move the stage, then Save once. What is typed is kept on the phone until the server
 * has it, so a dropped connection loses nothing.
 */
export default function LogMeetingScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useLocalSearchParams<{ kind: Kind; id: string; name?: string }>();
  const kind: Kind = params.kind === "person" ? "person" : "organization";
  const targetId = Number(params.id);
  const draftKey = `${kind}:${targetId}`;

  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [subject, setSubject] = useState<OrganizationDetail | Person | null>(null);
  const [note, setNote] = useState("");
  const [method, setMethod] = useState<MeetingMethod | null>(null);
  const [minutes, setMinutes] = useState("");
  const [followUp, setFollowUp] = useState("none");
  const [followUpText, setFollowUpText] = useState("");
  const [pendingChange, setPendingChange] = useState<StageStatusChange | null>(null);
  const [restored, setRestored] = useState(false);
  const [draftReady, setDraftReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [noteSaved, setNoteSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finished = useRef(false);

  useEffect(() => {
    getRole().then((role) => setIsAdmin(role === "admin"));
  }, []);

  useEffect(() => {
    const load = kind === "organization" ? fetchOrganization(targetId) : fetchPerson(targetId);
    load.then(setSubject).catch(() => setSubject(null));
  }, [kind, targetId]);

  useEffect(() => {
    loadDraft(draftKey).then((draft) => {
      if (draft) {
        setNote(draft.note);
        setMethod(METHODS.some((m) => m.value === draft.method) ? (draft.method as MeetingMethod) : null);
        setFollowUp(FOLLOW_UPS.some((f) => f.id === draft.followUp) ? draft.followUp : "none");
        setFollowUpText(draft.followUpText);
        setRestored(draft.note.trim().length > 0);
      }
      setDraftReady(true);
    });
  }, [draftKey]);

  // Keep what is typed on the phone until the server has it.
  useEffect(() => {
    if (!draftReady || finished.current) return;
    void saveDraft(draftKey, { note, method, followUp, followUpText });
  }, [draftReady, draftKey, note, method, followUp, followUpText]);

  const dictation = useVoiceDictation({
    transcribe: (uri) =>
      (kind === "organization" ? transcribeOrganizationNote(targetId, uri) : transcribePersonNote(targetId, uri)).then(
        (r) => r.transcript,
      ),
    onText: (text) => setNote((prev) => (prev ? `${prev}\n${text}` : text)),
  });

  const hasNote = note.trim().length > 0;
  // Something to send: a note, or a stage change (alone, or left over after the note went through).
  const canSave = !saving && (hasNote || !!pendingChange || (kind === "person" && followUp !== "none"));
  const title = params.name ? `${params.name}` : t(kind === "organization" ? "drawer.organization" : "drawer.person");

  function finish() {
    finished.current = true;
    notifyChanged(kind === "organization" ? organizationKey(targetId) : personKey(targetId));
    if (router.canGoBack()) router.back();
    else
      router.replace({
        pathname: kind === "organization" ? "/(drawer)/organization-detail" : "/(drawer)/person-detail",
        params: { id: String(targetId) },
      });
  }

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    // 1. the note — and only once: a retry after a later failure must not post it again
    if (hasNote && !noteSaved) {
      try {
        if (kind === "organization") {
          const date = followUpDate(followUp);
          await addOrganizationNote(targetId, {
            note: note.trim(),
            method,
            follow_up_date: date,
            follow_up_text: date === null ? null : followUpText.trim() || null,
            duration_minutes: typedMinutes(minutes),
          });
        } else {
          await addPersonNote(targetId, note.trim(), method ? PERSON_METHOD[method] : null, typedMinutes(minutes));
        }
        setNoteSaved(true);
        setNote("");
        await clearDraft(draftKey);
      } catch (err: any) {
        setError(err?.response?.data?.detail || t("meeting.saveFailed"));
        setSaving(false);
        return;
      }
    }
    // 2. a person's follow-up becomes their next step. Saving the same step again
    //    changes nothing on the server, so a retry is safe.
    if (kind === "person" && followUp !== "none") {
      try {
        await setPersonNextStep(targetId, followUpText.trim() || t("meeting.followUp"), followUpDate(followUp));
      } catch (err: any) {
        setError(err?.response?.data?.detail || t("meeting.nextStepFailedNoteSaved"));
        setSaving(false);
        return;
      }
    }
    // 3. the stage change, if any (organizations; a person's stage saves when tapped)
    if (kind === "organization" && pendingChange) {
      try {
        await updateOrganizationState(targetId, pendingChange);
        setPendingChange(null);
      } catch (err: any) {
        setError(err?.response?.data?.detail || t("meeting.stageFailedNoteSaved"));
        setSaving(false);
        return;
      }
    }
    setSaving(false);
    finish();
  }

  if (isAdmin === false) {
    return (
      <View style={styles.center}>
        <Text style={styles.muted}>{t("meeting.adminOnly")}</Text>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.heading}>{t("meeting.title")}</Text>
        <Text style={styles.subject}>{title}</Text>

        <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("meeting.method")}>
          {METHODS.map(({ value, labelKey }) => (
            <Chip
              key={value}
              label={t(labelKey)}
              selected={method === value}
              disabled={saving}
              onPress={() => setMethod(method === value ? null : value)}
            />
          ))}
        </View>
        {!!method && method !== "other" && (
          <TextInput
            style={styles.smallInput}
            value={minutes}
            onChangeText={setMinutes}
            keyboardType="number-pad"
            maxLength={4}
            placeholder={t("meeting.minutesPlaceholder")}
            placeholderTextColor="#666"
            editable={!saving}
            accessibilityLabel={t("meeting.minutes")}
          />
        )}

        <TextInput
          style={styles.input}
          multiline
          value={note}
          onChangeText={setNote}
          placeholder={t("meeting.placeholder")}
          placeholderTextColor="#666"
          editable={!saving}
          textAlignVertical="top"
          accessibilityLabel={t("meeting.placeholder")}
        />
        {restored && <Text style={styles.hint}>{t("meeting.draftRestored")}</Text>}

        <TouchableOpacity
          style={[styles.mic, dictation.phase === "recording" && styles.micActive]}
          onPress={dictation.toggle}
          disabled={dictation.phase === "transcribing" || saving}
          accessibilityRole="button"
          accessibilityLabel={t(dictation.phase === "recording" ? "meeting.stopDictating" : "meeting.dictate")}
        >
          {dictation.phase === "transcribing" ? (
            <ActivityIndicator color="#7c6fff" size="small" />
          ) : (
            <Text style={styles.micText}>
              {dictation.phase === "recording" ? `⏹  ${t("meeting.stopDictating")}` : `🎙  ${t("meeting.dictate")}`}
            </Text>
          )}
        </TouchableOpacity>
        {!!dictation.error && <Text style={styles.error}>{dictation.error}</Text>}

        {(kind === "organization" || kind === "person") && (
          <View style={styles.block}>
            <Text style={styles.label}>{kind === "person" ? t("meeting.nextStep") : t("meeting.followUp")}</Text>
            <View style={styles.choices} accessibilityRole="radiogroup" accessibilityLabel={t("meeting.followUp")}>
              {FOLLOW_UPS.map(({ id, labelKey }) => (
                <Chip
                  key={id}
                  label={t(labelKey)}
                  selected={followUp === id}
                  disabled={saving}
                  onPress={() => setFollowUp(id)}
                />
              ))}
            </View>
            {followUp !== "none" && (
              <>
                <Text style={styles.hint}>
                  {t("meeting.followUpOn", { date: followUpDate(followUp) })}
                </Text>
                <TextInput
                  style={styles.smallInput}
                  value={followUpText}
                  onChangeText={setFollowUpText}
                  placeholder={t("meeting.followUpAbout")}
                  placeholderTextColor="#666"
                  editable={!saving}
                />
              </>
            )}
          </View>
        )}

        {subject && kind === "organization" && (
          <StageStatusPicker
            key={`log-${targetId}`}
            embedded
            stage={(subject as OrganizationDetail).pipeline_stage}
            status={(subject as OrganizationDetail).status}
            onChange={setPendingChange}
          />
        )}
        {subject && kind === "person" && (
          <PersonStagePicker
            key={`log-person-${targetId}`}
            stage={(subject as Person).pipeline_stage ?? null}
            organizationStage={(subject as Person).company_pipeline_stage ?? null}
            onSave={async (stage: PipelineStage | null) => {
              await updatePersonStage(targetId, stage);
            }}
          />
        )}

        {!!error && (
          <Text style={styles.error} accessibilityLiveRegion="assertive">
            {error}
          </Text>
        )}
        {noteSaved && !!error && <Text style={styles.hint}>{t("meeting.noteIsSaved")}</Text>}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.save, !canSave && styles.saveDisabled]}
          onPress={save}
          disabled={!canSave}
          accessibilityRole="button"
          accessibilityState={{ disabled: !canSave, busy: saving }}
        >
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.saveText}>
              {noteSaved && pendingChange
                ? t("meeting.retryStage")
                : pendingChange && hasNote
                  ? t("meeting.saveWithStage")
                  : pendingChange
                    ? t("meeting.saveStageOnly")
                    : t("meeting.save")}
            </Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: "#0f0f23" },
  container: { flex: 1 },
  content: { padding: 20, paddingBottom: 30 },
  center: { alignItems: "center", backgroundColor: "#0f0f23", flex: 1, justifyContent: "center", padding: 24 },
  muted: { color: "#888", fontSize: 15, textAlign: "center" },
  heading: { color: "#888", fontSize: 11, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  subject: { color: "#fff", fontSize: 22, fontWeight: "700", marginBottom: 14, marginTop: 2 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  input: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff25",
    borderRadius: 10,
    borderWidth: 1,
    color: "#fff",
    fontSize: 16,
    marginTop: 14,
    minHeight: 150,
    padding: 12,
  },
  smallInput: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff25",
    borderRadius: 10,
    borderWidth: 1,
    color: "#fff",
    fontSize: 15,
    marginTop: 8,
    minHeight: 44,
    paddingHorizontal: 12,
  },
  hint: { color: "#888", fontSize: 12, marginTop: 8 },
  error: { color: "#ef8a8a", fontSize: 13, marginTop: 10 },
  mic: {
    alignItems: "center",
    borderColor: "#7c6fff",
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: 12,
    minHeight: 48,
  },
  micActive: { backgroundColor: "#7c6fff33", borderColor: "#ef8a8a" },
  micText: { color: "#aaa3ff", fontSize: 15, fontWeight: "600" },
  block: { marginTop: 18 },
  label: { color: "#888", fontSize: 11, fontWeight: "700", letterSpacing: 1, marginBottom: 8, textTransform: "uppercase" },
  footer: { backgroundColor: "#0f0f23", borderTopColor: "#ffffff15", borderTopWidth: 1, padding: 14 },
  save: { alignItems: "center", backgroundColor: "#7c6fff", borderRadius: 12, justifyContent: "center", minHeight: 54 },
  saveDisabled: { opacity: 0.4 },
  saveText: { color: "#fff", fontSize: 17, fontWeight: "700" },
});

import * as Crypto from "expo-crypto";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";

import { useLocalOffers } from "../hooks/useLocalOffers";
import { useTranslation } from "../i18n/I18nContext";
import { ACTIVITY_METHODS, PERSON_ACTIVITY_METHOD } from "../services/activityMethods";
import type { MeetingMethod } from "../services/api";
import { parseDay } from "../services/dates";
import { GENERAL } from "../services/deals";
import { dateInDays, FOLLOW_UPS, followUpDate } from "../services/followUps";
import { ATTITUDES, type Attitude, MY_READS, type MyRead } from "../services/judgments";
import { openActivityDraft, saveActivityDraft, type ActivityDraft } from "../services/local-activity-drafts";
import { queueLocalActivity } from "../services/local-outbox";
import { useOffline } from "../services/offline-context";
import { getSyncDeviceId } from "../services/sync-network";
import { useAdminRole } from "../services/use-admin-role";
import { JudgmentChips } from "./JudgmentChips";
import { OfferPicker } from "./OfferPicker";
import { Chip } from "./StageStatusPicker";

type Kind = "organization" | "person";
type OpenDraft = ActivityDraft & { database: object; target: string };
const stringValue = (value: unknown): string => typeof value === "string" ? value : "";

export function LocalActivityForm({ kind, syncId }: { kind: Kind; syncId: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const admin = useAdminRole();
  const { session, refreshStatus, requestSync } = useOffline();
  const offers = useLocalOffers();
  const [draft, setDraft] = useState<OpenDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const entityKind = kind === "person" ? "person_note" : "organization_activity";
  const activeDraft = session && draft?.database === session.database && draft.target === `${kind}:${syncId}` ? draft : null;
  const values = activeDraft?.values ?? {};
  const note = stringValue(values.note), method = stringValue(values.method), offer = stringValue(values.offer) || GENERAL;
  const followUp = stringValue(values.followUp) || "none", followType = stringValue(values.followType);
  const attitude = Array.isArray(values.attitude) ? values.attitude as Attitude[] : [];
  const myRead = Array.isArray(values.myRead) ? values.myRead as MyRead[] : [];

  useEffect(() => {
    let active = true;
    if (session && admin) openActivityDraft(session.database, entityKind, syncId, Crypto.randomUUID()).then((opened) => {
      if (active) setDraft({ ...opened, database: session.database, target: `${kind}:${syncId}` });
    }).catch(() => { if (active) setError("offlineActivity.draftError"); });
    return () => { active = false; };
  }, [session, admin, entityKind, kind, syncId]);

  useEffect(() => {
    if (!session || !activeDraft) return;
    let active = true;
    saveActivityDraft(session.database, activeDraft.id, activeDraft.values)
      .catch(() => { if (active) setError("offlineActivity.draftError"); });
    return () => { active = false; };
  }, [session, activeDraft]);

  function change(field: string, value: unknown) {
    setDraft((current) => current ? { ...current, values: { ...current.values, [field]: value } } : current);
  }

  async function save() {
    if (!session || !activeDraft || busy.current || !note.trim()) return;
    const minutes = stringValue(values.minutes).trim();
    if (minutes && (!/^\d{1,4}$/.test(minutes) || Number(minutes) > 1440)) { setError("offlineActivity.badMinutes"); return; }
    const day = kind === "organization" ? parseDay(stringValue(values.day)) : null;
    if (day === undefined || (day && day > dateInDays(0))) { setError("meeting.badDay"); return; }
    if (method && !ACTIVITY_METHODS.some((item) => item.value === method)) { setError("recordForm.saveFailed"); return; }
    busy.current = true;
    setSaving(true);
    setError(null);
    const changedAt = new Date().toISOString();
    const parentField = kind === "person" ? "person_sync_id" : "organization_sync_id";
    const bodyField = kind === "person" ? "note" : "summary";
    const patch: Record<string, unknown> = { [parentField]: syncId, [bodyField]: note.trim(),
      method: method ? kind === "person" ? PERSON_ACTIVITY_METHOD[method as MeetingMethod] : method : null,
      duration_minutes: minutes ? Number(minutes) : null, offer_slug: offer, attitude, my_read: myRead };
    if (kind === "organization") Object.assign(patch, { interaction_date: day,
      materials_left: stringValue(values.materials).trim() || null, next_action: stringValue(values.followText).trim() || null,
      next_action_date: followUpDate(followUp), follow_up_type: followType || null });
    try {
      await saveActivityDraft(session.database, activeDraft.id, values);
      await queueLocalActivity(session.database, { mutationId: Crypto.randomUUID(), deviceId: await getSyncDeviceId(),
        entityKind, entitySyncId: Crypto.randomUUID(), changedAt, patch, draftId: activeDraft.id });
    } catch {
      setError("meeting.saveFailed");
      busy.current = false;
      setSaving(false);
      return;
    }
    void Promise.resolve(refreshStatus()).catch(() => {});
    requestSync();
    router.back();
  }

  if (admin === false) return <Text>{t("meeting.adminOnly")}</Text>;
  if (!activeDraft || admin === null) return error ? <Text style={styles.error}>{t(error)}</Text> : <ActivityIndicator color="#7c6fff" />;
  return <ScrollView style={styles.container} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
    <Text style={styles.label}>{t("meeting.method")}</Text>
    <View style={styles.chips}>{ACTIVITY_METHODS.map((item) => <Chip key={item.value} label={t(item.labelKey)}
      selected={method === item.value} disabled={saving} onPress={() => change("method", item.value)} />)}</View>
    <Text style={styles.label}>{t("offlineActivity.note")}</Text>
    <TextInput style={styles.input} value={note} onChangeText={(value) => change("note", value)} multiline maxLength={20000}
      accessibilityLabel={t("offlineActivity.note")} placeholder={t("meeting.placeholder")} placeholderTextColor="#777" editable={!saving} />
    <Text style={styles.label}>{t("meeting.minutes")}</Text>
    <TextInput style={styles.input} value={stringValue(values.minutes)} onChangeText={(value) => change("minutes", value)}
      accessibilityLabel={t("meeting.minutes")} keyboardType="number-pad" maxLength={4} editable={!saving} />
    {kind === "organization" && <>
      <Text style={styles.label}>{t("activity.whenLabel")}</Text>
      <TextInput style={styles.input} value={stringValue(values.day)} onChangeText={(value) => change("day", value)}
        accessibilityLabel={t("activity.whenLabel")} placeholder={t("date.placeholder")} placeholderTextColor="#777" editable={!saving} />
      <Text style={styles.label}>{t("organizationBrief.materialsLeft")}</Text>
      <TextInput style={styles.input} value={stringValue(values.materials)} onChangeText={(value) => change("materials", value)}
        accessibilityLabel={t("organizationBrief.materialsLeft")} multiline maxLength={20000} editable={!saving} />
      <Text style={styles.label}>{t("meeting.followUpAbout")}</Text>
      <TextInput style={styles.input} value={stringValue(values.followText)} onChangeText={(value) => change("followText", value)}
        accessibilityLabel={t("meeting.followUpAbout")} maxLength={500} editable={!saving} />
      <View style={styles.chips}>{FOLLOW_UPS.map((item) => <Chip key={item.id} label={t(item.labelKey)}
        selected={followUp === item.id} disabled={saving} onPress={() => change("followUp", item.id)} />)}</View>
      <View style={styles.chips}>{["commitment", "check_in"].map((value) => <Chip key={value} label={t(`followUp.${value}`)}
        selected={followType === value} disabled={saving} onPress={() => change("followType", followType === value ? "" : value)} />)}</View>
    </>}
    <OfferPicker offers={offers} value={offer} onChange={(value) => change("offer", value)} label={t("offerFilter.label")} withGeneral disabled={saving} />
    <JudgmentChips labelKey="judgment.attitude" valuePrefix="impression." values={ATTITUDES} picked={attitude}
      onChange={(value) => change("attitude", value)} disabled={saving} />
    <JudgmentChips labelKey="judgment.myRead" valuePrefix="myRead." values={MY_READS} picked={myRead}
      onChange={(value) => change("myRead", value)} disabled={saving} />
    {error && <Text style={styles.error} accessibilityLiveRegion="assertive">{t(error)}</Text>}
    <TouchableOpacity accessibilityRole="button" disabled={saving || !note.trim()} onPress={() => { void save(); }} style={styles.button}>
      <Text style={styles.buttonText}>{t("meeting.save")}</Text></TouchableOpacity>
  </ScrollView>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23" }, content: { padding: 16 },
  label: { color: "#bbb", marginTop: 16, marginBottom: 6 }, input: { backgroundColor: "#1a1a2e", color: "#fff", borderRadius: 8, padding: 12 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }, error: { color: "#ff8b8b", marginTop: 12 },
  button: { backgroundColor: "#7c6fff", borderRadius: 8, marginTop: 20, padding: 14 }, buttonText: { color: "#fff", textAlign: "center" },
});

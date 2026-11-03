// The Field mode switch in Settings. Turning it on explains first (Android then asks for
// location, and shows a notification the whole time it records); turning it off stops
// recording at once and sends what is still queued.
import { useCallback, useState } from "react";
import { useFocusEffect } from "expo-router";
import { ActivityIndicator, Alert, Linking, StyleSheet, Switch, Text, View } from "react-native";

import { useTranslation } from "../i18n/I18nContext";
import { fieldModeEndsAt, FIELD_MODE_HOURS, isFieldModeOn, startFieldMode, stopFieldMode } from "../services/fieldMode";

const pad = (n: number) => String(n).padStart(2, "0");

export function FieldModeCard() {
  const { t } = useTranslation();
  const [on, setOn] = useState<boolean | null>(null);
  const [endsAt, setEndsAt] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const refresh = useCallback(
    () =>
      isFieldModeOn().then(async (running) => {
        setOn(running);
        setEndsAt(running ? await fieldModeEndsAt() : null);
      }),
    [],
  );

  // Again on every visit: field mode may have switched itself off in the meantime.
  useFocusEffect(
    useCallback(() => {
      let active = true;
      isFieldModeOn().then(async (running) => {
        if (!active) return;
        setOn(running);
        setEndsAt(running ? await fieldModeEndsAt() : null);
      });
      return () => {
        active = false;
      };
    }, []),
  );

  async function turnOn() {
    setBusy(true);
    setProblem(null);
    try {
      const result = await startFieldMode({
        title: t("fieldMode.notificationTitle"),
        body: t("fieldMode.notificationBody"),
      });
      if (result === "location-denied") setProblem(t("fieldMode.locationDenied"));
    } catch {
      setProblem(t("fieldMode.failed"));
    } finally {
      await refresh();
      setBusy(false);
    }
  }

  async function turnOff() {
    setBusy(true);
    setProblem(null);
    try {
      await stopFieldMode();
    } catch {
      setProblem(t("fieldMode.failed"));
    } finally {
      await refresh();
      setBusy(false);
    }
  }

  function toggle(next: boolean) {
    if (!next) {
      void turnOff();
      return;
    }
    Alert.alert(t("fieldMode.explainTitle"), t("fieldMode.explainBody"), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("fieldMode.continue"), onPress: () => void turnOn() },
    ]);
  }

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={styles.text}>
          <Text style={styles.title}>{t("fieldMode.title")}</Text>
          <Text style={styles.hint}>{t("fieldMode.hint", { hours: FIELD_MODE_HOURS })}</Text>
        </View>
        {on === null || busy ? (
          <ActivityIndicator color="#7c6fff" />
        ) : (
          <Switch value={on} onValueChange={toggle} accessibilityLabel={t("fieldMode.title")} />
        )}
      </View>
      {on && endsAt && (
        <Text style={styles.status}>{t("fieldMode.endsAt", { time: `${pad(endsAt.getHours())}:${pad(endsAt.getMinutes())}` })}</Text>
      )}
      {!!problem && (
        <View>
          <Text style={styles.problem} accessibilityLiveRegion="assertive">{problem}</Text>
          <Text style={styles.link} accessibilityRole="link" onPress={() => Linking.openSettings()}>
            {t("fieldMode.openSettings")}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#1a1a2e",
    borderColor: "#ffffff20",
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 24,
    padding: 18,
  },
  row: { alignItems: "center", flexDirection: "row", gap: 12 },
  text: { flex: 1 },
  title: { color: "#fff", fontSize: 16, fontWeight: "600" },
  hint: { color: "#888", fontSize: 12, lineHeight: 17, marginTop: 4 },
  status: { color: "#5fae78", fontSize: 13, marginTop: 10 },
  problem: { color: "#ef8a8a", fontSize: 13, marginTop: 10 },
  link: { color: "#7c6fff", fontSize: 13, marginTop: 6, textDecorationLine: "underline" },
});

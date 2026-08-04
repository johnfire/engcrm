#!/usr/bin/env bash
# Behavioral checks against the installed APK on a booted emulator/device:
# fires deep-link payloads and watches for crashes/fatal exceptions. Report-
# only by design — see android-security.yml.
#
# This deliberately does NOT try to re-derive exported-component status from
# `dumpsys package` — an earlier version of this script did, on the theory
# that Android's intent-resolver tables ("filter <hex>" entries) only list
# genuinely-exported components. That's wrong: the resolver table lists every
# component with a matching intent-filter regardless of its exported flag —
# `android:exported` is an access-control check enforced at intent-dispatch
# time, not a filter on what appears in the resolver table. This surfaced as
# real false positives on a different app (engcrm-mobile) where several
# Firebase/notification services correctly declare exported="false" but still
# showed up in the resolver table, because they have intent-filters. It never
# manifested on this app only because every intent-filtered component here
# happens to be genuinely exported — luck, not a validated design.
# android-static-checks.mjs (which reads Gradle's merged manifest, which
# explicitly states exported="true"/"false" per component) is the reliable,
# authoritative source for exported-component detection. Don't reintroduce a
# dumpsys-based version of that check here without a way to read the real
# exported flag, not just resolver-table presence.
set -uo pipefail

PACKAGE_NAME="${PACKAGE_NAME:-de.christopherrehm.engcrm}"
OUT_PATH="${SECURITY_FINDINGS_OUT:-android-dynamic-findings.json}"

findings="[]"

add_finding() {
  local severity="$1" category="$2" title="$3" detail="$4"
  findings=$(jq -c --arg s "$severity" --arg c "$category" --arg t "$title" --arg d "$detail" \
    '. + [{severity:$s, category:$c, title:$t, detail:$d}]' <<<"$findings")
}

echo "== app installed and running =="
if ! adb shell pidof "$PACKAGE_NAME" >/dev/null 2>&1; then
  add_finding "critical" "build" \
    "App is not running before deep-link probing has even started" \
    "adb shell pidof $PACKAGE_NAME returned nothing — install/launch may have failed earlier in the job."
  echo "  NOT RUNNING — deep-link probes below will be run anyway, but expect them to also report crashed"
else
  echo "  ok: $PACKAGE_NAME is running"
fi

echo
echo "== deep-link probing =="
payloads=(
  "engcrm://item/../../etc/passwd"
  "engcrm://item/$(printf 'A%.0s' {1..2000})"
  "engcrm://item/%00null"
  "engcrm://../../../"
)

for payload in "${payloads[@]}"; do
  echo "  probing: $payload"
  adb shell am start -a android.intent.action.VIEW -d "$payload" -n "$PACKAGE_NAME/.MainActivity" >/dev/null 2>&1
  sleep 1
  if ! adb shell pidof "$PACKAGE_NAME" >/dev/null 2>&1; then
    add_finding "critical" "MASVS-PLATFORM" \
      "App process died after deep-link payload" \
      "Payload: $payload — app was no longer running afterward. Check logcat for the crash."
    echo "    CRASHED"
    # Best-effort relaunch so remaining payloads still get a fair test.
    adb shell monkey -p "$PACKAGE_NAME" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
    sleep 2
    continue
  fi
  if adb logcat -d -t 50 | grep -q "FATAL EXCEPTION.*$PACKAGE_NAME\|AndroidRuntime.*$PACKAGE_NAME"; then
    add_finding "high" "MASVS-PLATFORM" \
      "Fatal exception logged after deep-link payload" \
      "Payload: $payload — app survived but logged a fatal exception around the same time. Check logcat."
    echo "    LOGGED FATAL EXCEPTION"
  fi
  adb logcat -c
done

echo
echo "$findings" | jq '{check: "android-dynamic-checks", timestamp: now | todate, findings: .}' > "$OUT_PATH"
cat "$OUT_PATH"

# Report-only — this script always exits 0. Findings are surfaced, not gated.
exit 0

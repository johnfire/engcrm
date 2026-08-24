#!/usr/bin/env bash
# UserPromptSubmit hook.
#
# When the prompt asks to fix/clean up dependency or security alerts, inject
# a reminder to (1) cross-check the alert count against a second source
# before reporting it, and (2) check whether anything still consumes a
# flagged file before fixing it, rather than fixing it unconditionally.
#
# Exists because both mistakes actually happened in the same session
# (2026-08-11, engcrm dependabot cleanup): reported zero alerts off a single
# empty `gh api` call when there were 67, then separately upgraded four
# uv.lock files that turned out to be dead weight nothing consumed.
set -uo pipefail

payload="$(cat)"
prompt=$(printf '%s' "$payload" | jq -r '.user_input // empty')

if printf '%s' "$prompt" | grep -qiE 'dependabot|security alert|vulnerabilit|\bcve\b|codeql'; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: "Reminder before touching dependency/security alerts (from past correction in this project): (1) A single empty or low API result is not proof of the true count -- cross-check `gh api .../dependabot/alerts` against the GraphQL `repository.vulnerabilityAlerts.totalCount` (or the GitHub UI) before reporting a number, especially if it contradicts what the user is seeing. (2) Before fixing/upgrading a flagged file (e.g. a lockfile), check whether anything still consumes it -- grep CI workflows, Dockerfiles, and imports. If nothing does, propose deleting it instead of investing in the fix."
    }
  }'
fi

exit 0

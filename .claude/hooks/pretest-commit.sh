#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash, if: "Bash(git commit*)").
#
# Before a `git commit` runs, run the test suite(s) for whatever staged files
# actually touch, and block the commit if any of them fail. Exists because a
# signature change to a shared agent dependency (get_or_create_dossier) was
# committed and pushed without the opportunity-agent's own tests catching it
# --- CI's test loop only covers research/scout/enrichment/outreach/followup,
# not opportunity or engcrm-interview-agent, so this is stricter than CI on
# purpose, not redundant with it.
set -uo pipefail

payload="$(cat)"
command=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')

# Only act on git commit invocations.
if ! printf '%s' "$command" | grep -qE '(^|[;&|]|&&)\s*git commit'; then
  exit 0
fi

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$repo_root" || exit 0

staged=$(git diff --cached --name-only)
if [ -z "$staged" ]; then
  exit 0
fi

labels=()
cmds=()

add_suite() {
  local label="$1" cmd="$2" l
  for l in "${labels[@]:-}"; do
    [ "$l" = "$label" ] && return
  done
  labels+=("$label")
  cmds+=("$cmd")
}

while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    agents/*/*)
      agent_dir=$(printf '%s' "$f" | cut -d/ -f1-2)
      add_suite "$agent_dir" "uv run pytest $agent_dir/tests -q"
      ;;
    engcrm-interview-agent/*)
      add_suite "engcrm-interview-agent" "cd engcrm-interview-agent && uv run pytest tests -q"
      ;;
    engcrm-mobile/*)
      add_suite "engcrm-mobile" "cd engcrm-mobile && npx jest --silent"
      ;;
    gcrm/*|scripts/*|tests/*|pyproject.toml|uv.lock)
      add_suite "root" 'uv run pytest tests -q -m "not integration and not e2e and not network"'
      ;;
  esac
done <<<"$staged"

if [ ${#labels[@]} -eq 0 ]; then
  exit 0
fi

failures=""
summary=""
for i in "${!labels[@]}"; do
  label="${labels[$i]}"
  cmd="${cmds[$i]}"
  output=$(eval "$cmd" 2>&1)
  status=$?
  if [ $status -ne 0 ]; then
    summary="${summary}${label}: FAIL\n"
    failures="${failures}\n--- ${label} (\`${cmd}\`) ---\n$(printf '%s' "$output" | tail -40)\n"
  else
    summary="${summary}${label}: pass\n"
  fi
done

if [ -n "$failures" ]; then
  reason=$(printf 'Commit blocked -- touched-package tests failed.\n%b%b' "$summary" "$failures")
  jq -n --arg reason "$reason" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
  exit 0
fi

msg=$(printf 'pretest-commit: %b' "$summary")
jq -n --arg msg "$msg" '{systemMessage: $msg}'
exit 0

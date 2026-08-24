#!/usr/bin/env bash
# UserPromptSubmit hook.
#
# When the prompt asks for a write against real production data (backfill,
# requeue, delete/fix rows, etc.), inject a reminder to follow the
# remediate-production-data sequence and to hand over the exact runnable SSH
# command rather than trying to execute it directly against the VPS.
#
# Exists because SSH-to-vps for a write reliably hits the sandbox's
# tool-permission layer, and a "yes, go ahead" in chat doesn't lift that --
# only a permission click (or the user running the command themselves) does.
# Re-attempting the ssh call anyway just burns a turn re-discovering that.
set -uo pipefail

payload="$(cat)"
prompt=$(printf '%s' "$payload" | jq -r '.user_input // empty')

if printf '%s' "$prompt" | grep -qiE 'backfill|requeue|(delete|remove|fix|update|clean(ed)? up|correct) (those|these|the) (rows|contacts|records|entries)|those (contacts|rows|records) are wrong|production data|prod (db|database)'; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: "This looks like a write against real production data -- follow the remediate-production-data skill sequence (evidence-based affected set, full preview before any write, guard the write on more than id, verify the goal not the action, re-run until idempotent). On execution: SSH-to-vps for a write reliably hits the sandbox tool-permission layer -- a \"yes, go ahead\" in chat does not lift that, only an interactive permission click or the user running it themselves does. Do not spend a turn re-attempting the ssh call after it is denied. Instead, once the dry run looks right and the user has confirmed in chat, hand over the exact runnable ssh/docker command for them to paste, the same way as the existing scripts/requeue_*.py precedent."
    }
  }'
fi

exit 0

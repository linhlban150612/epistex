#!/usr/bin/env bash
# Validate the kit and installed Paseo providers; --check never changes files.
set -euo pipefail

kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
paseo_config=${PASEO_CONFIG:-${PASEO_HOME:-$HOME/.paseo}/config.json}
dry=0
errs=0
fail() { printf '  ! %s\n' "$*" >&2; errs=$((errs + 1)); }

for arg in "$@"; do
  case "$arg" in
    --check) dry=1 ;;
    *) printf 'usage: %s [--check]\n' "$0" >&2; exit 2 ;;
  esac
done

for name in bash jq python3 dirname wc; do
  command -v "$name" >/dev/null || fail "need $name on PATH"
done
(( errs == 0 )) || exit 1
python3 -c 'import tomllib' 2>/dev/null || fail 'need Python 3.11+ (tomllib)'
codex_bin=${CODEX_BIN:-codex}
command -v "$codex_bin" >/dev/null || fail "CODEX_BIN executable not found: $codex_bin"

for seat in LEAD PEER SUPERVISOR; do
  prompt="$kit/agents/$seat.md"
  if [[ ! -f "$prompt" ]]; then
    fail "missing $prompt"
  elif (( $(wc -c < "$prompt") > 16384 )); then
    fail "$prompt exceeds 16 KiB"
  fi
done

for name in codex-room codex-room-sync; do
  wrapper="$kit/setup/$name"
  if [[ ! -f "$wrapper" ]]; then
    fail "missing $wrapper"
    continue
  fi
  if (( dry == 0 )); then chmod 755 "$wrapper"; fi
  [[ -x "$wrapper" ]] || fail "$wrapper is not executable"
done

if [[ ! -f "$paseo_config" ]]; then
  fail "missing $paseo_config; merge examples/paseo-providers.json first"
elif ! jq -e 'type == "object"' "$paseo_config" >/dev/null 2>&1; then
  fail "$paseo_config is not a valid JSON object"
else
  expected_deny='["archive_workspace","browser_back","browser_click","browser_close_tab","browser_drag","browser_evaluate","browser_fill","browser_forward","browser_hover","browser_keypress","browser_list_tabs","browser_logs","browser_navigate","browser_new_tab","browser_reload","browser_resize","browser_screenshot","browser_scroll","browser_select","browser_snapshot","browser_type","browser_upload","browser_wait","capture_terminal","create_heartbeat","create_schedule","create_terminal","create_workspace","delete_heartbeat","delete_schedule","inspect_provider","inspect_schedule","kill_agent","kill_terminal","list_profiles","list_schedules","list_terminals","list_workspace_scripts","pause_schedule","rename_workspace","resume_schedule","run_schedule_once","schedule_logs","send_terminal_keys","start_workspace_script","stop_workspace_script","update_agent","update_schedule"]'

  while IFS= read -r provider; do
    [[ -n "$provider" ]] || continue
    actual=$(jq -c --arg id "$provider" '.agents.providers[$id].paseoTools.disabledTools | if type == "array" and all(.[]; type == "string") then sort else null end' "$paseo_config")
    [[ "$actual" == "$expected_deny" ]] || fail "$provider: paseoTools.disabledTools must exactly match the deny-list"
  done < <(jq -r '.agents.providers | to_entries[] | select(.value.paseoTools.enabled == true) | .key' "$paseo_config")
  jq -e '.daemon.mcp.enabled != false and .daemon.mcp.injectIntoAgents == true' \
    "$paseo_config" >/dev/null || fail 'Paseo MCP injection is not enabled'
  jq -e --arg command "$kit/setup/role-agent" '
    .agents.providers["devin-supervisor"] |
    .extends == "acp" and .enabled == true and
    .command == [$command, "supervisor", "devin"] and .paseoTools.enabled == true and
    ([.models[] | select(.isDefault == true)] | length) == 1 and
    any(.models[]; .id == "fusion-claude-fable-5-1-medium-sidekick-swe-2-medium" and
      .isDefault == true and
      ([.thinkingOptions[] | select(.isDefault == true) | .id] == ["medium"]))
  ' "$paseo_config" >/dev/null || fail 'devin-supervisor: wrong launcher, tools or model/effort'
  for seat in lead peer; do
    model=gpt-6.1-sol
    [[ "$seat" != peer ]] || model=gpt-6-luna
    jq -e --arg key "codex-$seat" --arg role "$seat" \
      --arg command "$kit/setup/codex-room" --arg model "$model" '
      .agents.providers[$key] |
      .extends == "codex" and .enabled == true and
      .command == [$command, $role] and
      .paseoTools.enabled == ($role == "lead") and
      ([.models[] | select(.isDefault == true)] | length) == 1 and
      any(.models[]; .id == $model and .isDefault == true and
        ([.thinkingOptions[] | select(.isDefault == true) | .id] == ["low"]))
    ' "$paseo_config" >/dev/null || fail "codex-$seat: wrong wrapper, tool permissions or model/effort"
  done
fi

(( errs == 0 )) || { printf '! %s error(s) — setup is not ready.\n' "$errs" >&2; exit 1; }
printf '✓ static kit/provider check passed; auth, daemon and launch not checked\nAfter changing providers: reload with the Paseo CLI and verify launch per SETUP.md\n'

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

for name in bash jq python3 dirname wc grep; do
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

if ! jq -e '
  .compaction.modelOverrides | type == "object" and length > 0
' "$kit/.pi/settings.json" >/dev/null 2>&1; then
  fail '.pi/settings.json: need valid JSON with non-empty compaction.modelOverrides'
fi

if [[ ! -f "$kit/.omp/config.yml" ]] || ! grep -Eq '^[[:space:]]*thresholdTokens:[[:space:]]*100000[[:space:]]*$' "$kit/.omp/config.yml"; then
  fail '.omp/config.yml: need thresholdTokens: 100000'
fi

# Human opt-in is user-wide, so this observation must never gate workspace setup.
if ! jq -e '.agent.compaction_threshold_tokens == 100000' \
  "${XDG_CONFIG_HOME:-$HOME/.config}/devin/config.json" >/dev/null 2>&1; then
  printf '  note: Devin user-wide agent.compaction_threshold_tokens is absent or != 100000 (informational only)\n'
fi

if [[ ! -f "$paseo_config" ]]; then
  fail "missing $paseo_config; merge examples/paseo-providers.json first"
elif ! jq -e 'type == "object"' "$paseo_config" >/dev/null 2>&1; then
  fail "$paseo_config is not a valid JSON object"
else
  while IFS= read -r seat; do
    [[ -n "$seat" ]] || continue
    jq -e --arg seat "$seat" '
      .agents.providers[$seat].env.CLAUDE_CODE_AUTO_COMPACT_WINDOW == "100000"
    ' "$paseo_config" >/dev/null || fail "$seat: need env CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000"
  done < <(jq -r '
    ([.agents.providers | to_entries[] |
      select((.key | startswith("claude-")) and .value.enabled == true) | .key]
      + ["claude-peer"]) | unique[]
  ' "$paseo_config")

  expected_deny_lead='["archive_workspace","browser_back","browser_click","browser_close_tab","browser_drag","browser_evaluate","browser_fill","browser_forward","browser_hover","browser_keypress","browser_list_tabs","browser_logs","browser_navigate","browser_new_tab","browser_reload","browser_resize","browser_screenshot","browser_scroll","browser_select","browser_snapshot","browser_type","browser_upload","browser_wait","capture_terminal","create_heartbeat","create_schedule","create_terminal","create_workspace","delete_heartbeat","delete_schedule","inspect_provider","inspect_schedule","kill_agent","kill_terminal","list_schedules","list_terminals","list_workspace_scripts","pause_schedule","rename_workspace","resume_schedule","run_schedule_once","schedule_logs","send_terminal_keys","start_workspace_script","stop_workspace_script","update_agent","update_schedule"]'
  expected_deny_supervisor=$(jq -c 'map(select(. != "create_workspace"))' <<<"$expected_deny_lead")

  while IFS= read -r provider; do
    [[ -n "$provider" ]] || continue
    case "$provider" in
      *-lead|codex-lead) expected_deny=$expected_deny_lead ;;
      *-supervisor) expected_deny=$expected_deny_supervisor ;;
      *) fail "$provider: enabled Paseo seat must be a Lead or Supervisor"; continue ;;
    esac
    actual=$(jq -c --arg id "$provider" '.agents.providers[$id].paseoTools.disabledTools | if type == "array" and all(.[]; type == "string") then sort else null end' "$paseo_config")
    [[ "$actual" == "$(jq -c 'sort' <<<"$expected_deny")" ]] || fail "$provider: paseoTools.disabledTools must exactly match the deny-list"
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
  for seat in amp-supervisor claude-supervisor codex-supervisor; do
    case "$seat" in
      amp-supervisor) command="$kit/setup/role-agent"; args='["supervisor","amp"]'; model=medium; effort= ;;
      claude-supervisor) command="$kit/setup/role-agent"; args='["supervisor","claude"]'; model=claude-fable-5-1; effort=medium ;;
      codex-supervisor) command="$kit/setup/codex-room"; args='["supervisor"]'; model=gpt-6-astra; effort=low ;;
    esac
    jq -e --arg id "$seat" --arg command "$command" --argjson args "$args" --arg model "$model" --arg effort "$effort" '
      .agents.providers[$id] | .enabled == true and
      .command == ([$command] + $args) and
      .paseoTools.enabled == true and
      ([.models[] | select(.isDefault == true)] | length) == 1 and
      any(.models[]; .id == $model and .isDefault == true and
        (if has("thinkingOptions") then ([.thinkingOptions[] | select(.isDefault == true) | .id] == [$effort]) else $effort == "" end)) and
      (if $id == "amp-supervisor" then ([.models[].id] | sort) == ["high","medium"] else true end) and
      (if $id == "claude-supervisor" then any(.models[]; .id == $model and ([.thinkingOptions[].id] | sort) == ["medium"]) else true end) and
      (if $id == "codex-supervisor" then any(.models[]; .id == $model and ([.thinkingOptions[].id] | sort) == ["low","medium"]) else true end)
    ' "$paseo_config" >/dev/null || fail "$seat: wrong launcher, tools or model/effort"
  done
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
      any(.models[]; .id == $model and .isDefault == ($role == "lead" or $model == "gpt-6-luna") and
        (if $role == "lead" then ([.thinkingOptions[] | select(.isDefault == true) | .id] == ["low"])
         else ([.thinkingOptions[].id] | sort) == ["low"] end)) and
      (if $role == "peer" then any(.models[]; .id == "gpt-6.1-sol" and .isDefault != true and ([.thinkingOptions[].id] | sort) == ["low","medium"]) else true end)
    ' "$paseo_config" >/dev/null || fail "codex-$seat: wrong wrapper, tool permissions or model/effort"
  done
  jq -e '
    .agents.providers["omp-peer"].models |
    [ .[] | select(.id == "github-copilot/gpt-6-luna") ] == [{
      "id": "github-copilot/gpt-6-luna", "label": "GPT-6 Luna", "isDefault": false,
      "thinkingOptions": [
        {"id": "low", "label": "Low", "isDefault": true},
        {"id": "medium", "label": "Medium", "isDefault": false}
      ]
    }]
  ' "$paseo_config" >/dev/null || fail 'omp-peer: wrong GPT-6 Luna model/effort pin'
  for effort in low medium; do
    jq -e --arg effort "$effort" '
      [.daemon.agentProfiles[]? |
        select(.id == ("omp-peer--github-copilot-gpt-6-luna--" + $effort))] |
      length == 1 and all(.[];
        .provider == "omp-peer" and .model == "github-copilot/gpt-6-luna" and
        .thinkingOptionId == $effort)
    ' "$paseo_config" >/dev/null || fail "omp-peer: missing or wrong GPT-6 Luna $effort profile"
  done
  jq -e '
    [.daemon.agentProfiles[]? as $p |
      .agents.providers[$p.provider] as $seat |
      select(($seat | type) != "object" or $seat.enabled != true or
        (($p.provider | test("^(codex|claude|amp|pi|omp|copilot)-")) | not) or
        (([ $seat.models[]?.id ] | index($p.model)) == null) or
        (if any($seat.models[]?; .id == $p.model and has("thinkingOptions"))
         then (($p | has("thinkingOptionId")) | not) or
              (([ $seat.models[] | select(.id == $p.model) | .thinkingOptions[]?.id ] | index($p.thinkingOptionId)) == null)
         else ($p | has("thinkingOptionId")) end)
      )] | length == 0
  ' "$paseo_config" >/dev/null || fail 'daemon.agentProfiles: invalid seat, model or thinking option'
fi

(( errs == 0 )) || { printf '! %s error(s) — setup is not ready.\n' "$errs" >&2; exit 1; }
printf '✓ static kit/provider check passed; auth, daemon and launch not checked\nAfter changing providers: reload with the Paseo CLI and verify launch per SETUP.md\n'

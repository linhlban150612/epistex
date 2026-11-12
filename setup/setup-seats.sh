#!/usr/bin/env bash
# Validate the kit and installed Paseo providers; --check never changes files.
set -euo pipefail

kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
paseo_config=${PASEO_CONFIG:-${PASEO_HOME:-$HOME/.paseo}/config.json}
dry=0
errs=0
project=
plugin_action=
plugin_dir="$kit/plugins/epistex-delivery"
plugin_range='>=0.15.0 <0.16'
plugin_min=0.15.0
plugin_below=0.16.0
plugin_installed=0
fail() { printf '  ! %s\n' "$*" >&2; errs=$((errs + 1)); }
usage() { printf 'usage: %s [--check] [--project <path>] [--install-plugin | --remove-plugin]\n' "$0" >&2; exit 2; }

while (( $# )); do
  case "$1" in
    --check) dry=1 ;;
    --project) (( $# >= 2 )) || usage; project=$2; shift ;;
    --install-plugin) [[ -z "$plugin_action" ]] || usage; plugin_action=install ;;
    --remove-plugin) [[ -z "$plugin_action" ]] || usage; plugin_action=remove ;;
    *) usage ;;
  esac
  shift
done
# Installing or removing the plugin edits the Human's config.json through the daemon: never in --check.
[[ -z "$plugin_action" || "$dry" == 0 ]] || usage

for name in bash jq python3 dirname chmod grep sort diff cp mkdir git; do
  command -v "$name" >/dev/null || fail "need $name on PATH"
done
(( errs == 0 )) || exit 1
python3 -c 'import tomllib' 2>/dev/null || fail 'need Python 3.11+ (tomllib)'
codex_bin=${CODEX_BIN:-codex}
command -v "$codex_bin" >/dev/null || fail "CODEX_BIN executable not found: $codex_bin"

for seat in LEAD PEER SUPERVISOR; do
  PYTHONDONTWRITEBYTECODE=1 python3 "$kit/setup/role_prompt.py" "$seat" >/dev/null \
    || fail "$seat: common contract and role prompt must load within 16 KiB combined"
done

# Skills load only from a directory the backend reads: the project's .agents/skills for Amp, Codex,
# OMP, Cursor, Antigravity and Droid; .claude/skills for Claude Code; .kiro/skills for Kiro. Pi gates
# project skills behind project trust, so role-agent passes it the kit skills. Every skill the prompts
# and templates name must exist in the kit and be installed per project.
skill_dirs=(.agents/skills .claude/skills .kiro/skills)
skills_report=
kit_skills=("$kit"/.agents/skills/*/SKILL.md)
[[ -f "${kit_skills[0]}" ]] || fail 'no kit skills under .agents/skills/'
while IFS= read -r path; do
  [[ -f "$kit/$path" ]] || fail "$path: referenced by a prompt or template but missing from the kit"
done < <(grep -rhoE '\.agents/skills/[A-Za-z0-9_-]+/SKILL\.md' "$kit/agents" "$kit/examples" | sort -u)

if [[ -n "$project" ]]; then
  if [[ ! -d "$project" ]]; then
    fail "project directory not found: $project"
  else
    project=$(cd -- "$project" && pwd -P)
    for dir in "${skill_dirs[@]}"; do
      for skill in "${kit_skills[@]}"; do
        name=${skill%/SKILL.md}; name=${name##*/}
        source="$kit/.agents/skills/$name"; target="$project/$dir/$name"
        if [[ -L "$target" || -L "$project/$dir" || -L "$project/${dir%/skills}" ]]; then
          fail "$project: refusing to use symlinked skill path for $name in $dir"
          continue
        fi
        if (( dry == 0 )); then
          mkdir -p "$target" && cp -R "$source/." "$target/"
        fi
        if [[ ! -f "$target/SKILL.md" ]]; then
          fail "$project: missing skill $name in $dir; run without --check to install it"
        elif ! diff -rq "$source" "$target" >/dev/null; then
          fail "$project: skill $name differs from the kit in $dir; run without --check to refresh it"
        fi
      done
    done
    if [[ -f "$project/WORKSPACE_PROTOCOL.md" ]]; then
      while IFS= read -r path; do
        [[ -f "$project/$path" ]] || fail "$project: WORKSPACE_PROTOCOL.md names $path but it is not installed"
      done < <(grep -oE '\.agents/skills/[A-Za-z0-9_-]+/SKILL\.md' "$project/WORKSPACE_PROTOCOL.md" | sort -u)
    fi
    # Installed skills are process documents: keep them out of the target repository unless the
    # Human already tracks them. The repository-local exclude file never changes tracked files.
    for dir in "${skill_dirs[@]}"; do
      skills_git=untracked
      if exclude=$(cd -- "$project" && git rev-parse --git-path info/exclude 2>/dev/null); then
        [[ "$exclude" == /* ]] || exclude="$project/$exclude"
        probe=${kit_skills[0]%/SKILL.md}; probe="$dir/${probe##*/}/SKILL.md"
        if git -C "$project" ls-files --error-unmatch "$dir" >/dev/null 2>&1; then
          skills_git=tracked
        elif [[ -f "$project/$probe" ]] && git -C "$project" check-ignore -q "$probe"; then
          skills_git=ignored
        elif (( dry == 0 )); then
          mkdir -p "${exclude%/*}" && printf '/%s/\n' "$dir" >> "$exclude" && skills_git=ignored
        else
          fail "$project: $dir is neither tracked nor ignored; run without --check to add it to $exclude"
        fi
      fi
      skills_report+="✓ ${#kit_skills[@]} kit skills present in $project/$dir ($skills_git in Git)"$'\n'
    done
  fi
fi

for name in codex-room role-agent kiro-acp claude-sdk amp-acp devin-acp copilot-acp cursor-acp; do
  wrapper="$kit/setup/$name"
  if [[ ! -f "$wrapper" ]]; then
    fail "missing $wrapper"
    continue
  fi
  if (( dry == 0 )); then chmod 755 "$wrapper"; fi
  [[ -x "$wrapper" ]] || fail "$wrapper is not executable"
done

# The delivery plugin is verified on the Paseo releases in one range; manifest, guard and this checker share it.
# A prerelease counts as its stable core (as Paseo itself checks requirements.paseo): 0.15.0-beta.1 is 0.15.0.
paseo_in_range() {
  local core=${1%%[-+]*}
  [[ "$core" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  printf '%s\n%s\n' "$plugin_min" "$core" | sort -V -C || return 1
  [[ "$core" != "$plugin_below" ]] && printf '%s\n%s\n' "$core" "$plugin_below" | sort -V -C
}
if [[ ! -f "$plugin_dir/paseo-plugin.json" || ! -f "$plugin_dir/index.server.ts" || ! -f "$plugin_dir/server/plugin.ts" ]]; then
  fail "delivery plugin: missing files under $plugin_dir"
elif ! jq -e --arg range "$plugin_range" '.id == "epistex-delivery" and .requirements.paseo == $range' "$plugin_dir/paseo-plugin.json" >/dev/null 2>&1 ||
  ! grep -Fq "PASEO_RANGE = \"$plugin_range\"" "$plugin_dir/server/plugin.ts"; then
  fail "delivery plugin: paseo-plugin.json and server/plugin.ts must require Paseo $plugin_range"
fi
paseo_version=
if command -v paseo >/dev/null; then
  paseo_version=$(paseo --version 2>/dev/null) || paseo_version=
  paseo_version=${paseo_version%%$'\n'*}; paseo_version=${paseo_version//[[:space:]]/}
fi

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

  expected_deny_lead='["archive_workspace","browser_back","browser_click","browser_close_tab","browser_drag","browser_evaluate","browser_fill","browser_forward","browser_hover","browser_keypress","browser_list_tabs","browser_logs","browser_navigate","browser_new_tab","browser_reload","browser_resize","browser_screenshot","browser_scroll","browser_select","browser_snapshot","browser_type","browser_upload","browser_wait","capture_terminal","create_heartbeat","create_schedule","create_terminal","create_workspace","delete_heartbeat","delete_schedule","get_agent_activity","get_agent_status","inspect_provider","inspect_schedule","kill_agent","kill_terminal","list_agents","list_hosts","list_schedules","list_terminals","list_workspace_scripts","pause_schedule","rename_workspace","resume_schedule","run_schedule_once","schedule_logs","send_terminal_keys","start_workspace_script","stop_workspace_script","update_agent","update_schedule"]'
  # Lead waits for notifications, so it has no status, list or activity tools to poll with. Supervisor keeps them.
  expected_deny_supervisor=$(jq -c 'map(select(. != "create_workspace" and . != "get_agent_activity" and . != "get_agent_status" and . != "list_agents" and . != "list_hosts"))' <<<"$expected_deny_lead")

  while IFS= read -r provider; do
    [[ -n "$provider" ]] || continue
    case "$provider" in
      *-lead) expected_deny=$expected_deny_lead ;;
      *-supervisor) expected_deny=$expected_deny_supervisor ;;
      *) fail "$provider: enabled Paseo seat must be a Lead or Supervisor"; continue ;;
    esac
    actual=$(jq -c --arg id "$provider" '.agents.providers[$id].paseoTools.disabledTools | if type == "array" and all(.[]; type == "string") then sort else null end' "$paseo_config")
    [[ "$actual" == "$(jq -c 'sort' <<<"$expected_deny")" ]] || fail "$provider: paseoTools.disabledTools must exactly match the deny-list"
  done < <(jq -r '.agents.providers | to_entries[] | select(.value.enabled == true and .value.paseoTools.enabled == true) | .key' "$paseo_config")
  jq -e '.daemon.mcp.enabled != false and .daemon.mcp.injectIntoAgents == true' \
    "$paseo_config" >/dev/null || fail 'Paseo MCP injection is not enabled'
  for seat in amp-supervisor claude-supervisor codex-supervisor; do
    jq -e --arg seat "$seat" '.agents.providers[$seat].enabled == false' "$paseo_config" >/dev/null && continue
    case "$seat" in
      amp-supervisor) command="$kit/setup/role-agent"; args='["supervisor","amp"]'; model=medium; effort= ;;
      claude-supervisor) command="$kit/setup/role-agent"; args='["supervisor","claude"]'; model=claude-sonnet-5-5; effort=low ;;
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
      (if $id == "claude-supervisor" then ([.models[].id] | sort) == ["claude-fable-5-1","claude-opus-5-5","claude-sonnet-5-5"] and
        all(.models[] | select(.id != "claude-fable-5-1"); ([.thinkingOptions[].id] | sort) == ["low","medium"]) else true end) and
      (if $id == "codex-supervisor" then ([.models[].id] | sort) == ["gpt-6-astra","gpt-6.1-sol"] and
        all(.models[]; ([.thinkingOptions[].id] | sort) == ["low","medium"]) else true end)
    ' "$paseo_config" >/dev/null || fail "$seat: wrong launcher, tools or model/effort"
  done
  for seat in lead peer; do
    model=gpt-6.1-sol
    [[ "$seat" != peer ]] || model=gpt-6-luna
    jq -e --arg key "codex-$seat" --arg role "$seat" \
      --arg command "$kit/setup/codex-room" --arg model "$model" '
      .agents.providers[$key] | .models as $models |
      .extends == "codex" and .enabled == true and
      .command == [$command, $role] and
      .paseoTools.enabled == ($role == "lead") and
      ([.models[] | select(.isDefault == true)] | length) == 1 and
      any(.models[]; .id == $model and .isDefault == ($role == "lead" or $model == "gpt-6-luna") and
        (if $role == "lead" then ([.thinkingOptions[] | select(.isDefault == true) | .id] == ["low"])
         else ([.thinkingOptions[].id] | sort) == ["low","medium"] end)) and
      (if $role == "peer" then all("gpt-6.1-sol", "gpt-6.1-terra"; . as $m |
        any($models[]; .id == $m and .isDefault != true and ([.thinkingOptions[].id] | sort) == ["low","medium"])) else true end)
    ' "$paseo_config" >/dev/null || fail "codex-$seat: wrong wrapper, tool permissions or model/effort"
  done
  jq -e '.agents.providers["codex-lead"].models[] | select(.id == "gpt-6.1-sol") |
    ([.thinkingOptions[].id] | sort) == ["low","medium"]
  ' "$paseo_config" >/dev/null || fail 'codex-lead: gpt-6.1-sol needs low and medium efforts'
  for effort in low medium; do
    jq -e --arg effort "$effort" '
      [.daemon.agentProfiles[]? | select(.id == ("codex-lead--gpt-6-1-sol--" + $effort))] |
      length == 1 and all(.[]; .provider == "codex-lead" and .model == "gpt-6.1-sol" and
        .thinkingOptionId == $effort and .modeId == "full-access")
    ' "$paseo_config" >/dev/null || fail "codex-lead: missing or wrong gpt-6.1-sol $effort profile"
  done
  for effort in low medium; do
    jq -e --arg effort "$effort" '
      [.daemon.agentProfiles[]? | select(.id == ("codex-peer--gpt-6-luna--" + $effort))] |
      length == 1 and all(.[]; .provider == "codex-peer" and .model == "gpt-6-luna" and
        .thinkingOptionId == $effort and .modeId == "auto-review")
    ' "$paseo_config" >/dev/null || fail "codex-peer: missing or wrong gpt-6-luna $effort profile (modeId must be auto-review)"
    jq -e --arg effort "$effort" '
      [.daemon.agentProfiles[]? | select(.id == ("codex-peer--gpt-6-1-terra--" + $effort))] |
      length == 1 and all(.[]; .provider == "codex-peer" and .model == "gpt-6.1-terra" and
        .thinkingOptionId == $effort and .modeId == "auto-review")
    ' "$paseo_config" >/dev/null || fail "codex-peer: missing or wrong gpt-6.1-terra $effort profile (modeId must be auto-review)"
  done
  # acceptEdits and default stop a non-interactive Claude Peer on its first Bash permission request.
  jq -e 'all(.daemon.agentProfiles[]? | select(.provider == "claude-peer"); .modeId == "bypassPermissions")
  ' "$paseo_config" >/dev/null || fail "claude-peer: every profile needs modeId bypassPermissions"
  if jq -e '.agents.providers["claude-peer"].enabled == true' "$paseo_config" >/dev/null; then
    # claude-sdk passes this PreToolUse hook to the Claude Peer seat; a hook that cannot run denies nothing.
    guard="$kit/setup/claude-guard" allow=0 deny=0
    printf '{"tool_name":"Bash","tool_input":{"command":"git status"},"cwd":"/"}' |
      CLAUDE_PROJECT_DIR=/ "$guard" >/dev/null 2>&1 || allow=$?
    printf '{"tool_name":"Bash","tool_input":{"command":"git reset --hard"},"cwd":"/"}' |
      CLAUDE_PROJECT_DIR=/ "$guard" >/dev/null 2>&1 || deny=$?
    (( allow == 0 && deny == 2 )) ||
      fail 'claude-peer: setup/claude-guard must be executable, allow git status and deny git reset --hard with exit 2'
  fi
  # Paseo does not inherit the caller's mode into an agent of another provider: create_agent without modeId fails.
  for pair in amp-peer:local cursor-peer:agent kiro-peer:epistex_peer omp-peer:full \
      kiro-lead:epistex_lead kiro-supervisor:epistex_supervisor; do
    jq -e --arg provider "${pair%%:*}" --arg mode "${pair#*:}" '
      all(.daemon.agentProfiles[]? | select(.provider == $provider); .modeId == $mode)
    ' "$paseo_config" >/dev/null || fail "${pair%%:*}: every profile needs modeId ${pair#*:}"
  done
  jq -e '
    .agents.providers["omp-peer"].models |
    [ .[] | select(.id == "openai-codex/gpt-6-luna") ] == [{
      "id": "openai-codex/gpt-6-luna", "label": "GPT-6 Luna", "isDefault": false,
      "thinkingOptions": [
        {"id": "low", "label": "Low", "isDefault": true},
        {"id": "medium", "label": "Medium", "isDefault": false}
      ]
    }]
  ' "$paseo_config" >/dev/null || fail 'omp-peer: wrong GPT-6 Luna model/effort pin'
  jq -e '
    ([.agents.providers["omp-peer"].models[] | select(.isDefault == true) |
      {id, effort: [.thinkingOptions[] | select(.isDefault == true) | .id]}]) ==
      [{"id": "huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017", "effort": ["low"]}] and
    ([.agents.providers["pi-peer"].models[] | select(.isDefault == true) |
      {id, effort: [.thinkingOptions[] | select(.isDefault == true) | .id]}]) ==
      [{"id": "huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017", "effort": ["low"]}]
  ' "$paseo_config" >/dev/null || fail 'omp-peer/pi-peer: default must be Hugging Face DeepSeek V4.1 Flash 1017, low effort'
  for seat in pi-peer omp-peer; do
    jq -e --arg seat "$seat" '
      .agents.providers[$seat].models as $models |
      any($models[]; .id == "openrouter/deepseek/deepseek-v4.1-flash-1017") and
      all($models[]; .id != "openrouter/deepseek/deepseek-v4.1-flash") and
      ([.daemon.agentProfiles[]? | select(.provider == $seat and
        .model == "huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017" and
        .thinkingOptionId == "low")] | length == 1) and
      ([.daemon.agentProfiles[]? | select(.provider == $seat and
        .model == "openrouter/deepseek/deepseek-v4.1-flash-1017" and
        .thinkingOptionId == "low")] | length == 1) and
      all(.daemon.agentProfiles[]?; .provider != $seat or
        .model != "openrouter/deepseek/deepseek-v4.1-flash")
    ' "$paseo_config" >/dev/null || fail "$seat: wrong DeepSeek 1017 models/profiles"
  done
  for effort in low medium; do
    jq -e --arg effort "$effort" '
      [.daemon.agentProfiles[]? |
        select(.id == ("omp-peer--openai-codex-gpt-6-luna--" + $effort))] |
      length == 1 and all(.[];
        .provider == "omp-peer" and .model == "openai-codex/gpt-6-luna" and
        .thinkingOptionId == $effort)
    ' "$paseo_config" >/dev/null || fail "omp-peer: missing or wrong GPT-6 Luna $effort profile"
  done
  jq -e --arg command "$kit/setup/role-agent" '
    .agents.providers["agy-peer"] as $p |
    $p.extends == "acp" and $p.enabled == true and
    $p.label == "Antigravity Peer Seat" and
    $p.command == [$command, "peer", "agy"] and
    $p.paseoTools.enabled == false and
    $p.env == {} and
    ([ $p.models[] | select(.isDefault == true) | .id ]) == ["gemini-3.8-flash-low"] and
    ([ $p.models[].id ] | sort) == ["gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-4-argon-low", "gemini-4-argon-medium"]
  ' "$paseo_config" >/dev/null || fail 'agy-peer: wrong launcher, permissions or model pins'
  for model in gemini-3.8-flash-low gemini-3.8-flash-medium gemini-4-argon-low gemini-4-argon-medium; do
    jq -e --arg model "$model" '
      [.daemon.agentProfiles[]? | select(.id == ("agy-peer--" + ($model | gsub("\\.";"-"))))] |
      length == 1 and all(.[];
        .provider == "agy-peer" and .model == $model and .modeId == "auto_edit" and
        .modeId != "yolo" and (has("thinkingOptionId") | not))
    ' "$paseo_config" >/dev/null || fail "agy-peer: missing or wrong $model profile"
  done
  if jq -e '.agents.providers | has("agy-lead") and .["agy-lead"].enabled != false' "$paseo_config" >/dev/null; then
    jq -e --arg command "$kit/setup/role-agent" '
      .agents.providers["agy-lead"] as $p |
      $p.extends == "acp" and $p.enabled == true and
      $p.label == "Antigravity Lead Seat" and
      $p.command == [$command, "lead", "agy"] and
      $p.paseoTools.enabled == true and
      $p.env == {} and
      ([ $p.models[] | select(.id == "gemini-4-argon-low" and .isDefault == true) ] | length) == 1 and
      ([ $p.models[].id ] | sort) == ["gemini-4-argon-low", "gemini-4-argon-medium"]
    ' "$paseo_config" >/dev/null || fail 'agy-lead: wrong launcher, permissions or model pins'
    for model in gemini-4-argon-low gemini-4-argon-medium; do
      jq -e --arg model "$model" '
        [.daemon.agentProfiles[]? | select(.id == ("agy-lead--" + $model))] |
        length == 1 and all(.[];
          .provider == "agy-lead" and .model == $model and .modeId == "yolo" and
          (has("thinkingOptionId") | not))
      ' "$paseo_config" >/dev/null || fail "agy-lead: missing or wrong $model profile"
    done
  fi
  if ! jq -e '.agents.providers["devin-peer"].enabled == false' "$paseo_config" >/dev/null; then
    jq -e --arg command "$kit/setup/role-agent" '
      .agents.providers["devin-peer"] |
      .extends == "acp" and .enabled == true and
      .command == [$command, "peer", "devin"] and .paseoTools.enabled == false and
      .env == {} and ([.models[].id]) == ["swe-2-high"] and
      all(.models[]; ([.thinkingOptions[].id] | sort) == ["high"])
    ' "$paseo_config" >/dev/null || fail 'devin-peer: wrong launcher, tools or model'
    jq -e '
      [.daemon.agentProfiles[]? | select(.id == "devin-peer--swe-2-high--high")] |
      length == 1 and all(.[]; .provider == "devin-peer" and .model == "swe-2-high" and .thinkingOptionId == "high")
    ' "$paseo_config" >/dev/null || fail "devin-peer: missing or wrong swe-2-high profile"
  fi
  # Droid env is empty (stored login) or a per-seat key plus its own Droid home: Droid rejects
  # sessions when a key and the stored login in ~/.factory belong to different orgs.
  droid_env='.env == {} or (.env | keys == ["FACTORY_API_KEY","FACTORY_HOME_OVERRIDE"] and
    (.FACTORY_API_KEY | type == "string" and startswith("fk-")) and
    (.FACTORY_HOME_OVERRIDE | type == "string" and startswith("/")))'
  droid_homes=$(jq -r '[.agents.providers | to_entries[] |
    select((.key | test("^droid-(peer|lead|supervisor)$")) and .value.enabled == true) |
    .value.env.FACTORY_HOME_OVERRIDE? | strings] | if length == (unique | length) then .[] else "DUPLICATE" end' "$paseo_config")
  while IFS= read -r home; do
    [[ -n "$home" ]] || continue
    if [[ "$home" == DUPLICATE ]]; then
      fail 'droid seats: each FACTORY_HOME_OVERRIDE must be unique'
    elif [[ -L "$home" || ! -d "$home" || -L "$home/.factory" || "$home/" == "$kit/"* ]]; then
      fail "droid seats: FACTORY_HOME_OVERRIDE $home must be an existing non-symlink directory outside the kit"
    elif [[ -L "$home/.factory/settings.json" || ! -f "$home/.factory/settings.json" ]] ||
      ! jq -e '.compactionTokenLimit == 100000' "$home/.factory/settings.json" >/dev/null 2>&1; then
      # Droid reads only this copy; without it the limit falls back to 250000.
      fail "droid seats: $home/.factory/settings.json must be a regular file (copy, not symlink) with compactionTokenLimit 100000"
    elif jq -e '.hooksDisabled == true' "$home/.factory/settings.json" >/dev/null 2>&1; then
      # hooksDisabled stops every hook, also the seat guard that role-agent passes with --settings.
      fail "droid seats: $home/.factory/settings.json must not set hooksDisabled: the seat guard is a hook"
    fi
  done <<<"$droid_homes"
  if jq -e '[.agents.providers | to_entries[] | select(.key | test("^droid-(peer|lead|supervisor)$")) |
      .value.enabled == true] | any' "$paseo_config" >/dev/null; then
    # role-agent passes this PreToolUse hook to every Droid seat; ACP ignores --remove-tools.
    guard="$kit/setup/droid-guard" allow=0 deny=0 push=0 reset=0
    printf '{"tool_name":"Glob"}' | "$guard" >/dev/null 2>&1 || allow=$?
    printf '{"tool_name":"Task"}' | "$guard" >/dev/null 2>&1 || deny=$?
    (( allow == 0 && deny == 2 )) || fail 'droid seats: setup/droid-guard must be executable, allow Glob and deny Task with exit 2'
    printf '{"tool_name":"Execute","tool_input":{"command":"git push"}}' | "$guard" lead >/dev/null 2>&1 || push=$?
    (( allow != 0 || deny != 2 || push == 2 )) || fail 'droid seats: setup/droid-guard must deny git push in a Lead seat with exit 2'
    printf '{"tool_name":"Execute","tool_input":{"command":"git reset --hard"},"cwd":"/"}' |
      FACTORY_PROJECT_DIR=/ "$guard" peer >/dev/null 2>&1 || reset=$?
    (( allow != 0 || deny != 2 || reset == 2 )) || fail 'droid seats: setup/droid-guard must deny git reset --hard in a Peer seat with exit 2'
  fi
  for role in lead supervisor; do
    seat="droid-$role"
    jq -e --arg seat "$seat" '.agents.providers[$seat].enabled == true' "$paseo_config" >/dev/null || continue
    default=claude-opus-5-5
    [[ "$role" != supervisor ]] || default=claude-sonnet-5-5
    jq -e --arg command "$kit/setup/role-agent" --arg seat "$seat" --arg role "$role" --arg default "$default" "
      .agents.providers[\$seat] |
      .extends == \"acp\" and .command == [\$command,\$role,\"droid\"] and
      .paseoTools.enabled == true and ($droid_env) and
      ([.models[].id] | sort) == [\"claude-opus-5-5\",\"claude-sonnet-5-5\",\"gemini-4-argon\",\"gpt-6.1-sol\"] and
      [.models[] | select(.isDefault == true) | .id] == [\$default] and
      all(.models[]; ([.thinkingOptions[].id] | sort) == [\"low\",\"medium\"])
    " "$paseo_config" >/dev/null || fail "$seat: wrong launcher, tools, env or model/effort"
    for model in claude-opus-5-5 claude-sonnet-5-5 gpt-6.1-sol gemini-4-argon; do
      for effort in low medium; do
        # auto-high: lower Droid modes stop on a permission request for every Paseo MCP call.
        jq -e --arg seat "$seat" --arg model "$model" --arg effort "$effort" '
          [.daemon.agentProfiles[]? | select(.id == ($seat + "--" + ($model | gsub("\\.";"-")) + "--" + $effort))] |
          length == 1 and all(.[];
            .provider == $seat and .model == $model and .thinkingOptionId == $effort and
            .modeId == "auto-high")
        ' "$paseo_config" >/dev/null || fail "$seat: missing or wrong $model $effort profile"
      done
    done
  done
  if jq -e '.agents.providers["amp-lead"].enabled == true' "$paseo_config" >/dev/null; then
    jq -e --arg command "$kit/setup/role-agent" '
      .agents.providers["amp-lead"] |
      .extends == "acp" and .command == [$command,"lead","amp"] and
      .paseoTools.enabled == true and .env == {} and
      ([.models[].id]) == ["medium"]
    ' "$paseo_config" >/dev/null || fail 'amp-lead: wrong launcher, tools or model'
    jq -e '
      [.daemon.agentProfiles[]? | select(.id == "amp-lead--medium")] |
      length == 1 and all(.[]; .provider == "amp-lead" and .model == "medium" and .modeId == "local")
    ' "$paseo_config" >/dev/null || fail 'amp-lead: missing or wrong medium profile'
  fi
  jq -e --arg command "$kit/setup/role-agent" '
    .agents.providers["amp-peer"] |
    .extends == "acp" and .command == [$command,"peer","amp"] and
    .paseoTools.enabled == false and .env == {} and ([.models[].id]) == ["low"]
  ' "$paseo_config" >/dev/null || fail 'amp-peer: wrong launcher, tools or model'
  jq -e '
    [.daemon.agentProfiles[]? | select(.id == "amp-peer--low")] |
    length == 1 and all(.[]; .provider == "amp-peer" and .model == "low")
  ' "$paseo_config" >/dev/null || fail 'amp-peer: missing or wrong low profile'
  for role in peer lead supervisor; do
    seat="kiro-$role"
    kiro_default=claude-sonnet-5.5
    [[ "$role" != lead ]] || kiro_default=claude-opus-5.5
    jq -e --arg seat "$seat" '.agents.providers[$seat].enabled == true' "$paseo_config" >/dev/null || continue
    # Lead keeps Paseo tools (deny-list enforced above); Peer has none.
    jq -e --arg command "$kit/setup/role-agent" --arg seat "$seat" --arg role "$role" --arg default "$kiro_default" '
      .agents.providers[$seat] |
      .extends == "acp" and .command == [$command,$role,"kiro"] and
      .paseoTools.enabled == ($role != "peer") and .env == {} and
      ([.models[].id] | sort) == ["claude-opus-5.5","claude-sonnet-5.5"] and
      ([.models[] | select(.isDefault == true) | .id] == [$default]) and
      all(.models[]; ([.thinkingOptions[].id] | sort) == ["low","medium"] and
        ([.thinkingOptions[] | select(.isDefault == true) | .id] == ["low"]))
    ' "$paseo_config" >/dev/null || fail "$seat: wrong launcher, tools or model/effort"
    for model in claude-opus-5.5 claude-sonnet-5.5; do
      for effort in low medium; do
        jq -e --arg seat "$seat" --arg model "$model" --arg effort "$effort" '
          [.daemon.agentProfiles[]? | select(.id == ($seat + "--" + ($model | gsub("\\.";"-")) + "--" + $effort))] |
          length == 1 and all(.[]; .provider == $seat and .model == $model and .thinkingOptionId == $effort)
        ' "$paseo_config" >/dev/null || fail "$seat: missing or wrong $model $effort profile"
      done
    done
    python3 - "$kit/setup/$seat.json" "$HOME/.kiro/agents/epistex_$role.json" <<'PY' || fail "$seat: install exact seat-owned runtime config (no symlinks)"
import pathlib, sys
source, installed = map(pathlib.Path, sys.argv[1:])
sys.exit(installed.is_symlink() or not installed.is_file() or installed.read_bytes() != source.read_bytes())
PY
  done
  if jq -e '.agents.providers["droid-peer"].enabled == true' "$paseo_config" >/dev/null; then
    # Requested efforts advertised by Droid ACP, not generic Paseo metadata.
    droid_efforts='{
      "gemini-4-argon":["low","medium"], "gemini-3.8-flash":["low","medium"],
      "claude-opus-5-5":["low","medium"], "claude-sonnet-5-5":["low","medium"],
      "claude-haiku-5-5":["low","medium"], "gpt-6.1-sol":["low","medium"],
      "glm-5.3":["low","high"], "kimi-k3":["low","high"],
      "deepseek-v4.1-flash-1017":["low"]
    }'
    jq -e --arg command "$kit/setup/role-agent" --argjson efforts "$droid_efforts" '
      .agents.providers["droid-peer"] |
      .extends == "acp" and .label == "Factory Droid Peer Seat" and
      .command == [$command,"peer","droid"] and
      .paseoTools.enabled == false and ('"$droid_env"') and
      ([.models[].id] | sort) == ($efforts | keys) and
      [.models[] | select(.isDefault == true) | .id] == ["claude-haiku-5-5"] and
      all(.models[]; . as $model |
        ([.thinkingOptions[].id] | sort) == ($efforts[$model.id] | sort) and
        [.thinkingOptions[] | select(.isDefault == true) | .id] == ["low"])
    ' "$paseo_config" >/dev/null || fail 'droid-peer: wrong launcher, tools, env or model/effort'
    # auto-high: lower Droid modes stop a non-interactive Peer on its first edit permission request.
    jq -e --argjson efforts "$droid_efforts" '
      . as $config |
      all($efforts | to_entries[]; . as $entry |
        all(.value[]; . as $effort |
          [$config.daemon.agentProfiles[]? |
            select(.id == ("droid-peer--" + ($entry.key | gsub("\\.";"-")) + "--" + $effort))] |
          length == 1 and all(.[]; .provider == "droid-peer" and
            .model == $entry.key and .thinkingOptionId == $effort and .modeId == "auto-high")))
    ' "$paseo_config" >/dev/null || fail 'droid-peer: missing or wrong supported model/effort profile (modeId must be auto-high)'
  fi
  jq -e '
    [.daemon.agentProfiles[]? as $p |
      .agents.providers[$p.provider] as $seat |
      select(($seat | type) != "object" or $seat.enabled != true or
        (($p.provider | test("^(codex|claude|amp|agy|pi|omp|copilot|cursor|kiro|droid|devin)-")) | not) or
        (([ $seat.models[]?.id ] | index($p.model)) == null) or
        (($p | has("modeId")) and (($p.modeId | type) != "string" or $p.modeId == "")) or
        (($p | has("featureValues")) and ($p.featureValues | type) != "object") or
        (if any($seat.models[]?; .id == $p.model and has("thinkingOptions"))
         then (($p | has("thinkingOptionId")) | not) or
              (([ $seat.models[] | select(.id == $p.model) | .thinkingOptions[]?.id ] | index($p.thinkingOptionId)) == null)
         else ($p | has("thinkingOptionId")) end)
      )] | length == 0
  ' "$paseo_config" >/dev/null || fail 'daemon.agentProfiles: invalid seat, model or thinking option (or malformed mode/features settings)'
  # Paseo 0.15+ can resume agents cut by a daemon restart (default off). The Lead rules treat a cut Peer
  # as `was closed` and reassign its round; a resumed Peer would keep writing it. Human decision: keep it off.
  jq -e '.agents.resumeOnStartup != true' "$paseo_config" >/dev/null ||
    fail 'agents.resumeOnStartup must stay off: a resumed Peer keeps writing a round the Lead reassigns'
  if jq -e '.plugins["epistex-delivery"] | type == "object"' "$paseo_config" >/dev/null; then
    plugin_installed=1
    installed_path=$(jq -r '.plugins["epistex-delivery"] | select(.source == "directory") | .path // empty' "$paseo_config")
    if [[ -z "$installed_path" || -L "$installed_path" || ! -d "$installed_path" || "$(cd -- "$installed_path" && pwd -P)" != "$plugin_dir" ]]; then
      fail "delivery plugin: config entry must be a directory source at $plugin_dir (no symlink)"
    fi
    jq -e '.plugins["epistex-delivery"].enabled != false' "$paseo_config" >/dev/null || fail 'delivery plugin: disabled in config (paseo plugin enable epistex-delivery)'
    jq -e '.pluginsEnabled == true' "$paseo_config" >/dev/null || fail 'delivery plugin: installed but pluginsEnabled is not true; the Human sets it in config.json'
    if [[ -z "$paseo_version" ]]; then
      printf '  note: paseo not on PATH; delivery plugin range %s not checked against the daemon (pending)\n' "$plugin_range"
    elif ! paseo_in_range "$paseo_version"; then
      fail "delivery plugin: requires Paseo $plugin_range but paseo is $paseo_version"
    fi
  elif [[ -z "$plugin_action" ]]; then
    fail "delivery plugin: not installed; it is required (missed finish notifications, #6346). After Human approval run $0 --install-plugin"
  fi
fi

(( errs == 0 )) || { printf '! %s error(s) — setup is not ready.\n' "$errs" >&2; exit 1; }
case "$plugin_action" in
  install)
    [[ -n "$paseo_version" ]] || fail 'delivery plugin: paseo not on PATH; install needs the CLI and a running daemon'
    [[ -z "$paseo_version" ]] || paseo_in_range "$paseo_version" || fail "delivery plugin: requires Paseo $plugin_range but paseo is $paseo_version; not installing"
    jq -e '.pluginsEnabled == true' "$paseo_config" >/dev/null || fail 'delivery plugin: set "pluginsEnabled": true in config.json first (Human-approved change); not installing'
    if (( errs == 0 )); then
      if (( plugin_installed )); then
        printf '✓ delivery plugin already installed from %s\n' "$plugin_dir"
      elif paseo plugin install "$plugin_dir"; then
        printf '✓ delivery plugin installed from %s; verify with: paseo plugin ls --json\n' "$plugin_dir"
      else
        fail 'delivery plugin: paseo plugin install failed'
      fi
    fi
    ;;
  remove)
    if (( plugin_installed == 0 )); then
      printf '  note: delivery plugin not installed; nothing to remove\n'
    elif [[ -n "$paseo_version" ]] && paseo plugin remove epistex-delivery; then
      printf '✓ delivery plugin removed from the config; receipts under PASEO_HOME/epistex-delivery are kept\n'
    else
      fail 'delivery plugin: paseo plugin remove failed (needs the CLI and a running daemon)'
    fi
    ;;
esac
(( errs == 0 )) || { printf '! %s error(s) — setup is not ready.\n' "$errs" >&2; exit 1; }
printf '%s' "$skills_report"
printf '✓ static kit/provider check passed; auth, daemon and launch not checked\nAfter changing providers: reload with the Paseo CLI and verify launch per SETUP.md\n'

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
  command -v "$name" >/dev/null || fail "cần $name trên PATH"
done
(( errs == 0 )) || exit 1
python3 -c 'import tomllib' 2>/dev/null || fail 'cần Python 3.11+ (tomllib)'
codex_bin=${CODEX_BIN:-codex}
command -v "$codex_bin" >/dev/null || fail "không tìm thấy executable CODEX_BIN: $codex_bin"

for seat in LEAD PEER; do
  prompt="$kit/agents/$seat.md"
  if [[ ! -f "$prompt" ]]; then
    fail "thiếu $prompt"
  elif (( $(wc -c < "$prompt") > 16384 )); then
    fail "$prompt vượt 16 KiB"
  fi
done

for name in codex-room codex-room-sync; do
  wrapper="$kit/setup/$name"
  if [[ ! -f "$wrapper" ]]; then
    fail "thiếu $wrapper"
    continue
  fi
  if (( dry == 0 )); then chmod 755 "$wrapper"; fi
  [[ -x "$wrapper" ]] || fail "$wrapper chưa executable"
done

if [[ ! -f "$paseo_config" ]]; then
  fail "thiếu $paseo_config; merge examples/paseo-providers.json trước"
elif ! jq -e 'type == "object"' "$paseo_config" >/dev/null 2>&1; then
  fail "$paseo_config không phải JSON object hợp lệ"
else
  jq -e '.daemon.mcp.enabled != false and .daemon.mcp.injectIntoAgents == true' \
    "$paseo_config" >/dev/null || fail 'Paseo MCP injection chưa bật'
  for seat in lead peer; do
    model=gpt-5.6-sol
    [[ "$seat" != peer ]] || model=gpt-5.6-luna
    jq -e --arg key "codex-$seat" --arg role "$seat" \
      --arg command "$kit/setup/codex-room" --arg model "$model" '
      .agents.providers[$key] |
      .extends == "codex" and .enabled == true and
      .command == [$command, $role] and
      .paseoTools.enabled == ($role == "lead") and
      ([.models[] | select(.isDefault == true)] | length) == 1 and
      any(.models[]; .id == $model and .isDefault == true and
        ([.thinkingOptions[] | select(.isDefault == true) | .id] == ["low"]))
    ' "$paseo_config" >/dev/null || fail "codex-$seat: sai wrapper, quyền tools hoặc model/effort"
  done
fi

(( errs == 0 )) || { printf '! %s lỗi — setup chưa sẵn sàng.\n' "$errs" >&2; exit 1; }
printf '✓ kiểm tra tĩnh kit/provider hợp lệ; chưa kiểm auth, daemon hoặc launch\nSau khi đổi provider: dùng Paseo CLI để reload và kiểm launch theo SETUP.md\n'

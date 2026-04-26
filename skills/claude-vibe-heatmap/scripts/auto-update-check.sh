#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../.vibe-profile.conf"
LAST_UPDATE_FILE="$SCRIPT_DIR/../.last-auto-update"
COOLDOWN=86400

[[ -f "$CONFIG_FILE" ]] || exit 0

if [[ -f "$LAST_UPDATE_FILE" ]]; then
  last_ts="$(cat "$LAST_UPDATE_FILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  elapsed=$(( now - last_ts ))
  [[ "$elapsed" -ge "$COOLDOWN" ]] || exit 0
fi

bash "$SCRIPT_DIR/run_profile_update.sh" heatmap 2>&1 | tail -5

date +%s > "$LAST_UPDATE_FILE"
printf '[vibe] Auto-update complete.\n'

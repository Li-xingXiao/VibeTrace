#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="claude"

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [--target claude|codex|both]

Install VibeTrace skills from this checkout.

Options:
  --target claude   Install into ~/.claude/skills (default)
  --target codex    Install into ~/.codex/skills
  --target both     Install into both skill directories
  -h, --help        Show help
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '[vibetrace][error] Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

copy_skills() {
  local dest="$1"
  mkdir -p "$dest"
  for skill_dir in "$ROOT_DIR"/skills/*; do
    [[ -d "$skill_dir" ]] || continue
    local name
    name="$(basename "$skill_dir")"
    rm -rf "$dest/$name"
    cp -R "$skill_dir" "$dest/$name"
  done
  printf '[vibetrace] Installed skills into %s\n' "$dest"
}

case "$TARGET" in
  claude)
    copy_skills "$HOME/.claude/skills"
    ;;
  codex)
    copy_skills "$HOME/.codex/skills"
    ;;
  both)
    copy_skills "$HOME/.claude/skills"
    copy_skills "$HOME/.codex/skills"
    ;;
  *)
    printf '[vibetrace][error] Invalid target: %s\n' "$TARGET" >&2
    usage >&2
    exit 1
    ;;
esac

printf '[vibetrace] Next: /vibe set github=<your-github-username>\n'
printf '[vibetrace] Then: /vibe heatmap\n'

---
name: codefuse-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for CodeFuse local coding history. Use when users ask for CodeFuse vibe stats, CodeFuse coding heatmaps, or publishing CodeFuse activity to a GitHub profile README with the same /vibe workflow.
---

# CodeFuse Vibe Heatmap

Use the same workflow as `vibe`, fixed to the CodeFuse source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source codefuse`
- Key/value equivalent: `/vibe heatmap source=codefuse`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source codefuse`.

CodeFuse engine and project JSONL histories are detected by the core generator when available. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

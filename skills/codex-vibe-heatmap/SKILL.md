---
name: codex-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for Codex local coding history. Use when users ask for Codex vibe stats, Codex coding heatmaps, or publishing Codex activity to a GitHub profile README with the same /vibe workflow.
---

# Codex Vibe Heatmap

Use the same workflow as `vibe`, fixed to the Codex source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source codex`
- Key/value equivalent: `/vibe heatmap source=codex`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source codex`.

Codex history is read from `~/.codex/history.jsonl` by default. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

---
name: windsurf-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for Windsurf local coding history when a compatible history export is available. Use when users ask for Windsurf vibe stats, Windsurf coding heatmaps, or publishing Windsurf activity to a GitHub profile README with the same /vibe workflow.
---

# Windsurf Vibe Heatmap

Use the same workflow as `vibe`, fixed to the Windsurf source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source windsurf`
- With explicit history: `/vibe heatmap source=windsurf history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source windsurf`.

Windsurf does not always expose a reliable local session log. If no usable history is detected, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

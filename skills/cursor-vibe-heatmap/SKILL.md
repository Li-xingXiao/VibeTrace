---
name: cursor-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for Cursor local coding history when a compatible history export is available. Use when users ask for Cursor vibe stats, Cursor coding heatmaps, or publishing Cursor activity to a GitHub profile README with the same /vibe workflow.
---

# Cursor Vibe Heatmap

Use the same workflow as `vibe`, fixed to the Cursor source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source cursor`
- With explicit history: `/vibe heatmap source=cursor history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source cursor`.

Cursor does not always expose a reliable local session log. If no usable history is detected, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

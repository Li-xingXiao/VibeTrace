---
name: aider-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for Aider local coding history when a compatible history export is available. Use when users ask for Aider vibe stats, Aider coding heatmaps, or publishing Aider activity to a GitHub profile README with the same /vibe workflow.
---

# Aider Vibe Heatmap

Use the same workflow as `vibe`, fixed to the Aider source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source aider`
- With explicit history: `/vibe heatmap source=aider history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source aider`.

If Aider history is not detected automatically, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

---
name: antigravity-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for Antigravity local coding history. Use when users ask for Antigravity vibe stats, Antigravity coding heatmaps, or publishing Antigravity activity to a GitHub profile README with the same /vibe workflow.
---

# Antigravity Vibe Heatmap

Use the same workflow as `vibe`, fixed to the Antigravity source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source antigravity`
- With explicit history: `/vibe heatmap source=antigravity history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source antigravity`.

Antigravity local files vary by install. If no usable session history is detected, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

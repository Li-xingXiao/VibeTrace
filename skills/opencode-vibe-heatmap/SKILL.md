---
name: opencode-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for OpenCode local coding history. Use when users ask for OpenCode vibe stats, OpenCode coding heatmaps, or publishing OpenCode activity to a GitHub profile README with the same /vibe workflow.
---

# OpenCode Vibe Heatmap

Use the same workflow as `vibe`, fixed to the OpenCode source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source opencode`
- With explicit history: `/vibe heatmap source=opencode history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source opencode`.

If OpenCode history is not detected automatically, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

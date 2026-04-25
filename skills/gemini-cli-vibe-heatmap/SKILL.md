---
name: gemini-cli-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for Gemini CLI local coding history when a compatible history export is available. Use when users ask for Gemini CLI vibe stats, Gemini CLI coding heatmaps, or publishing Gemini CLI activity to a GitHub profile README with the same /vibe workflow.
---

# Gemini CLI Vibe Heatmap

Use the same workflow as `vibe`, fixed to the Gemini CLI source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source gemini-cli`
- With explicit history: `/vibe heatmap source=gemini-cli history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source gemini-cli`.

If Gemini CLI history is not detected automatically, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

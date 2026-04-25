---
name: codebuddy-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for CodeBuddy local coding history. Use when users ask for CodeBuddy vibe stats, CodeBuddy coding heatmaps, or publishing CodeBuddy activity to a GitHub profile README with the same /vibe workflow.
---

# CodeBuddy Vibe Heatmap

Use the same workflow as `vibe`, fixed to the CodeBuddy source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source codebuddy`
- With explicit history: `/vibe heatmap source=codebuddy history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source codebuddy`.

If CodeBuddy history is not detected automatically, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

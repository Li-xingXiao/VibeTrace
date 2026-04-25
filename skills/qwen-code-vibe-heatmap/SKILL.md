---
name: qwen-code-vibe-heatmap
description: Generate and publish VibeTrace heatmaps and tool usage cards for Qwen Code local coding history when a compatible history export is available. Use when users ask for Qwen Code vibe stats, Qwen Code coding heatmaps, or publishing Qwen Code activity to a GitHub profile README with the same /vibe workflow.
---

# Qwen Code Vibe Heatmap

Use the same workflow as `vibe`, fixed to the Qwen Code source.

## Commands

- Setup: `/vibe set github=<username>`
- Config: `/vibe config`
- Publish: `/vibe heatmap --source qwen-code`
- With explicit history: `/vibe heatmap source=qwen-code history=<path-or-glob>`

Do not ask the user to run bash manually. Resolve the core script from `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh` or `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`, then run it internally with `heatmap --source qwen-code`.

If Qwen Code history is not detected automatically, accept `history=<path-or-glob>` from the user and pass it to the same script. The profile README is preserved outside the `<!-- vibe-heatmap:start -->` marker block.

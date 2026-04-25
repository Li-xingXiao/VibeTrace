---
name: codex-vibe-heatmap
description: Build and maintain a GitHub-style vibe coding heatmap from Codex local history (`~/.codex/history.jsonl`), including daily active minutes, session frequency, yearly SVG output, and optional README auto-update. Use when users ask to track Codex coding time/frequency, visualize activity like GitHub contributions, or publish a profile heatmap.
---

# Codex Vibe Heatmap

Generate a GitHub-style contribution heatmap from Codex local history and keep a profile README block updated.

## Use This Workflow

1. Resolve target scope.
- Codex only: `--source codex`
- Cross-agent: `--source combined`

2. Generate SVG + JSON stats.

```bash
python3 scripts/vibe_heatmap.py \
  --source codex \
  --year "$(date +%Y)" \
  --output-svg assets/codex-vibe-heatmap.svg \
  --output-json assets/codex-vibe-heatmap.json
```

3. Update README marker block when the user wants profile display.

```bash
python3 scripts/vibe_heatmap.py \
  --source codex \
  --year "$(date +%Y)" \
  --output-svg assets/codex-vibe-heatmap.svg \
  --output-json assets/codex-vibe-heatmap.json \
  --readme README.md \
  --svg-url ./assets/codex-vibe-heatmap.svg
```

## Script Behavior

- Read `~/.codex/history.jsonl` by default.
- Parse timestamps from `ts`/`timestamp` fields (sec and ms both supported).
- Estimate active time using `event_window_minutes` (default 4).
- Split sessions when event gaps exceed `idle_gap_minutes` (default 25).
- Render GitHub-style yearly grid SVG with activity levels.
- Print one-line JSON summary to stdout for automation.

## Key Options

- `--source claude|codex|combined`
- `--year 2026`
- `--claude-history <path>`
- `--codex-history <path>`
- `--output-svg <path>`
- `--output-json <path>`
- `--readme <path>`
- `--svg-url <url-or-path>`
- `--idle-gap-minutes <float>`
- `--event-window-minutes <float>`
- `--intensity-mode minutes|sessions|events`
- `--tz Asia/Hong_Kong`

## Marker Contract

When `--readme` is set, replace only this block:

```markdown
<!-- vibe-heatmap:start -->
...
<!-- vibe-heatmap:end -->
```

If markers are missing, append the block to the end of README.

## Troubleshooting

- Missing output or all-zero heatmap: verify history file exists and has recent lines.
- Wrong day bucket: pass explicit timezone with `--tz`.
- Session count too high/low: tune `--idle-gap-minutes`.
- Active minutes too high/low: tune `--event-window-minutes`.

## References

- Profile automation recipe: `references/github-profile-workflow.md`

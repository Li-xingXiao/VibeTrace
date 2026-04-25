# GitHub Profile Workflow

Use this workflow to publish a GitHub-style vibe heatmap to a profile repository.

## 1) Prepare profile repository

Create or open the repository named exactly as your GitHub username.

Example: username `alice` -> repository `alice/alice`.

## 2) Add marker block in README

Insert these markers once in your profile `README.md`:

```markdown
<!-- vibe-heatmap:start -->
<!-- vibe-heatmap:end -->
```

The script rewrites only this block.

## 3) Commit script into repository

Copy `scripts/vibe_heatmap.py` into the profile repository.

Recommended path:

```text
scripts/vibe_heatmap.py
assets/vibe-heatmap.svg
assets/vibe-heatmap.json
```

## 4) Add GitHub Actions workflow

Create `.github/workflows/vibe-heatmap.yml`:

```yaml
name: vibe-heatmap

on:
  schedule:
    - cron: "8 */6 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Generate heatmap from local logs snapshot
        run: |
          python3 scripts/vibe_heatmap.py \
            --source combined \
            --year "$(date +%Y)" \
            --claude-history data/claude-history.jsonl \
            --codex-history data/codex-history.jsonl \
            --output-svg assets/vibe-heatmap.svg \
            --output-json assets/vibe-heatmap.json \
            --readme README.md \
            --svg-url ./assets/vibe-heatmap.svg

      - name: Commit changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add README.md assets/vibe-heatmap.svg assets/vibe-heatmap.json
          git diff --cached --quiet || git commit -m "chore: refresh vibe heatmap"
          git push
```

## 5) Data source strategy

Use one of these options:

1. Sync `~/.claude/history.jsonl` and `~/.codex/history.jsonl` to `data/` via your own private pipeline.
2. Replace the two history files with exports from other trackers (WakaTime/Wakapi) after adapting fields to timestamps.
3. Run this script locally and push only generated `assets/vibe-heatmap.svg`.

## 6) Local run examples

Claude only:

```bash
python3 scripts/vibe_heatmap.py \
  --source claude \
  --year 2026 \
  --output-svg assets/claude-vibe.svg \
  --output-json assets/claude-vibe.json
```

Codex only:

```bash
python3 scripts/vibe_heatmap.py \
  --source codex \
  --year 2026 \
  --output-svg assets/codex-vibe.svg \
  --output-json assets/codex-vibe.json
```

Combined:

```bash
python3 scripts/vibe_heatmap.py \
  --source combined \
  --year 2026 \
  --output-svg assets/vibe-heatmap.svg \
  --output-json assets/vibe-heatmap.json \
  --readme README.md \
  --svg-url ./assets/vibe-heatmap.svg
```

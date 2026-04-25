---
name: claude-vibe-heatmap
description: Build and maintain a GitHub-style vibe coding heatmap from Claude Code local history (`~/.claude/history.jsonl`), including daily active minutes, session frequency, yearly SVG output, and optional README auto-update. Use when users ask to track Claude coding time/frequency, visualize activity like GitHub contributions, or publish a profile heatmap.
trigger: /vibe
tags:
  - profile
  - github
  - analytics
---

# Claude Vibe Heatmap

Generate a GitHub-style contribution heatmap from Claude Code local history and keep a profile README block updated.

## Slash Command

Command intents:
- `/vibe set github=<username>`: set up the GitHub account/profile repository association with defaults.
- `/vibe set github=<username> repo=<path> auth=ssh name=<git-name> email=<git-email>`: set up the association with explicit values.
- `/vibe set github=<username> auth=https_pat token_env=<ENV_NAME>`: set up HTTPS PAT auth using a token from an environment variable.
- `/vibe config`: show the saved GitHub/profile repository association.
- `/vibe`: generate, update README, commit, and push using the saved association.

Do not ask the user to run shell commands manually. Parse `/vibe` parameters and execute the bundled script internally.

This setup stores:
- GitHub username
- Profile repository local path
- Git author name/email
- Auth mode (`ssh` or `https_pat`)

For `/vibe set`, only `github` is required. Defaults: `repo=$HOME/<github>`, `auth=ssh`, git author name from global git config or `<github>`, and git author email from global git config or `<github>@users.noreply.github.com`.

If `<github>/<github>` does not exist on GitHub, `/vibe set` should try to create that public profile repository automatically before cloning. If `gh` is missing, install it internally through a supported package manager, then fall back to a user-local release install into `$HOME/.local/bin` without sudo. If `gh` is installed but not authenticated, run `gh auth login --hostname github.com --git-protocol ssh` internally, then create the repo with `gh repo create`. If `gh` installation/authentication fails, use `VIBE_GITHUB_TOKEN` or `GITHUB_TOKEN`. If a token is needed, send the user to `https://github.com/settings/tokens/new?scopes=public_repo&description=VibeTrace%20profile%20repo%20setup` and GitHub's PAT docs at `https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens`. Do not ask the user to manually create the repository first unless automated creation fails because credentials are unavailable.

When `/vibe` is used before setup, tell the user to use `/vibe set github=<username>`.

Defaults:
- source: `combined`
- intensity-mode: `sessions`
- year: current year
- action: generate + update README + commit + push
- missing profile `README.md`: create it automatically, then update, commit, and push
- existing profile `README.md`: preserve existing content and add/update only the marker block

Useful overrides:
- `--source claude`
- `--intensity-mode events`
- `--no-push`
- `--no-commit`
- `--show-config`

## Use This Workflow

1. Resolve target scope.
- Claude only: `--source claude`
- Cross-agent: `--source combined`

2. Generate SVG + JSON stats.

```bash
python3 scripts/vibe_heatmap.py \
  --source claude \
  --year "$(date +%Y)" \
  --output-svg assets/claude-vibe-heatmap.svg \
  --output-json assets/claude-vibe-heatmap.json
```

3. Update README marker block when the user wants profile display.

```bash
python3 scripts/vibe_heatmap.py \
  --source claude \
  --year "$(date +%Y)" \
  --output-svg assets/claude-vibe-heatmap.svg \
  --output-json assets/claude-vibe-heatmap.json \
  --readme README.md \
  --svg-url ./assets/claude-vibe-heatmap.svg
```

## Script Behavior

- Read `~/.claude/history.jsonl` by default.
- Parse timestamps from `timestamp`/`ts` fields (ms and sec both supported).
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
If README.md is missing in the profile repository, create it first with a profile heading and the marker block.

## Troubleshooting

- Missing output or all-zero heatmap: verify history file exists and has recent lines.
- Wrong day bucket: pass explicit timezone with `--tz`.
- Session count too high/low: tune `--idle-gap-minutes`.
- Active minutes too high/low: tune `--event-window-minutes`.

## References

- Profile automation recipe: `references/github-profile-workflow.md`

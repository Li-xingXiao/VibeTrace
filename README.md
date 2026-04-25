# VibeTrace

Publish a GitHub profile AI coding heatmap from local vibe coding history.

VibeTrace updates your GitHub profile `README.md` with:

- a GitHub-style activity heatmap
- an overall AI coding tool usage card
- a recent usage card, defaulting to the last 7 days
- safe README updates that only replace the `<!-- vibe-heatmap:start -->` block

Supported built-in labels include Claude, Codex, CodeFuse, OpenCode, CodeBuddy, Antigravity, GitHub Copilot, Cursor, Windsurf, Continue, Aider, Gemini CLI, and Qwen Code. Tools are only shown when local history is detectable or explicitly provided.

## Install

### Claude Code Marketplace

```bash
/plugin marketplace add Li-xingXiao/VibeTrace
/plugin install vibetrace@vibetrace
```

Then run:

```text
/vibe set github=<your-github-username>
/vibe heatmap
```

### Manual Install

```bash
git clone https://github.com/Li-xingXiao/VibeTrace.git
cd VibeTrace
scripts/install.sh --target claude
```

For Codex skill installs:

```bash
scripts/install.sh --target codex
```

To install into both:

```bash
scripts/install.sh --target both
```

Then run:

```text
/vibe set github=<your-github-username>
/vibe heatmap
```

## Usage

Set up the GitHub profile association:

```text
/vibe set github=Li-xingXiao
```

Generate, commit, and push the profile update:

```text
/vibe heatmap
```

Generate only one tool's view:

```text
/vibe heatmap --source codex
/vibe heatmap source=opencode
```

Provide a custom JSON/JSONL history source:

```text
/vibe heatmap source=codebuddy history=~/.codebuddy/history.jsonl
/vibe heatmap source=copilot history=<path-or-glob>
```

Useful options:

```text
/vibe config
/vibe heatmap --no-push
/vibe heatmap --no-commit
/vibe heatmap --recent-days 14
/vibe heatmap --intensity-mode sessions
```

## What `/vibe set` Does

`/vibe set github=<username>` stores the profile association and prepares the GitHub profile repository.

If the `<username>/<username>` profile repo does not exist, VibeTrace tries to create it automatically with GitHub CLI. If GitHub CLI is missing, it attempts an internal install. If API credentials are needed, use a GitHub PAT with public repo creation permission.

PAT link:

```text
https://github.com/settings/tokens/new?scopes=public_repo&description=VibeTrace%20profile%20repo%20setup
```

## Files Written To Your Profile Repo

VibeTrace writes:

```text
README.md
assets/vibe-heatmap.svg
assets/vibe-tools.svg
assets/vibe-tools-recent.svg
assets/vibe-heatmap.json
```

Existing `README.md` content is preserved. Only the VibeTrace marker block is replaced.

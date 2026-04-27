---
name: vibe
description: Handle /vibe and vibe requests for generating a GitHub-style coding heatmap plus AI coding tool usage cards, associating a GitHub profile account/repository, showing saved config, and publishing the results to a GitHub profile README. Use when the user asks for /vibe, /vibe set, /vibe setup, /vibe config, vibe heatmap, vibe tool stats, or GitHub account association for VibeTrace.
trigger: /vibe
tags:
  - profile
  - github
  - analytics
---

# Vibe

This skill owns the user-facing `/vibe` interface. Do not ask the user to run shell commands manually. Collect `/vibe` parameters from the user, then run the installed profile update script internally.

## Command Mapping

- `/vibe set github=<username>`: set up GitHub association using defaults.
- `/vibe set github=<username> repo=<path> auth=ssh name=<git-name> email=<git-email>`: set up GitHub association with explicit values.
- `/vibe set github=<username> auth=https_pat token_env=<ENV_NAME>`: set up HTTPS PAT mode using a token from an environment variable. If `token_env` is omitted, the script checks `VIBE_GITHUB_TOKEN`, then `GITHUB_TOKEN`.
- `/vibe config`: show the saved GitHub/profile repository association.
- `/vibe heatmap`: generate the heatmap plus overall/recent AI coding tool usage cards, create README.md only if missing, preserve any existing profile README content, add/update only the vibe heatmap block, commit, and push.
- `/vibe heatmap --source <tool-id>` or `/vibe heatmap source=<tool-id>`: publish the same profile block filtered to one vibe coding tool.
- `/vibe heatmap source=<tool-id> history=<path-or-glob>`: publish with an extra JSON/JSONL history source for tools that do not have a reliable default history path.
- `/vibe auto`: show auto-publish status (cron schedule and session-start hook).
- `/vibe auto enable`: enable daily auto-publish via system crontab (default: every day at 9am).
- `/vibe auto enable "<cron>"`: enable with a custom cron schedule, e.g. `/vibe auto enable "0 */6 * * *"`.
- `/vibe auto enable daily`: preset — every day at 9am.
- `/vibe auto enable weekly`: preset — every Monday at 9am.
- `/vibe auto enable 6h`: preset — every 6 hours.
- `/vibe auto disable`: remove the auto-publish crontab entry.
- `/vibe sync push`: export local history data and push to the profile repo for cross-device merge.
- `/vibe sync pull`: pull latest sync data from the profile repo and SSH remotes.
- `/vibe sync status`: show device name, synced devices, and registered remotes.
- `/vibe sync remote add <name> <user@host>`: register an SSH remote server for history pull.
- `/vibe sync remote remove <name>`: remove a registered SSH remote.
- `/vibe sync remote list`: list registered SSH remotes.
- `/vibe sync import <file>`: import a history file or device export into the sync directory.
- `/vibe set device=<name>`: set this device's name for cross-device sync (default: hostname).
- `/vibe`: keep as backward-compatible publish behavior, but prefer `/vibe heatmap` in user-facing instructions.

## Behavior

For setup, only `github` is required. Defaults:
- `repo=$HOME/<github>`
- `auth=ssh`
- `name=<github>` when no global git user.name is configured
- `email=<github>@users.noreply.github.com` when no global git user.email is configured

If the GitHub profile repository `<github>/<github>` does not exist, setup should try to create it automatically before cloning. If `gh` is missing, install it internally: first via supported package managers, then via a user-local release install into `$HOME/.local/bin` without sudo. If `gh` is installed but not authenticated, run `gh auth login --hostname github.com --git-protocol ssh` internally, then create the repo with `gh repo create`. If `gh` installation/authentication fails, fall back to `VIBE_GITHUB_TOKEN` or `GITHUB_TOKEN` with repo creation permission. If the user needs a token, point them to `https://github.com/settings/tokens/new?scopes=public_repo&description=VibeTrace%20profile%20repo%20setup` and GitHub's PAT docs at `https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens`.

Core script path: resolve to the first existing path:
- `~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`
- `~/.codex/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`

Internal command mapping:
- Setup: run the resolved core script with `set` plus the parsed key=value arguments.
- Config: run the resolved core script with `config`.
- Publish: run the resolved core script with `heatmap`.
- Tool-specific publish: run the same script with `heatmap --source <tool-id>`; when the user supplies `history=<path-or-glob>`, pass it through as `history=<path-or-glob>` or `--extra-history <tool-id>=<path-or-glob>`.
- Auto commands: run the resolved core script with `auto` plus the sub-command (`enable`, `disable`, or `status`) and optional schedule argument. Preset names `daily`, `weekly`, `6h`, `12h` are accepted alongside raw cron expressions.
- Sync commands: run the resolved core script with `sync` plus the sub-command (`push`, `pull`, `status`, `remote add <name> <host>`, `remote remove <name>`, `remote list`, `import <file> [device=<name>]`). The sync feature uses the profile repo as a sync medium — each device exports to `assets/vibe-sync/<device>.json`, and during heatmap generation all device data is automatically merged.

README safety: never replace an existing profile README wholesale. If the marker block exists, replace only that block. If markers are missing, append the vibe heatmap block to the end. Create a new README only when `README.md` does not exist.

Tool stats: the generator distinguishes detected local histories for Claude, Codex, CodeFuse, OpenCode, and extra JSON/JSONL sources passed as `--extra-history TOOL=PATH_OR_GLOB`. Built-in labels include Claude, Codex, OpenCode, CodeBuddy, CodeFuse, Antigravity, GitHub Copilot, Cursor, Windsurf, Continue, Aider, Gemini CLI, and Qwen Code; only tools with detectable local history are rendered.

If `/vibe set` is missing `github`, ask for the GitHub username and no other field unless needed. If repository creation fails after automatic `gh` installation/authentication and token fallback, ask the user to create a PAT from `https://github.com/settings/tokens/new?scopes=public_repo&description=VibeTrace%20profile%20repo%20setup` and provide it as `VIBE_GITHUB_TOKEN`; do not ask them to manually create the repository first. If `/vibe heatmap` fails because no profile repository is configured, tell the user to use `/vibe set github=<username>`.

## Session-Start Hook

VibeTrace includes a SessionStart hook script (`auto-update-check.sh`) that auto-updates the GitHub profile when a Claude Code session starts, if the last update was more than 24 hours ago. The script is installed alongside the core scripts. To activate it, the user should add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "bash ~/.claude/skills/claude-vibe-heatmap/scripts/auto-update-check.sh"
      }]
    }]
  }
}
```

When the user runs `/vibe auto enable`, mention the session-start hook as a complementary option. If the user wants both, offer to configure the hook in their `~/.claude/settings.json`. Append the `SessionStart` entry to any existing hooks array — never overwrite other hooks.

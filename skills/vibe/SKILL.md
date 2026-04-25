---
name: vibe
description: Handle /vibe and vibe requests for generating a GitHub-style coding heatmap, associating a GitHub profile account/repository, showing saved config, and publishing the heatmap to a GitHub profile README. Use when the user asks for /vibe, /vibe set, /vibe setup, /vibe config, vibe heatmap, or GitHub account association for VibeTrace.
---

# Vibe

This skill owns the user-facing `/vibe` interface. Do not ask the user to run shell commands manually. Collect `/vibe` parameters from the user, then run the installed profile update script internally.

## Command Mapping

- `/vibe set github=<username>`: set up GitHub association using defaults.
- `/vibe set github=<username> repo=<path> auth=ssh name=<git-name> email=<git-email>`: set up GitHub association with explicit values.
- `/vibe set github=<username> auth=https_pat token_env=<ENV_NAME>`: set up HTTPS PAT mode using a token from an environment variable. If `token_env` is omitted, the script checks `VIBE_GITHUB_TOKEN`, then `GITHUB_TOKEN`.
- `/vibe config`: show the saved GitHub/profile repository association.
- `/vibe`: generate the heatmap, create README.md only if missing, preserve any existing profile README content, add/update only the vibe heatmap block, commit, and push.

## Behavior

For setup, only `github` is required. Defaults:
- `repo=$HOME/<github>`
- `auth=ssh`
- `name=<github>` when no global git user.name is configured
- `email=<github>@users.noreply.github.com` when no global git user.email is configured

If the GitHub profile repository `<github>/<github>` does not exist, setup should try to create it automatically before cloning. If `gh` is missing, install it internally: first via supported package managers, then via a user-local release install into `$HOME/.local/bin` without sudo. If `gh` is installed but not authenticated, run `gh auth login --hostname github.com --git-protocol ssh` internally, then create the repo with `gh repo create`. If `gh` installation/authentication fails, fall back to `VIBE_GITHUB_TOKEN` or `GITHUB_TOKEN` with repo creation permission. If the user needs a token, point them to `https://github.com/settings/tokens/new?scopes=public_repo&description=VibeTrace%20profile%20repo%20setup` and GitHub's PAT docs at `https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens`.

Internal command mapping:
- Setup: run `/home/xiaolixing/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh set` plus the parsed key=value arguments.
- Config: run `/home/xiaolixing/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh config`.
- Publish: run `/home/xiaolixing/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh`.

README safety: never replace an existing profile README wholesale. If the marker block exists, replace only that block. If markers are missing, append the vibe heatmap block to the end. Create a new README only when `README.md` does not exist.

If `/vibe set` is missing `github`, ask for the GitHub username and no other field unless needed. If repository creation fails after automatic `gh` installation/authentication and token fallback, ask the user to create a PAT from `https://github.com/settings/tokens/new?scopes=public_repo&description=VibeTrace%20profile%20repo%20setup` and provide it as `VIBE_GITHUB_TOKEN`; do not ask them to manually create the repository first. If `/vibe` fails because no profile repository is configured, tell the user to use `/vibe set github=<username>`.

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEATMAP_SCRIPT="${SCRIPT_DIR}/vibe_heatmap.py"
CONFIG_FILE="${SCRIPT_DIR}/../.vibe-profile.conf"

SAVED_PROFILE_REPO=""
SAVED_GITHUB_USERNAME=""
SAVED_GIT_AUTHOR_NAME=""
SAVED_GIT_AUTHOR_EMAIL=""
SAVED_AUTH_MODE=""

usage() {
  cat <<'EOF'
Usage: run_profile_update.sh [options]
       run_profile_update.sh set [github=USER] [repo=PATH] [auth=ssh|https_pat] [name=NAME] [email=EMAIL]
       run_profile_update.sh config
       run_profile_update.sh heatmap [options]
       run_profile_update.sh auto [enable|disable|status]

Generate vibe heatmap, update profile README marker block, then commit/push.

Options:
  --setup                  One-time interactive GitHub account/repo setup for direct push
  --show-config            Print saved setup config and exit
  --github-username USER   GitHub username for non-interactive setup
  --auth-mode MODE         ssh|https_pat for non-interactive setup
  --git-author-name NAME   Git author name for non-interactive setup
  --git-author-email EMAIL Git author email for non-interactive setup
  --github-token-env NAME  Env var containing PAT for https_pat setup
  --profile-repo PATH      Profile repository path (default: saved config or auto-detect)
  --source MODE            combined or a detected tool id (default: combined)
  --extra-history TOOL=GLOB Add generic JSON/JSONL history source for a tool
  --recent-days DAYS       Days used by the recent tool usage card (default: 7)
  --intensity-mode MODE    minutes|sessions|events (default: sessions)
  --year YYYY              Calendar year (default: current year)
  --tz NAME                Timezone name, e.g. Asia/Hong_Kong
  --no-push                Commit only, do not push
  --no-commit              Generate/update files only
  -h, --help               Show help

Environment:
  VIBE_PROFILE_REPO        Override saved profile repo path
  VIBE_GITHUB_TOKEN        Token used to create GitHub repo or configure HTTPS PAT auth
  GITHUB_TOKEN             Fallback token used to create GitHub repo or configure HTTPS PAT auth

Commands:
  set, setup               Alias for --setup; supports key=value parameters
  config, show-config      Alias for --show-config
  heatmap, publish         Generate/update README, commit, and push
  auto [enable|disable|status]  Manage scheduled auto-publish via system crontab
  auto enable              Enable daily auto-publish (default: 9am)
  auto enable "<cron>"     Enable with custom cron schedule
  auto enable daily        Preset: every day at 9am
  auto enable weekly       Preset: every Monday at 9am
  auto enable 6h           Preset: every 6 hours
  auto disable             Remove auto-publish cron entry
  auto status              Show current auto-publish configuration

Set parameters:
  github=USER, username=USER
  repo=PATH
  auth=ssh|https_pat
  name=NAME
  email=EMAIL
  token_env=NAME           Default: VIBE_GITHUB_TOKEN, then GITHUB_TOKEN

Heatmap key=value parameters:
  source=TOOL              Same as --source TOOL
  history=PATH_OR_GLOB     Add history for the selected source
  extra_history=TOOL=GLOB  Same as --extra-history TOOL=GLOB
  year=YYYY
  intensity=minutes|sessions|events
  recent_days=DAYS
EOF
}

log() {
  printf '[vibe] %s\n' "$*"
}

die() {
  printf '[vibe][error] %s\n' "$*" >&2
  exit 1
}

load_saved_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
    SAVED_PROFILE_REPO="${VIBE_PROFILE_REPO:-}"
    SAVED_GITHUB_USERNAME="${VIBE_GITHUB_USERNAME:-}"
    SAVED_GIT_AUTHOR_NAME="${VIBE_GIT_AUTHOR_NAME:-}"
    SAVED_GIT_AUTHOR_EMAIL="${VIBE_GIT_AUTHOR_EMAIL:-}"
    SAVED_AUTH_MODE="${VIBE_AUTH_MODE:-}"
    SAVED_DEVICE_NAME="${VIBE_DEVICE_NAME:-}"
    SAVED_SYNC_REMOTES="${VIBE_SYNC_REMOTES:-}"
  fi
}

save_config() {
  local repo="$1"
  local username="$2"
  local author_name="$3"
  local author_email="$4"
  local auth_mode="$5"

  mkdir -p "$(dirname "$CONFIG_FILE")"
  {
    printf 'VIBE_PROFILE_REPO=%q\n' "$repo"
    printf 'VIBE_GITHUB_USERNAME=%q\n' "$username"
    printf 'VIBE_GIT_AUTHOR_NAME=%q\n' "$author_name"
    printf 'VIBE_GIT_AUTHOR_EMAIL=%q\n' "$author_email"
    printf 'VIBE_AUTH_MODE=%q\n' "$auth_mode"
    printf 'VIBE_DEVICE_NAME=%q\n' "${VIBE_DEVICE_NAME:-}"
    printf 'VIBE_SYNC_REMOTES=%q\n' "${VIBE_SYNC_REMOTES:-}"
  } > "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"
}

save_full_config() {
  load_saved_config
  save_config \
    "${SAVED_PROFILE_REPO}" \
    "${SAVED_GITHUB_USERNAME}" \
    "${SAVED_GIT_AUTHOR_NAME}" \
    "${SAVED_GIT_AUTHOR_EMAIL}" \
    "${SAVED_AUTH_MODE}"
}

show_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    printf '[vibe] Config file: %s\n' "$CONFIG_FILE"
    cat "$CONFIG_FILE"
  else
    printf '[vibe] No saved config found at %s\n' "$CONFIG_FILE"
  fi
}

expand_home_path() {
  local path="$1"
  case "$path" in
    "~")
      printf '%s\n' "$HOME"
      ;;
    "~/"*)
      printf '%s/%s\n' "$HOME" "${path#~/}"
      ;;
    *)
      printf '%s\n' "$path"
      ;;
  esac
}

prompt_with_default() {
  local label="$1"
  local default_value="$2"
  local out_var="$3"
  local input=""

  if [[ -n "$default_value" ]]; then
    read -r -p "$label [$default_value]: " input || true
  else
    read -r -p "$label: " input || true
  fi

  if [[ -z "$input" ]]; then
    input="$default_value"
  fi

  printf -v "$out_var" '%s' "$input"
}

configure_remote() {
  local repo="$1"
  local remote_url="$2"

  if git -C "$repo" remote get-url origin >/dev/null 2>&1; then
    git -C "$repo" remote set-url origin "$remote_url"
  else
    git -C "$repo" remote add origin "$remote_url"
  fi
}

configure_https_pat_auth() {
  local username="$1"
  local token_env="${2:-}"
  local token=""

  if [[ -n "$token_env" ]]; then
    token="${!token_env:-}"
  fi
  if [[ -z "$token" ]]; then
    token="${VIBE_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}"
  fi
  if [[ -z "$token" ]]; then
    read -r -s -p "GitHub PAT (won't be saved to skill config): " token
    printf '\n'
  fi
  [[ -n "$token" ]] || die "PAT cannot be empty when auth mode is https_pat."

  if [[ -z "$(git config --global credential.helper || true)" ]]; then
    git config --global credential.helper store
    log "Set git credential.helper=store for direct push."
  fi

  printf 'protocol=https\nhost=github.com\nusername=%s\npassword=%s\n\n' "$username" "$token" | git credential approve
}

github_api_token() {
  local token_env="${1:-}"
  local token=""

  if [[ -n "$token_env" ]]; then
    token="${!token_env:-}"
  fi
  if [[ -z "$token" ]]; then
    token="${VIBE_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}"
  fi

  printf '%s\n' "$token"
}

github_repo_exists() {
  local remote_url="$1"

  git ls-remote "$remote_url" HEAD >/dev/null 2>&1
}

run_with_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    command -v sudo >/dev/null 2>&1 || return 1
    sudo -n "$@"
  fi
}

gh_release_arch() {
  case "$(uname -m)" in
    x86_64|amd64)
      printf 'amd64\n'
      ;;
    aarch64|arm64)
      printf 'arm64\n'
      ;;
    armv6l|armv6)
      printf 'armv6\n'
      ;;
    i386|i686)
      printf '386\n'
      ;;
    *)
      return 1
      ;;
  esac
}

install_gh_with_apt() {
  command -v apt-get >/dev/null 2>&1 || return 1
  command -v dpkg >/dev/null 2>&1 || return 1

  log "Installing gh with apt from the official GitHub CLI repository."

  if ! command -v wget >/dev/null 2>&1; then
    run_with_sudo apt-get update
    run_with_sudo apt-get install -y wget
  fi

  run_with_sudo mkdir -p -m 755 /etc/apt/keyrings
  local keyring_tmp
  keyring_tmp="$(mktemp)"
  wget -nv -O "$keyring_tmp" https://cli.github.com/packages/githubcli-archive-keyring.gpg
  run_with_sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg < "$keyring_tmp" >/dev/null
  rm -f "$keyring_tmp"
  run_with_sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  run_with_sudo mkdir -p -m 755 /etc/apt/sources.list.d
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' "$(dpkg --print-architecture)" \
    | run_with_sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  run_with_sudo apt-get update
  run_with_sudo apt-get install -y gh
}

install_gh_user_local() {
  command -v curl >/dev/null 2>&1 || return 1
  command -v tar >/dev/null 2>&1 || return 1

  local arch api_json tag version url tmpdir archive extracted gh_binary
  arch="$(gh_release_arch)" || return 1

  log "Installing gh into user directory: $HOME/.local/bin"

  api_json="$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest)" || return 1
  tag="$(printf '%s\n' "$api_json" | sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  [[ -n "$tag" ]] || return 1
  version="${tag#v}"

  url="$(printf '%s\n' "$api_json" | grep -Eo "https://github.com/cli/cli/releases/download/${tag}/gh_${version}_linux_${arch}\\.tar\\.gz" | head -n 1 || true)"
  if [[ -z "$url" ]]; then
    url="https://github.com/cli/cli/releases/download/${tag}/gh_${version}_linux_${arch}.tar.gz"
  fi

  tmpdir="$(mktemp -d)"
  archive="$tmpdir/gh.tar.gz"
  curl -fsSL -o "$archive" "$url" || {
    rm -rf "$tmpdir"
    return 1
  }
  tar -xzf "$archive" -C "$tmpdir" || {
    rm -rf "$tmpdir"
    return 1
  }

  extracted="$(find "$tmpdir" -type d -name "gh_${version}_linux_${arch}" | head -n 1)"
  gh_binary="$extracted/bin/gh"
  [[ -x "$gh_binary" ]] || {
    rm -rf "$tmpdir"
    return 1
  }

  mkdir -p "$HOME/.local/bin"
  cp "$gh_binary" "$HOME/.local/bin/gh"
  chmod 755 "$HOME/.local/bin/gh"
  rm -rf "$tmpdir"

  export PATH="$HOME/.local/bin:$PATH"
  hash -r 2>/dev/null || true
  command -v gh >/dev/null 2>&1
}

install_gh_if_missing() {
  command -v gh >/dev/null 2>&1 && return 0

  log "gh CLI is not installed. Trying to install it automatically."

  if install_gh_with_apt; then
    command -v gh >/dev/null 2>&1
    return
  fi

  if install_gh_user_local; then
    return 0
  fi

  if command -v brew >/dev/null 2>&1; then
    brew install gh && return 0
  fi

  if command -v dnf >/dev/null 2>&1; then
    run_with_sudo dnf install -y gh && return 0
  fi

  if command -v yum >/dev/null 2>&1; then
    run_with_sudo yum install -y gh && return 0
  fi

  if command -v zypper >/dev/null 2>&1; then
    run_with_sudo zypper --non-interactive install gh && return 0
  fi

  if command -v pacman >/dev/null 2>&1; then
    run_with_sudo pacman -S --noconfirm github-cli && return 0
  fi

  return 1
}

create_github_profile_repo_with_gh() {
  local username="$1"

  install_gh_if_missing || return 1
  if ! gh auth status >/dev/null 2>&1; then
    log "gh CLI is installed but not authenticated. Starting gh auth login."
    gh auth login --hostname github.com --git-protocol ssh
    gh auth status >/dev/null 2>&1 || return 1
  fi

  log "Creating GitHub profile repo with gh: ${username}/${username}"
  gh repo create "${username}/${username}" \
    --public \
    --description "GitHub profile README" >/dev/null
}

create_github_profile_repo_with_api() {
  local username="$1"
  local token_env="${2:-}"
  local token http_status response_file

  command -v curl >/dev/null 2>&1 || return 1

  token="$(github_api_token "$token_env")"
  [[ -n "$token" ]] || return 1

  response_file="$(mktemp)"
  http_status="$(
    curl -sS -o "$response_file" -w '%{http_code}' \
      -X POST \
      -H "Accept: application/vnd.github+json" \
      -H "Authorization: Bearer ${token}" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      https://api.github.com/user/repos \
      -d "{\"name\":\"${username}\",\"description\":\"GitHub profile README\",\"private\":false,\"auto_init\":false}"
  )"

  rm -f "$response_file"
  [[ "$http_status" == "201" ]]
}

ensure_github_profile_repo_exists() {
  local username="$1"
  local remote_url="$2"
  local token_env="${3:-}"

  if github_repo_exists "$remote_url"; then
    return 0
  fi

  log "GitHub profile repo ${username}/${username} was not found. Trying to create it automatically."

  if create_github_profile_repo_with_gh "$username"; then
    return 0
  fi

  if create_github_profile_repo_with_api "$username" "$token_env"; then
    return 0
  fi

  die "Could not create GitHub repo ${username}/${username}. /vibe set tried to install and authenticate gh automatically, then fell back to token-based creation. Create a GitHub PAT at https://github.com/settings/tokens/new?scopes=public_repo&description=VibeTrace%20profile%20repo%20setup and provide it via VIBE_GITHUB_TOKEN or GITHUB_TOKEN, then rerun /vibe set github=${username}. GitHub PAT docs: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens"
}

clone_profile_repo_if_needed() {
  local repo="$1"
  local remote_url="$2"

  if [[ -d "$repo/.git" ]]; then
    return 0
  fi

  if [[ -e "$repo" ]] && [[ ! -d "$repo" ]]; then
    die "Path exists but is not a directory: $repo"
  fi

  if [[ -d "$repo" ]] && [[ -n "$(ls -A "$repo" 2>/dev/null || true)" ]]; then
    die "Directory exists but is not a git repo: $repo"
  fi

  log "Cloning profile repo into $repo"
  git clone "$remote_url" "$repo"
}

auto_detect_profile_repo() {
  local candidates=()
  local git_dir repo origin owner name

  while IFS= read -r git_dir; do
    repo="${git_dir%/.git}"
    origin="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
    if [[ -z "$origin" ]]; then
      continue
    fi

    if [[ "$origin" =~ [:/]([^/:]+)/([^/]+)(\.git)?$ ]]; then
      owner="${BASH_REMATCH[1]}"
      name="${BASH_REMATCH[2]}"
      if [[ "$owner" == "$name" ]]; then
        candidates+=("$repo")
      fi
    fi
  done < <(find "$HOME" -maxdepth 4 -type d -name .git 2>/dev/null)

  if [[ "${#candidates[@]}" -eq 1 ]]; then
    printf '%s\n' "${candidates[0]}"
    return 0
  fi

  if [[ "${#candidates[@]}" -gt 1 ]]; then
    printf '[vibe][error] Found multiple possible profile repos:\n' >&2
    printf '  - %s\n' "${candidates[@]}" >&2
    printf '[vibe][error] Use --profile-repo PATH or run --setup once.\n' >&2
    return 1
  fi

  return 1
}

# ---------------------------------------------------------------------------
# sync: cross-device data sync
# ---------------------------------------------------------------------------

resolve_device_name() {
  if [[ -n "${VIBE_DEVICE_NAME:-}" ]]; then
    printf '%s\n' "$VIBE_DEVICE_NAME"
  elif [[ -n "${SAVED_DEVICE_NAME:-}" ]]; then
    printf '%s\n' "$SAVED_DEVICE_NAME"
  else
    hostname -s 2>/dev/null || hostname
  fi
}

sync_push() {
  load_saved_config
  local profile_repo="${SAVED_PROFILE_REPO:-${PROFILE_REPO:-}}"
  if [[ -z "$profile_repo" ]]; then
    profile_repo="$(auto_detect_profile_repo || true)"
  fi
  [[ -n "$profile_repo" && -d "$profile_repo/.git" ]] || die "Profile repo not configured. Run /vibe set github=<username> first."

  local device
  device="$(resolve_device_name)"
  local sync_dir="$profile_repo/assets/vibe-sync"
  mkdir -p "$sync_dir"

  local cmd=(
    python3 "$HEATMAP_SCRIPT"
    --export-device "$sync_dir/$device.json"
    --device-name "$device"
  )
  for extra in "${EXTRA_HISTORY_ARGS[@]}"; do
    cmd+=(--extra-history "$extra")
  done
  if [[ -n "$TZ_NAME" ]]; then
    cmd+=(--tz "$TZ_NAME")
  fi

  "${cmd[@]}"

  cd "$profile_repo"
  git add "assets/vibe-sync/$device.json"
  if git diff --cached --quiet; then
    log "No changes to sync."
    return 0
  fi
  git commit -m "chore: sync device $device"
  git push
  log "Sync push complete for device '$device'."
}

sync_pull() {
  load_saved_config
  local profile_repo="${SAVED_PROFILE_REPO:-${PROFILE_REPO:-}}"
  if [[ -z "$profile_repo" ]]; then
    profile_repo="$(auto_detect_profile_repo || true)"
  fi
  [[ -n "$profile_repo" && -d "$profile_repo/.git" ]] || die "Profile repo not configured. Run /vibe set github=<username> first."

  log "Pulling latest from profile repo..."
  git -C "$profile_repo" pull --rebase || log "Warning: git pull failed, continuing with local data."

  local remotes="${SAVED_SYNC_REMOTES:-${VIBE_SYNC_REMOTES:-}}"
  if [[ -n "$remotes" ]]; then
    local sync_dir="$profile_repo/assets/vibe-sync"
    mkdir -p "$sync_dir"
    local changed=0
    local IFS=','
    for entry in $remotes; do
      IFS=' '
      local rname="${entry%%=*}"
      local rhost="${entry#*=}"
      if [[ -z "$rname" || -z "$rhost" ]]; then
        log "Skipping invalid remote entry: $entry"
        continue
      fi
      log "Pulling from remote '$rname' ($rhost)..."
      sync_pull_one_remote "$rname" "$rhost" "$sync_dir" && changed=1 || log "Warning: pull from '$rname' had issues."
    done
    if [[ "$changed" -eq 1 ]]; then
      cd "$profile_repo"
      git add assets/vibe-sync/
      if ! git diff --cached --quiet; then
        git commit -m "chore: sync remote devices"
        git push
        log "Remote sync data committed and pushed."
      fi
    fi
  fi
  log "Sync pull complete."
}

sync_pull_one_remote() {
  local name="$1" host="$2" sync_dir="$3"
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  local known_paths=(
    "claude:.claude/history.jsonl"
    "codex:.codex/history.jsonl"
    "codefuse-claude:.codefuse/engine/cc/history.jsonl"
    "codefuse-codex:.codefuse/engine/codex/history.jsonl"
  )
  local extra_args=()
  for spec in "${known_paths[@]}"; do
    local tool="${spec%%:*}"
    local rpath="${spec#*:}"
    scp -q "$host:~/$rpath" "$tmp_dir/${tool}.jsonl" 2>/dev/null || true
  done
  scp -q "$host:~/.claude/stats-cache.json" "$tmp_dir/stats-cache-1.json" 2>/dev/null || true
  scp -q "$host:~/.codefuse/engine/cc/stats-cache.json" "$tmp_dir/stats-cache-2.json" 2>/dev/null || true

  for f in "$tmp_dir"/*.jsonl; do
    [[ -f "$f" && -s "$f" ]] || continue
    local tool_name
    tool_name="$(basename "$f" .jsonl)"
    extra_args+=(--extra-history "$tool_name=$f")
  done

  if [[ ${#extra_args[@]} -eq 0 ]]; then
    log "No history files found on '$name'."
    rm -rf "$tmp_dir"
    return 1
  fi

  local cmd=(
    python3 "$HEATMAP_SCRIPT"
    --no-default-sources
    --export-device "$sync_dir/$name.json"
    --device-name "$name"
    "${extra_args[@]}"
  )
  for sc in "$tmp_dir"/stats-cache-*.json; do
    [[ -f "$sc" && -s "$sc" ]] || continue
    cmd+=(--stats-cache "$sc")
  done
  if [[ -n "$TZ_NAME" ]]; then
    cmd+=(--tz "$TZ_NAME")
  fi

  "${cmd[@]}"
  rm -rf "$tmp_dir"
  return 0
}

sync_remote_add() {
  local name="${1:-}" host="${2:-}"
  [[ -n "$name" ]] || die "Usage: sync remote add <name> <user@host>"
  [[ -n "$host" ]] || die "Usage: sync remote add <name> <user@host>"

  load_saved_config
  local remotes="${SAVED_SYNC_REMOTES:-}"
  local new_entry="$name=$host"
  if [[ -n "$remotes" ]]; then
    local updated=""
    local found=0
    local IFS=','
    for entry in $remotes; do
      IFS=' '
      local ename="${entry%%=*}"
      if [[ "$ename" == "$name" ]]; then
        updated="${updated:+$updated,}$new_entry"
        found=1
      else
        updated="${updated:+$updated,}$entry"
      fi
    done
    if [[ "$found" -eq 0 ]]; then
      updated="${updated:+$updated,}$new_entry"
    fi
    VIBE_SYNC_REMOTES="$updated"
  else
    VIBE_SYNC_REMOTES="$new_entry"
  fi
  save_config \
    "${SAVED_PROFILE_REPO}" \
    "${SAVED_GITHUB_USERNAME}" \
    "${SAVED_GIT_AUTHOR_NAME}" \
    "${SAVED_GIT_AUTHOR_EMAIL}" \
    "${SAVED_AUTH_MODE}"
  log "Remote '$name' ($host) added."
}

sync_remote_remove() {
  local name="${1:-}"
  [[ -n "$name" ]] || die "Usage: sync remote remove <name>"

  load_saved_config
  local remotes="${SAVED_SYNC_REMOTES:-}"
  if [[ -z "$remotes" ]]; then
    log "No remotes configured."
    return 0
  fi
  local updated=""
  local IFS=','
  for entry in $remotes; do
    IFS=' '
    local ename="${entry%%=*}"
    if [[ "$ename" != "$name" ]]; then
      updated="${updated:+$updated,}$entry"
    fi
  done
  VIBE_SYNC_REMOTES="$updated"
  save_config \
    "${SAVED_PROFILE_REPO}" \
    "${SAVED_GITHUB_USERNAME}" \
    "${SAVED_GIT_AUTHOR_NAME}" \
    "${SAVED_GIT_AUTHOR_EMAIL}" \
    "${SAVED_AUTH_MODE}"
  log "Remote '$name' removed."
}

sync_remote_list() {
  load_saved_config
  local remotes="${SAVED_SYNC_REMOTES:-${VIBE_SYNC_REMOTES:-}}"
  if [[ -z "$remotes" ]]; then
    printf '[vibe] No remotes configured.\n'
    return 0
  fi
  printf '[vibe] Registered remotes:\n'
  local IFS=','
  for entry in $remotes; do
    IFS=' '
    local rname="${entry%%=*}"
    local rhost="${entry#*=}"
    printf '  %s  →  %s\n' "$rname" "$rhost"
  done
}

sync_import() {
  local file="${1:-}" device_arg=""
  [[ -n "$file" ]] || die "Usage: sync import <file> [device=<name>]"
  [[ -f "$file" ]] || die "File not found: $file"
  shift

  for arg in "$@"; do
    case "$arg" in
      device=*) device_arg="${arg#device=}" ;;
    esac
  done

  load_saved_config
  local profile_repo="${SAVED_PROFILE_REPO:-${PROFILE_REPO:-}}"
  if [[ -z "$profile_repo" ]]; then
    profile_repo="$(auto_detect_profile_repo || true)"
  fi
  [[ -n "$profile_repo" && -d "$profile_repo/.git" ]] || die "Profile repo not configured."

  local sync_dir="$profile_repo/assets/vibe-sync"
  mkdir -p "$sync_dir"

  if python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('v')==1" "$file" 2>/dev/null; then
    local dev_name="${device_arg:-}"
    if [[ -z "$dev_name" ]]; then
      dev_name="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('device','imported'))" "$file" 2>/dev/null)"
    fi
    cp "$file" "$sync_dir/${dev_name}.json"
    log "Imported device export '${dev_name}' to sync directory."
  else
    local dev_name="${device_arg:-imported}"
    python3 "$HEATMAP_SCRIPT" \
      --no-default-sources \
      --extra-history "unknown=$file" \
      --export-device "$sync_dir/${dev_name}.json" \
      --device-name "$dev_name"
    log "Converted and imported as device '${dev_name}'."
  fi

  cd "$profile_repo"
  git add "assets/vibe-sync/"
  if ! git diff --cached --quiet; then
    git commit -m "chore: import device sync data"
    git push
    log "Import committed and pushed."
  fi
}

sync_status() {
  load_saved_config
  local device
  device="$(resolve_device_name)"
  printf '[vibe] Device name: %s\n' "$device"

  local profile_repo="${SAVED_PROFILE_REPO:-${PROFILE_REPO:-}}"
  if [[ -z "$profile_repo" ]]; then
    profile_repo="$(auto_detect_profile_repo || true)"
  fi
  if [[ -n "$profile_repo" && -d "$profile_repo/.git" ]]; then
    local sync_dir="$profile_repo/assets/vibe-sync"
    if [[ -d "$sync_dir" ]] && ls "$sync_dir"/*.json &>/dev/null; then
      printf '[vibe] Sync directory: %s\n' "$sync_dir"
      for f in "$sync_dir"/*.json; do
        local fname
        fname="$(basename "$f" .json)"
        local size
        size="$(du -h "$f" 2>/dev/null | cut -f1)"
        local mtime
        mtime="$(stat -c '%y' "$f" 2>/dev/null | cut -d. -f1)"
        if [[ "$fname" == "$device" ]]; then
          printf '  %s  %s  %s  (this device)\n' "$fname" "$size" "$mtime"
        else
          printf '  %s  %s  %s\n' "$fname" "$size" "$mtime"
        fi
      done
    else
      printf '[vibe] No sync data found.\n'
    fi
  else
    printf '[vibe] Profile repo not configured.\n'
  fi

  local remotes="${SAVED_SYNC_REMOTES:-${VIBE_SYNC_REMOTES:-}}"
  if [[ -n "$remotes" ]]; then
    printf '[vibe] SSH remotes:\n'
    local IFS=','
    for entry in $remotes; do
      IFS=' '
      local rname="${entry%%=*}"
      local rhost="${entry#*=}"
      printf '  %s  →  %s\n' "$rname" "$rhost"
    done
  fi
}

CRON_TAG="# vibetrace-auto"

resolve_auto_schedule() {
  local input="$1"
  case "$input" in
    daily)       printf '0 9 * * *\n' ;;
    weekly)      printf '0 9 * * 1\n' ;;
    6h)          printf '0 */6 * * *\n' ;;
    12h)         printf '0 */12 * * *\n' ;;
    *)           printf '%s\n' "$input" ;;
  esac
}

auto_cron_line() {
  local schedule="$1"
  local script_path
  script_path="$(cd "$SCRIPT_DIR" && pwd)/run_profile_update.sh"
  printf '%s bash %s heatmap %s\n' "$schedule" "$script_path" "$CRON_TAG"
}

auto_enable() {
  local raw_schedule="${1:-daily}"
  local schedule
  schedule="$(resolve_auto_schedule "$raw_schedule")"

  [[ -n "$SAVED_PROFILE_REPO" ]] || die "No profile configured. Run /vibe set github=<username> first."
  [[ -d "$SAVED_PROFILE_REPO/.git" ]] || die "Profile repo not found at $SAVED_PROFILE_REPO. Run /vibe set github=<username> first."

  local new_line
  new_line="$(auto_cron_line "$schedule")"
  ( crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true ; printf '%s\n' "$new_line" ) | crontab -
  log "Auto-publish enabled."
  log "Schedule: $schedule"
  log "Cron entry: $new_line"
}

auto_disable() {
  if crontab -l 2>/dev/null | grep -q "$CRON_TAG"; then
    ( crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true ) | crontab -
    log "Auto-publish disabled. Cron entry removed."
  else
    log "No auto-publish cron entry found."
  fi
}

auto_status() {
  local entry
  entry="$(crontab -l 2>/dev/null | grep "$CRON_TAG" || true)"
  if [[ -n "$entry" ]]; then
    log "Auto-publish is ENABLED"
    log "Schedule: $entry"
  else
    log "Auto-publish is DISABLED (no cron entry found)"
  fi

  local hook_script="$SCRIPT_DIR/auto-update-check.sh"
  if [[ -f "$hook_script" ]]; then
    local last_file="$SCRIPT_DIR/../.last-auto-update"
    if [[ -f "$last_file" ]]; then
      local last_ts now elapsed hours
      last_ts="$(cat "$last_file" 2>/dev/null || echo 0)"
      now="$(date +%s)"
      elapsed=$(( now - last_ts ))
      hours=$(( elapsed / 3600 ))
      log "Session-start hook: installed (last update ${hours}h ago)"
    else
      log "Session-start hook: installed (never triggered)"
    fi
  else
    log "Session-start hook: not installed"
  fi
}

run_setup() {
  local github_username="${SETUP_GITHUB_USERNAME:-${SAVED_GITHUB_USERNAME:-}}"
  local auth_mode="${SETUP_AUTH_MODE:-${SAVED_AUTH_MODE:-ssh}}"
  local profile_repo="${SETUP_PROFILE_REPO:-${PROFILE_REPO:-${SAVED_PROFILE_REPO:-}}}"
  local author_name="${SETUP_GIT_AUTHOR_NAME:-${SAVED_GIT_AUTHOR_NAME:-$(git config --global user.name || true)}}"
  local author_email="${SETUP_GIT_AUTHOR_EMAIL:-${SAVED_GIT_AUTHOR_EMAIL:-$(git config --global user.email || true)}}"
  local remote_url=""

  printf '[vibe] GitHub profile setup for direct push\n'

  if [[ "$SETUP_NONINTERACTIVE" -eq 0 ]]; then
    prompt_with_default "GitHub username" "$github_username" github_username
  fi
  [[ -n "$github_username" ]] || die "GitHub username is required."

  if [[ "$SETUP_NONINTERACTIVE" -eq 0 ]]; then
    prompt_with_default "Auth mode (ssh or https_pat)" "$auth_mode" auth_mode
  fi
  case "$auth_mode" in
    ssh|https_pat) ;;
    *) die "Invalid auth mode: $auth_mode" ;;
  esac

  if [[ -z "$profile_repo" ]]; then
    profile_repo="$HOME/$github_username"
  fi
  profile_repo="$(expand_home_path "$profile_repo")"
  if [[ "$SETUP_NONINTERACTIVE" -eq 0 ]]; then
    prompt_with_default "Profile repository local path" "$profile_repo" profile_repo
  fi
  profile_repo="$(expand_home_path "$profile_repo")"
  [[ -n "$profile_repo" ]] || die "Profile repository path is required."

  if [[ -z "$author_name" ]]; then
    author_name="$github_username"
  fi
  if [[ "$SETUP_NONINTERACTIVE" -eq 0 ]]; then
    prompt_with_default "Git author name" "$author_name" author_name
  fi
  [[ -n "$author_name" ]] || die "Git author name is required."

  if [[ -z "$author_email" ]]; then
    author_email="${github_username}@users.noreply.github.com"
  fi
  if [[ "$SETUP_NONINTERACTIVE" -eq 0 ]]; then
    prompt_with_default "Git author email" "$author_email" author_email
  fi
  [[ -n "$author_email" ]] || die "Git author email is required."

  if [[ "$auth_mode" == "ssh" ]]; then
    remote_url="git@github.com:${github_username}/${github_username}.git"
  else
    remote_url="https://github.com/${github_username}/${github_username}.git"
  fi

  if [[ ! -d "$profile_repo/.git" ]]; then
    ensure_github_profile_repo_exists "$github_username" "$remote_url" "$SETUP_GITHUB_TOKEN_ENV"
    clone_profile_repo_if_needed "$profile_repo" "$remote_url"
  fi
  [[ -d "$profile_repo/.git" ]] || die "Not a git repository: $profile_repo"

  configure_remote "$profile_repo" "$remote_url"

  git -C "$profile_repo" config user.name "$author_name"
  git -C "$profile_repo" config user.email "$author_email"

  if [[ "$auth_mode" == "https_pat" ]]; then
    configure_https_pat_auth "$github_username" "$SETUP_GITHUB_TOKEN_ENV"
  fi

  save_config "$profile_repo" "$github_username" "$author_name" "$author_email" "$auth_mode"

  log "Setup complete."
  log "Saved config: $CONFIG_FILE"
  log "Next run: /vibe heatmap"
}

apply_setup_assignment() {
  local raw="$1"
  local key="${raw%%=*}"
  local value="${raw#*=}"

  [[ "$raw" == *=* ]] || die "Expected key=value setup parameter, got: $raw"
  SETUP_NONINTERACTIVE=1

  case "$key" in
    github|username|github_username)
      SETUP_GITHUB_USERNAME="$value"
      ;;
    repo|profile_repo|profile-repo)
      SETUP_PROFILE_REPO="$(expand_home_path "$value")"
      PROFILE_REPO="$value"
      ;;
    auth|auth_mode|auth-mode)
      SETUP_AUTH_MODE="$value"
      ;;
    name|author_name|git_author_name|git-author-name)
      SETUP_GIT_AUTHOR_NAME="$value"
      ;;
    email|author_email|git_author_email|git-author-email)
      SETUP_GIT_AUTHOR_EMAIL="$value"
      ;;
    token_env|token-env|github_token_env|github-token-env)
      SETUP_GITHUB_TOKEN_ENV="$value"
      ;;
    device|device_name|device-name)
      VIBE_DEVICE_NAME="$value"
      ;;
    *)
      die "Unknown setup parameter: $key"
      ;;
  esac
}

apply_heatmap_assignment() {
  local raw="$1"
  local key="${raw%%=*}"
  local value="${raw#*=}"

  [[ "$raw" == *=* ]] || die "Expected key=value heatmap parameter, got: $raw"

  case "$key" in
    source)
      SOURCE="$value"
      ;;
    history|history_glob|history-glob)
      HEATMAP_HISTORY_GLOB="$value"
      ;;
    extra_history|extra-history)
      EXTRA_HISTORY_ARGS+=("$value")
      ;;
    year)
      YEAR="$value"
      ;;
    intensity|intensity_mode|intensity-mode)
      INTENSITY_MODE="$value"
      ;;
    recent_days|recent-days)
      RECENT_DAYS="$value"
      ;;
    tz)
      TZ_NAME="$value"
      ;;
    *)
      die "Unknown heatmap parameter: $key"
      ;;
  esac
}

load_saved_config

PROFILE_REPO="${VIBE_PROFILE_REPO:-${SAVED_PROFILE_REPO:-}}"
SOURCE="combined"
INTENSITY_MODE="sessions"
YEAR="$(date +%Y)"
TZ_NAME=""
RECENT_DAYS="7"
NO_PUSH=0
NO_COMMIT=0
PUBLISH_MODE=0
SETUP_MODE=0
SHOW_CONFIG=0
AUTO_MODE=0
SETUP_NONINTERACTIVE=0
SETUP_GITHUB_USERNAME=""
SETUP_AUTH_MODE=""
SETUP_PROFILE_REPO=""
SETUP_GIT_AUTHOR_NAME=""
SETUP_GIT_AUTHOR_EMAIL=""
SETUP_GITHUB_TOKEN_ENV=""
HEATMAP_HISTORY_GLOB=""
EXTRA_HISTORY_ARGS=()
AUTO_ARGS=()
SYNC_MODE=0
SYNC_ARGS=()

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    set|setup)
      SETUP_MODE=1
      shift
      ;;
    config|show-config)
      SHOW_CONFIG=1
      shift
      ;;
    heatmap|publish|generate)
      PUBLISH_MODE=1
      shift
      ;;
    auto)
      AUTO_MODE=1
      shift
      ;;
    sync)
      SYNC_MODE=1
      shift
      ;;
    --setup)
      SETUP_MODE=1
      shift
      ;;
    --show-config)
      SHOW_CONFIG=1
      shift
      ;;
    --github-username|--username)
      SETUP_MODE=1
      SETUP_NONINTERACTIVE=1
      SETUP_GITHUB_USERNAME="${2:-}"
      shift 2
      ;;
    --auth-mode)
      SETUP_MODE=1
      SETUP_NONINTERACTIVE=1
      SETUP_AUTH_MODE="${2:-}"
      shift 2
      ;;
    --git-author-name)
      SETUP_MODE=1
      SETUP_NONINTERACTIVE=1
      SETUP_GIT_AUTHOR_NAME="${2:-}"
      shift 2
      ;;
    --git-author-email)
      SETUP_MODE=1
      SETUP_NONINTERACTIVE=1
      SETUP_GIT_AUTHOR_EMAIL="${2:-}"
      shift 2
      ;;
    --github-token-env)
      SETUP_MODE=1
      SETUP_NONINTERACTIVE=1
      SETUP_GITHUB_TOKEN_ENV="${2:-}"
      shift 2
      ;;
    --profile-repo)
      PROFILE_REPO="${2:-}"
      if [[ "$SETUP_MODE" -eq 1 ]]; then
        SETUP_NONINTERACTIVE=1
        SETUP_PROFILE_REPO="$PROFILE_REPO"
      fi
      shift 2
      ;;
    --source)
      SOURCE="${2:-}"
      shift 2
      ;;
    --extra-history)
      EXTRA_HISTORY_ARGS+=("${2:-}")
      shift 2
      ;;
    --recent-days)
      RECENT_DAYS="${2:-}"
      shift 2
      ;;
    --intensity-mode)
      INTENSITY_MODE="${2:-}"
      shift 2
      ;;
    --year)
      YEAR="${2:-}"
      shift 2
      ;;
    --tz)
      TZ_NAME="${2:-}"
      shift 2
      ;;
    --no-push)
      NO_PUSH=1
      shift
      ;;
    --no-commit)
      NO_COMMIT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *=*)
      if [[ "$SETUP_MODE" -eq 1 ]]; then
        apply_setup_assignment "$1"
        shift
      elif [[ "$SYNC_MODE" -eq 1 ]]; then
        SYNC_ARGS+=("$1")
        shift
      else
        PUBLISH_MODE=1
        apply_heatmap_assignment "$1"
        shift
      fi
      ;;
    *)
      if [[ "$AUTO_MODE" -eq 1 ]]; then
        AUTO_ARGS+=("$1")
        shift
      elif [[ "$SYNC_MODE" -eq 1 ]]; then
        SYNC_ARGS+=("$1")
        shift
      else
        die "Unknown option: $1"
      fi
      ;;
  esac
done

if [[ "$SHOW_CONFIG" -eq 1 ]]; then
  show_config
  exit 0
fi

if [[ "$SETUP_MODE" -eq 1 ]]; then
  run_setup
  exit 0
fi

if [[ "$AUTO_MODE" -eq 1 ]]; then
  local_auto_sub="${AUTO_ARGS[0]:-status}"
  case "$local_auto_sub" in
    enable|setup)
      auto_enable "${AUTO_ARGS[1]:-daily}"
      ;;
    disable|remove)
      auto_disable
      ;;
    status|"")
      auto_status
      ;;
    *)
      auto_enable "$local_auto_sub"
      ;;
  esac
  exit 0
fi

if [[ "$SYNC_MODE" -eq 1 ]]; then
  local_sync_sub="${SYNC_ARGS[0]:-status}"
  case "$local_sync_sub" in
    push)
      sync_push
      ;;
    pull)
      sync_pull
      ;;
    status|"")
      sync_status
      ;;
    remote)
      local_remote_action="${SYNC_ARGS[1]:-list}"
      case "$local_remote_action" in
        add)
          sync_remote_add "${SYNC_ARGS[2]:-}" "${SYNC_ARGS[3]:-}"
          ;;
        remove|rm)
          sync_remote_remove "${SYNC_ARGS[2]:-}"
          ;;
        list|"")
          sync_remote_list
          ;;
        *)
          die "Unknown sync remote action: $local_remote_action"
          ;;
      esac
      ;;
    import)
      sync_import "${SYNC_ARGS[@]:1}"
      ;;
    *)
      die "Unknown sync action: $local_sync_sub (expected: push, pull, status, remote, import)"
      ;;
  esac
  exit 0
fi

case "$SOURCE" in
  claude|codex|combined|codefuse|codefuse-codex|codefuse-claude|codebuddy|opencode|antigravity|copilot|cursor|windsurf|continue|aider|gemini-cli|qwen-code) ;;
  *) die "Invalid --source: $SOURCE" ;;
esac

case "$INTENSITY_MODE" in
  minutes|sessions|events) ;;
  *) die "Invalid --intensity-mode: $INTENSITY_MODE" ;;
esac

if [[ -n "$HEATMAP_HISTORY_GLOB" ]]; then
  EXTRA_HISTORY_ARGS+=("${SOURCE}=${HEATMAP_HISTORY_GLOB}")
fi

if [[ -z "$PROFILE_REPO" ]]; then
  PROFILE_REPO="$(auto_detect_profile_repo || true)"
fi

if [[ -z "$PROFILE_REPO" ]]; then
  die "Profile repo is not configured. Run /vibe set github=<username> first, then run /vibe heatmap."
fi

[[ -d "$PROFILE_REPO/.git" ]] || die "Not a git repository: $PROFILE_REPO"

README_PATH="$PROFILE_REPO/README.md"
if [[ ! -f "$README_PATH" ]]; then
  log "README.md not found in profile repo. Creating a profile README."
  cat > "$README_PATH" <<EOF
# Hey, I'm ${SAVED_GITHUB_USERNAME:-$(basename "$PROFILE_REPO")}

I turn prompts, half-formed ideas, and late-night curiosity into commits.
This profile is part lab notebook, part shipping log, part proof that the side quest got serious.

<!-- vibe-heatmap:start -->
<!-- vibe heatmap will be inserted here -->
<!-- vibe-heatmap:end -->
EOF
fi

ASSETS_DIR="$PROFILE_REPO/assets"
mkdir -p "$ASSETS_DIR"

SVG_PATH="$ASSETS_DIR/vibe-heatmap.svg"
TOOLS_SVG_PATH="$ASSETS_DIR/vibe-tools.svg"
RECENT_TOOLS_SVG_PATH="$ASSETS_DIR/vibe-tools-recent.svg"
TOKEN_SVG_PATH="$ASSETS_DIR/vibe-tokens.svg"
SCORECARD_SVG_PATH="$ASSETS_DIR/vibe-scorecard.svg"
BADGES_SVG_PATH="$ASSETS_DIR/vibe-badges.svg"
JSON_PATH="$ASSETS_DIR/vibe-heatmap.json"

cmd=(
  python3 "$HEATMAP_SCRIPT"
  --source "$SOURCE"
  --year "$YEAR"
  --intensity-mode "$INTENSITY_MODE"
  --output-svg "$SVG_PATH"
  --output-tools-svg "$TOOLS_SVG_PATH"
  --output-recent-tools-svg "$RECENT_TOOLS_SVG_PATH"
  --output-token-svg "$TOKEN_SVG_PATH"
  --output-scorecard-svg "$SCORECARD_SVG_PATH"
  --output-badges-svg "$BADGES_SVG_PATH"
  --output-json "$JSON_PATH"
  --readme "$README_PATH"
  --svg-url "./assets/vibe-heatmap.svg"
  --tools-svg-url "./assets/vibe-tools.svg"
  --recent-tools-svg-url "./assets/vibe-tools-recent.svg"
  --token-svg-url "./assets/vibe-tokens.svg"
  --scorecard-svg-url "./assets/vibe-scorecard.svg"
  --badges-svg-url "./assets/vibe-badges.svg"
  --recent-days "$RECENT_DAYS"
)

for extra_history in "${EXTRA_HISTORY_ARGS[@]}"; do
  cmd+=(--extra-history "$extra_history")
done

if [[ -n "$TZ_NAME" ]]; then
  cmd+=(--tz "$TZ_NAME")
fi

SYNC_DIR="$PROFILE_REPO/assets/vibe-sync"
if [[ -d "$SYNC_DIR" ]] && ls "$SYNC_DIR"/*.json &>/dev/null; then
  DEVICE_NAME="$(resolve_device_name)"
  cmd+=(--import-devices "$SYNC_DIR" --device-name "$DEVICE_NAME")
fi

log "Generating heatmap and updating README in: $PROFILE_REPO"
"${cmd[@]}"

if [[ "$NO_COMMIT" -eq 1 ]]; then
  log "Skipping commit/push (--no-commit)."
  exit 0
fi

cd "$PROFILE_REPO"

if [[ -z "$(git status --porcelain -- README.md assets/vibe-heatmap.svg assets/vibe-tools.svg assets/vibe-tools-recent.svg assets/vibe-tokens.svg assets/vibe-scorecard.svg assets/vibe-badges.svg assets/vibe-heatmap.json)" ]]; then
  log "No file changes detected. Nothing to commit."
  exit 0
fi

git add README.md assets/vibe-heatmap.svg assets/vibe-tools.svg assets/vibe-tools-recent.svg assets/vibe-tokens.svg assets/vibe-scorecard.svg assets/vibe-badges.svg assets/vibe-heatmap.json

git commit -m "chore: update vibe heatmap (${YEAR}, ${SOURCE}, ${INTENSITY_MODE})"

if [[ "$NO_PUSH" -eq 1 ]]; then
  log "Commit created, push skipped (--no-push)."
  exit 0
fi

git push
log "Done: committed and pushed profile update."

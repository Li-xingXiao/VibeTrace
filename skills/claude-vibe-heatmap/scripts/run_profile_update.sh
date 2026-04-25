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
  --source MODE            claude|codex|combined (default: combined)
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

Set parameters:
  github=USER, username=USER
  repo=PATH
  auth=ssh|https_pat
  name=NAME
  email=EMAIL
  token_env=NAME           Default: VIBE_GITHUB_TOKEN, then GITHUB_TOKEN
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
  } > "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"
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

  ensure_github_profile_repo_exists "$github_username" "$remote_url" "$SETUP_GITHUB_TOKEN_ENV"
  clone_profile_repo_if_needed "$profile_repo" "$remote_url"
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
  log "Next run: /vibe"
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
    *)
      die "Unknown setup parameter: $key"
      ;;
  esac
}

load_saved_config

PROFILE_REPO="${VIBE_PROFILE_REPO:-${SAVED_PROFILE_REPO:-}}"
SOURCE="combined"
INTENSITY_MODE="sessions"
YEAR="$(date +%Y)"
TZ_NAME=""
NO_PUSH=0
NO_COMMIT=0
SETUP_MODE=0
SHOW_CONFIG=0
SETUP_NONINTERACTIVE=0
SETUP_GITHUB_USERNAME=""
SETUP_AUTH_MODE=""
SETUP_PROFILE_REPO=""
SETUP_GIT_AUTHOR_NAME=""
SETUP_GIT_AUTHOR_EMAIL=""
SETUP_GITHUB_TOKEN_ENV=""

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
      else
        die "Unexpected key=value parameter outside setup mode: $1"
      fi
      ;;
    *)
      die "Unknown option: $1"
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

case "$SOURCE" in
  claude|codex|combined) ;;
  *) die "Invalid --source: $SOURCE" ;;
esac

case "$INTENSITY_MODE" in
  minutes|sessions|events) ;;
  *) die "Invalid --intensity-mode: $INTENSITY_MODE" ;;
esac

if [[ -z "$PROFILE_REPO" ]]; then
  PROFILE_REPO="$(auto_detect_profile_repo || true)"
fi

if [[ -z "$PROFILE_REPO" ]]; then
  die "Profile repo is not configured. Run /vibe set, or run: bash ~/.claude/skills/claude-vibe-heatmap/scripts/run_profile_update.sh --setup"
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
JSON_PATH="$ASSETS_DIR/vibe-heatmap.json"

cmd=(
  python3 "$HEATMAP_SCRIPT"
  --source "$SOURCE"
  --year "$YEAR"
  --intensity-mode "$INTENSITY_MODE"
  --output-svg "$SVG_PATH"
  --output-json "$JSON_PATH"
  --readme "$README_PATH"
  --svg-url "./assets/vibe-heatmap.svg"
)

if [[ -n "$TZ_NAME" ]]; then
  cmd+=(--tz "$TZ_NAME")
fi

log "Generating heatmap and updating README in: $PROFILE_REPO"
"${cmd[@]}"

if [[ "$NO_COMMIT" -eq 1 ]]; then
  log "Skipping commit/push (--no-commit)."
  exit 0
fi

cd "$PROFILE_REPO"

if [[ -z "$(git status --porcelain -- README.md assets/vibe-heatmap.svg assets/vibe-heatmap.json)" ]]; then
  log "No file changes detected. Nothing to commit."
  exit 0
fi

git add README.md assets/vibe-heatmap.svg assets/vibe-heatmap.json

git commit -m "chore: update vibe heatmap (${YEAR}, ${SOURCE}, ${INTENSITY_MODE})"

if [[ "$NO_PUSH" -eq 1 ]]; then
  log "Commit created, push skipped (--no-push)."
  exit 0
fi

git push
log "Done: committed and pushed profile update."

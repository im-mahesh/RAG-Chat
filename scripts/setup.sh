#!/usr/bin/env bash
# One-shot setup for DocChat on a fresh macOS or Linux machine. Safe to re-run.
#
# Installs (only what is missing): uv (+ Python 3.12), Node, pnpm, then the
# project's dependencies, a .env file, and the embedding model.
#
#   bash scripts/setup.sh [--skip-model] [--no-profile]
#
#   --skip-model   don't pre-download the embedding model (~90 MB)
#   --no-profile   don't add the tool directories to your shell profile
set -euo pipefail

NODE_VERSION="${NODE_VERSION:-24.22.2}"
NODE_PREFIX="${NODE_PREFIX:-$HOME/.local/node}"
BIN_DIR="$HOME/.local/bin"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGINAL_PATH="$PATH"
SKIP_MODEL=0
SKIP_PROFILE=0

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --skip-model) SKIP_MODEL=1 ;;
      --no-profile) SKIP_PROFILE=1 ;;
      -h | --help) sed -n '2,11p' "${BASH_SOURCE[0]}"; exit 0 ;;
      *) die "unknown option: $arg (try --help)" ;;
    esac
  done
}

check_prerequisites() {
  have curl || die "curl is required but not installed."
  have tar || die "tar is required but not installed."
  case "$(uname -s)" in Darwin | Linux) ;; *) die "unsupported OS: $(uname -s)" ;; esac
  have git || warn "git not found. On macOS run: xcode-select --install"
}

install_uv() {
  if have uv; then
    log "uv already installed ($(uv --version))"
    return
  fi
  log "Installing uv (official installer from astral.sh)"
  curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh
  export PATH="$BIN_DIR:$PATH"
  have uv || die "uv installed but not found on PATH."
}

node_is_recent() {
  have node || return 1
  [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ]
}

node_platform() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$(uname -m)" in
    arm64 | aarch64) arch=arm64 ;;
    x86_64 | amd64) arch=x64 ;;
    *) die "unsupported CPU architecture: $(uname -m)" ;;
  esac
  echo "$os-$arch"
}

sha256_of() {
  if have shasum; then shasum -a 256 "$1" | cut -d' ' -f1; else sha256sum "$1" | cut -d' ' -f1; fi
}

install_node() {
  if node_is_recent; then
    log "Node already installed ($(node -v))"
    return
  fi
  local name base expected
  name="node-v$NODE_VERSION-$(node_platform)"
  base="https://nodejs.org/dist/v$NODE_VERSION"
  tmp="$(mktemp -d)" # global so the EXIT trap can still see it
  trap 'rm -rf "${tmp:-}"' EXIT
  log "Installing Node $NODE_VERSION into $NODE_PREFIX (official build from nodejs.org)"
  curl -fsSL -o "$tmp/node.tar.gz" "$base/$name.tar.gz"
  expected="$(curl -fsSL "$base/SHASUMS256.txt" | grep " $name.tar.gz\$" | cut -d' ' -f1)"
  [ -n "$expected" ] || die "could not find the checksum for $name.tar.gz"
  [ "$(sha256_of "$tmp/node.tar.gz")" = "$expected" ] || die "checksum mismatch for $name.tar.gz"
  mkdir -p "$NODE_PREFIX"
  tar -xzf "$tmp/node.tar.gz" -C "$NODE_PREFIX" --strip-components=1
  export PATH="$NODE_PREFIX/bin:$PATH"
  node_is_recent || die "Node install failed."
}

install_pnpm() {
  if have pnpm; then
    log "pnpm already installed ($(pnpm -v))"
    return
  fi
  have corepack || die "corepack not found; install pnpm manually: https://pnpm.io/installation"
  log "Enabling pnpm via corepack"
  COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack enable pnpm
  COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm -v >/dev/null
}

install_dependencies() {
  log "Installing JavaScript dependencies"
  (cd "$REPO_ROOT" && pnpm install --frozen-lockfile)
  log "Installing Python dependencies (uv also fetches Python 3.12 if needed)"
  (cd "$REPO_ROOT/apps/api" && uv sync --frozen)
}

create_env_file() {
  if [ -f "$REPO_ROOT/.env" ]; then
    log ".env already exists; leaving it alone"
    return
  fi
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  log "Created .env from .env.example (add your ANTHROPIC_API_KEY to it)"
}

prefetch_model() {
  if [ "$SKIP_MODEL" -eq 1 ]; then
    log "Skipping embedding model download (--skip-model); it downloads on first API start"
    return
  fi
  log "Downloading the embedding model (all-MiniLM-L6-v2, ~90 MB, cached afterwards)"
  (cd "$REPO_ROOT/apps/api" && uv run python -c "from app import ingest; ingest.get_model(); print('model ready')")
}

path_entries_needed() {
  local dir
  for dir in "$NODE_PREFIX/bin" "$BIN_DIR"; do
    if [ -d "$dir" ] && [[ ":$ORIGINAL_PATH:" != *":$dir:"* ]]; then
      printf '%s\n' "$dir"
    fi
  done
}

profile_file() {
  case "$(basename "${SHELL:-}")" in
    zsh) echo "$HOME/.zshrc" ;;
    bash) if [ "$(uname -s)" = Darwin ]; then echo "$HOME/.bash_profile"; else echo "$HOME/.bashrc"; fi ;;
    *) echo "" ;;
  esac
}

update_shell_profile() {
  local dirs profile line
  dirs="$(path_entries_needed | paste -sd: -)"
  [ -n "$dirs" ] || return 0
  line="export PATH=\"$dirs:\$PATH\"  # added by docchat setup"
  profile="$(profile_file)"
  if [ "$SKIP_PROFILE" -eq 1 ] || [ -z "$profile" ]; then
    log "Add this line to your shell profile so new terminals find the tools:"
    echo "  $line"
  elif grep -qF "added by docchat setup" "$profile" 2>/dev/null; then
    log "Shell profile already updated ($profile)"
  else
    printf '\n%s\n' "$line" >>"$profile"
    log "Added the tools to your PATH in $profile (open a new terminal to pick it up)"
  fi
}

print_next_steps() {
  cat <<EOF

Setup complete.

Next steps:
  1. Put your key in .env:   ANTHROPIC_API_KEY=...
  2. Start both servers:     pnpm dev
  3. Open:                   http://localhost:5173
EOF
}

main() {
  parse_args "$@"
  export PATH="$NODE_PREFIX/bin:$BIN_DIR:$PATH"
  check_prerequisites
  install_uv
  install_node
  install_pnpm
  install_dependencies
  create_env_file
  prefetch_model
  update_shell_profile
  print_next_steps
}

main "$@"

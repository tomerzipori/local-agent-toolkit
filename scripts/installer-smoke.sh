#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

export HOME="$TMP_DIR/home"
export PATH="$HOME/.local/bin:$PATH"

EXPECTED_VERSION="$(python3 "$ROOT/scripts/read_version.py")"
INSTALLER="$ROOT/install.sh"
PUBLIC_BIN="$HOME/.local/bin/local-agent"
MANAGED_ROOT="$HOME/.local/share/local-agent-toolkit"
CONFIG_PATH="$HOME/.config/local-agent/config.json"
ZSHRC="$HOME/.zshrc"

mkdir -p "$HOME"

bash "$INSTALLER" --instructions none
test -x "$PUBLIC_BIN"
command -v local-agent >/dev/null
test "$(local-agent --version)" = "local-agent $EXPECTED_VERSION"

bash "$INSTALLER" --instructions none

mkdir -p "$(dirname "$CONFIG_PATH")"
printf '{"model":"saved"}\n' > "$CONFIG_PATH"

bash "$INSTALLER" --uninstall
test ! -e "$PUBLIC_BIN"
test ! -e "$MANAGED_ROOT"
test -f "$CONFIG_PATH"
if [ -f "$ZSHRC" ]; then
    if grep -Fq 'BEGIN LOCAL-AGENT TOOLKIT PATH' "$ZSHRC"; then
        exit 1
    fi
fi

bash "$INSTALLER" --instructions none
bash "$INSTALLER" --uninstall --purge-config
test ! -e "$PUBLIC_BIN"
test ! -e "$MANAGED_ROOT"
test ! -e "$HOME/.config/local-agent"

mkdir -p "$(dirname "$PUBLIC_BIN")"
printf 'foreign command\n' > "$PUBLIC_BIN"
set +e
COLLISION_OUTPUT="$(bash "$INSTALLER" --instructions none 2>&1)"
STATUS=$?
set -e
test "$STATUS" -ne 0
printf '%s' "$COLLISION_OUTPUT" | grep -F "Refusing to replace existing path:"

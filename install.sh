#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
TARGET="${BIN_DIR}/local-agent"
ZSHRC="${HOME}/.zshrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$TARGET"
    printf 'Removed %s (configuration was kept).\n' "$TARGET"
    exit 0
fi

if [ "$#" -ne 0 ]; then
    printf 'Usage: %s [--uninstall]\n' "$0" >&2
    exit 2
fi

mkdir -p "$BIN_DIR"
cp "$SOURCE_DIR/bin/local-agent" "$TARGET"
chmod +x "$TARGET"

if ! grep -Fq "$PATH_LINE" "$ZSHRC" 2>/dev/null; then
    printf '\n# Local Agent toolkit\n%s\n' "$PATH_LINE" >> "$ZSHRC"
fi

printf 'Installed %s\n' "$TARGET"
printf 'Open a new shell or run: source ~/.zshrc\n'
if [ -t 0 ] && [ -t 1 ]; then
    "$TARGET" configure || printf 'Configuration skipped; run `local-agent configure` after Ollama is available.\n' >&2
fi

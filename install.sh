#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${HOME}/.local/share/qwen-agent"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "$INSTALL_DIR" "$BIN_DIR"
cp "$SOURCE_DIR/bin/qwen-agent" "$INSTALL_DIR/qwen-agent"
chmod +x "$INSTALL_DIR/qwen-agent"

for wrapper in "$SOURCE_DIR"/bin/qwen-*; do
    name="$(basename "$wrapper")"
    if [ "$name" = "qwen-agent" ]; then
        continue
    fi
    cp "$wrapper" "$BIN_DIR/$name"
    chmod +x "$BIN_DIR/$name"
done

ln -sf "$INSTALL_DIR/qwen-agent" "$BIN_DIR/qwen-agent"

ZSHRC="${HOME}/.zshrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
if ! grep -Fq "$PATH_LINE" "$ZSHRC" 2>/dev/null; then
    printf '\n# Local Qwen agent commands\n%s\n' "$PATH_LINE" >> "$ZSHRC"
fi

printf '\nInstalled commands into %s\n' "$BIN_DIR"
printf 'Run: source ~/.zshrc\n'

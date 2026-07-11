#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
TARGET="${BIN_DIR}/local-agent"
ZSHRC="${HOME}/.zshrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
INSTRUCTION_START='<!-- BEGIN LOCAL-AGENT TOOLKIT -->'
INSTRUCTION_END='<!-- END LOCAL-AGENT TOOLKIT -->'

usage() {
    printf 'Usage: %s [--instructions codex|claude|both|none] [--uninstall]\n' "$0" >&2
}

instructions=""
uninstall=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --uninstall)
            uninstall=1
            shift
            ;;
        --instructions)
            if [ "$#" -lt 2 ]; then
                usage
                exit 2
            fi
            instructions="$2"
            shift 2
            ;;
        --instructions=*)
            instructions="${1#*=}"
            shift
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

case "$instructions" in
    ""|codex|claude|both|none) ;;
    *)
        usage
        exit 2
        ;;
esac

update_instruction_file() {
    local target="$1"
    local snippet="$2"
    local operation="$3"
    mkdir -p "$(dirname "$target")"
    python3 - "$target" "$snippet" "$operation" "$INSTRUCTION_START" "$INSTRUCTION_END" <<'PY'
from __future__ import annotations

import os
import re
import stat
import sys
import tempfile
from pathlib import Path

target = Path(sys.argv[1])
snippet_path = Path(sys.argv[2])
operation = sys.argv[3]
start = sys.argv[4]
end = sys.argv[5]
existing = target.read_text(encoding="utf-8") if target.exists() else ""
pattern = re.compile(
    rf"(?ms)^[ \t]*{re.escape(start)}\n.*?^[ \t]*{re.escape(end)}[ \t]*\n?"
)

if operation == "install":
    block = f"{start}\n{snippet_path.read_text(encoding='utf-8').rstrip()}\n{end}\n"
    if pattern.search(existing):
        updated = pattern.sub(block, existing, count=1)
    else:
        prefix = existing
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix:
            prefix += "\n"
        updated = prefix + block
else:
    updated = pattern.sub("", existing, count=1)

if updated == existing:
    raise SystemExit(0)

target.parent.mkdir(parents=True, exist_ok=True)
mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(updated)
    os.chmod(temporary, mode)
    os.replace(temporary, target)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
}

if [ "$uninstall" -eq 1 ]; then
    rm -f "$TARGET"
    update_instruction_file "${HOME}/.codex/AGENTS.md" "${SOURCE_DIR}/instructions/AGENTS-snippet.md" uninstall
    update_instruction_file "${HOME}/.claude/CLAUDE.md" "${SOURCE_DIR}/instructions/CLAUDE-snippet.md" uninstall
    printf 'Removed %s and toolkit-managed instruction blocks (configuration was kept).\n' "$TARGET"
    exit 0
fi

if [ -z "$instructions" ] && [ -t 0 ] && [ -t 1 ]; then
    printf 'Install global delegation instructions?\n'
    printf '  codex  - ~/.codex/AGENTS.md\n'
    printf '  claude - ~/.claude/CLAUDE.md\n'
    printf '  both\n'
    printf '  none\n'
    while :; do
        read -r -p 'Choose codex, claude, both, or none: ' instructions
        case "$instructions" in
            codex|claude|both|none) break ;;
            *) printf 'Please enter codex, claude, both, or none.\n' >&2 ;;
        esac
    done
elif [ -z "$instructions" ]; then
    instructions=none
fi

mkdir -p "$BIN_DIR"
cp "$SOURCE_DIR/bin/local-agent" "$TARGET"
chmod +x "$TARGET"

if ! grep -Fq "$PATH_LINE" "$ZSHRC" 2>/dev/null; then
    printf '\n# Local Agent toolkit\n%s\n' "$PATH_LINE" >> "$ZSHRC"
fi

case "$instructions" in
    codex|both)
        update_instruction_file "${HOME}/.codex/AGENTS.md" "${SOURCE_DIR}/instructions/AGENTS-snippet.md" install
        ;;
esac
case "$instructions" in
    claude|both)
        update_instruction_file "${HOME}/.claude/CLAUDE.md" "${SOURCE_DIR}/instructions/CLAUDE-snippet.md" install
        ;;
esac

printf 'Installed %s\n' "$TARGET"
printf 'Open a new shell or run: source ~/.zshrc\n'
if [ "$instructions" != "none" ]; then
    printf 'Restart existing Codex or Claude sessions to load updated instructions.\n'
fi
if [ -t 0 ] && [ -t 1 ]; then
    "$TARGET" configure || printf 'Configuration skipped; run `local-agent configure` after Ollama is available.\n' >&2
fi

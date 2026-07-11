#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_ROOT="${HOME}/.local/share/local-agent-toolkit"
MANAGED_BIN="${INSTALL_ROOT}/bin/local-agent"
PUBLIC_BIN="${HOME}/.local/bin/local-agent"
STATE_FILE="${INSTALL_ROOT}/install-state.json"
CONFIG_DIR="${HOME}/.config/local-agent"
ZSHRC="${HOME}/.zshrc"

PATH_BLOCK_START='# BEGIN LOCAL-AGENT TOOLKIT PATH'
PATH_BLOCK_END='# END LOCAL-AGENT TOOLKIT PATH'
PATH_EXPORT="export PATH=\"\$HOME/.local/bin:\$PATH\""

INSTRUCTION_START='<!-- BEGIN LOCAL-AGENT TOOLKIT -->'
INSTRUCTION_END='<!-- END LOCAL-AGENT TOOLKIT -->'

usage() {
    printf 'Usage: %s [--instructions codex|claude|both|none] [--uninstall] [--purge-config] [--dry-run]\n' "$0" >&2
}

die() {
    printf '%s\n' "$1" >&2
    exit "${2:-1}"
}

note() {
    printf '%s\n' "$1"
}

require_python() {
    command -v python3 >/dev/null 2>&1 || die 'python3 is required to run install.sh'
}

resolve_path() {
    python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

path_exists() {
    [ -e "$1" ] || [ -L "$1" ]
}

managed_install_exists() {
    path_exists "$INSTALL_ROOT"
}

is_owned_public_link() {
    [ -L "$PUBLIC_BIN" ] || return 1
    [ "$(resolve_path "$PUBLIC_BIN")" = "$(resolve_path "$MANAGED_BIN")" ]
}

assert_install_target_available() {
    note "Inspecting existing public path: $PUBLIC_BIN"
    if ! path_exists "$PUBLIC_BIN"; then
        return 0
    fi
    if is_owned_public_link; then
        return 0
    fi
    die "Refusing to replace existing path:
  $PUBLIC_BIN

Move or remove it manually, then rerun the installer."
}

manage_block() {
    local target="$1"
    local operation="$2"
    local start_marker="$3"
    local end_marker="$4"
    local content_kind="$5"
    local content_value="$6"

    note "Inspecting managed block in: $target"
    if [ "$dry_run" -eq 1 ]; then
        note "Would ${operation} managed block in $target"
        return 0
    fi

    python3 - "$target" "$operation" "$start_marker" "$end_marker" "$content_kind" "$content_value" <<'PY'
from __future__ import annotations

import os
import re
import stat
import sys
import tempfile
from pathlib import Path

target = Path(sys.argv[1])
operation = sys.argv[2]
start = sys.argv[3]
end = sys.argv[4]
content_kind = sys.argv[5]
content_value = sys.argv[6]

existing = target.read_text(encoding="utf-8") if target.exists() else ""
pattern = re.compile(
    rf"(?ms)^[ \t]*{re.escape(start)}\n.*?^[ \t]*{re.escape(end)}[ \t]*\n?"
)

content = ""
if operation == "install":
    if content_kind == "file":
        content = Path(content_value).read_text(encoding="utf-8")
    else:
        content = content_value
    block = f"{start}\n{content.rstrip()}\n{end}\n"
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
    updated = re.sub(
        rf"(?ms)\n^[ \t]*{re.escape(start)}\n.*?^[ \t]*{re.escape(end)}[ \t]*\n?",
        "",
        existing,
        count=1,
    )
    if updated == existing:
        updated = pattern.sub("", existing, count=1)

if updated == existing:
    raise SystemExit(0)

if operation == "install":
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

file_has_marker() {
    local target="$1"
    local marker="$2"
    [ -f "$target" ] && grep -Fq "$marker" "$target"
}

install_path_block() {
    note "Inspecting shell PATH configuration: $ZSHRC"
    if file_has_marker "$ZSHRC" "$PATH_BLOCK_START"; then
        manage_block "$ZSHRC" install "$PATH_BLOCK_START" "$PATH_BLOCK_END" text "$PATH_EXPORT"
        return 0
    fi
    if [ -f "$ZSHRC" ] && grep -Fq "$PATH_EXPORT" "$ZSHRC"; then
        note "PATH already exports ~/.local/bin outside toolkit markers; leaving it unchanged"
        return 0
    fi
    manage_block "$ZSHRC" install "$PATH_BLOCK_START" "$PATH_BLOCK_END" text "$PATH_EXPORT"
}

install_instruction_block() {
    local target="$1"
    local snippet="$2"
    manage_block "$target" install "$INSTRUCTION_START" "$INSTRUCTION_END" file "$snippet"
}

remove_managed_blocks() {
    manage_block "${HOME}/.codex/AGENTS.md" uninstall "$INSTRUCTION_START" "$INSTRUCTION_END" text ""
    manage_block "${HOME}/.claude/CLAUDE.md" uninstall "$INSTRUCTION_START" "$INSTRUCTION_END" text ""
    manage_block "$ZSHRC" uninstall "$PATH_BLOCK_START" "$PATH_BLOCK_END" text ""
}

cleanup_managed_install() {
    remove_public_symlink_if_owned
    remove_tree "$INSTALL_ROOT"
    remove_managed_blocks
}

install_managed_binary() {
    local source_binary="${SOURCE_DIR}/bin/local-agent"
    note "Inspecting source binary: $source_binary"
    [ -f "$source_binary" ] || die "Required file is missing: $source_binary"
    note "Would manage binary at: $MANAGED_BIN"
    if [ "$dry_run" -eq 1 ]; then
        note "Would create directory: $(dirname "$MANAGED_BIN")"
        note "Would atomically copy $source_binary to $MANAGED_BIN"
        return 0
    fi

    mkdir -p "$(dirname "$MANAGED_BIN")"
    python3 - "$source_binary" "$MANAGED_BIN" "$$" <<'PY'
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
pid = sys.argv[3]
temporary = destination.parent / f".local-agent.tmp.{pid}"

try:
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    shutil.copyfile(source, temporary)
    os.chmod(temporary, stat.S_IMODE(source.stat().st_mode) | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(temporary, destination)
finally:
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
PY
}

ensure_public_symlink() {
    note "Inspecting public binary path: $PUBLIC_BIN"
    if [ "$dry_run" -eq 1 ]; then
        if path_exists "$PUBLIC_BIN"; then
            note "Would keep existing owned symlink at $PUBLIC_BIN"
        else
            note "Would create directory: $(dirname "$PUBLIC_BIN")"
            note "Would create symlink: $PUBLIC_BIN -> $MANAGED_BIN"
        fi
        return 0
    fi

    mkdir -p "$(dirname "$PUBLIC_BIN")"
    if is_owned_public_link; then
        return 0
    fi
    ln -s "$MANAGED_BIN" "$PUBLIC_BIN"
}

write_install_state() {
    note "Would manage install state at: $STATE_FILE"
    if [ "$dry_run" -eq 1 ]; then
        note "Would record installed instructions: ${instructions}"
        return 0
    fi

    mkdir -p "$(dirname "$STATE_FILE")"
    python3 - "$STATE_FILE" "$instructions" <<'PY'
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

state_path = Path(sys.argv[1])
mode = sys.argv[2]
installed = {
    "codex": ["codex"],
    "claude": ["claude"],
    "both": ["codex", "claude"],
    "none": [],
}.get(mode, [])
payload = {
    "schema_version": 1,
    "public_binary": "~/.local/bin/local-agent",
    "managed_binary": "~/.local/share/local-agent-toolkit/bin/local-agent",
    "installed_instructions": installed,
}

fd, temporary = tempfile.mkstemp(prefix=f".{state_path.name}.", dir=state_path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, state_path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
}

remove_tree() {
    local target="$1"
    note "Inspecting managed path for removal: $target"
    if [ "$dry_run" -eq 1 ]; then
        note "Would remove: $target"
        return 0
    fi
    python3 - "$target" <<'PY'
from __future__ import annotations

import shutil
import sys
from pathlib import Path

target = Path(sys.argv[1]).expanduser()
if target.exists() or target.is_symlink():
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()
PY
}

remove_public_symlink_if_owned() {
    note "Inspecting public binary for uninstall: $PUBLIC_BIN"
    if ! path_exists "$PUBLIC_BIN"; then
        return 0
    fi
    if is_owned_public_link; then
        if [ "$dry_run" -eq 1 ]; then
            note "Would remove owned symlink: $PUBLIC_BIN"
        else
            rm -f "$PUBLIC_BIN"
        fi
        return 0
    fi
    note 'local-agent: public command is no longer owned by this installation; leaving it untouched'
}

confirm_reinstall() {
    printf 'A managed local-agent installation already exists at %s.\n' "$INSTALL_ROOT"
    printf 'Reinstalling will remove the managed installation and reinstall it.\n'
    while :; do
        read -r -p 'Type yes to reinstall or no to cancel: ' response
        case "$response" in
            yes)
                return 0
                ;;
            no)
                note 'Reinstall cancelled; existing installation was left unchanged.'
                return 1
                ;;
            *)
                printf 'Please enter exact lowercase yes or no.\n' >&2
                ;;
        esac
    done
}

validate_instruction_sources() {
    case "$instructions" in
        codex|both)
            [ -f "${SOURCE_DIR}/instructions/AGENTS-snippet.md" ] || die "Required file is missing: ${SOURCE_DIR}/instructions/AGENTS-snippet.md"
            ;;
    esac
    case "$instructions" in
        claude|both)
            [ -f "${SOURCE_DIR}/instructions/CLAUDE-snippet.md" ] || die "Required file is missing: ${SOURCE_DIR}/instructions/CLAUDE-snippet.md"
            ;;
    esac
}

instructions=""
uninstall=0
purge_config=0
dry_run=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --uninstall)
            uninstall=1
            shift
            ;;
        --purge-config)
            purge_config=1
            shift
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        --instructions)
            [ "$#" -ge 2 ] || die 'Missing value for --instructions' 2
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

if [ "$purge_config" -eq 1 ] && [ "$uninstall" -ne 1 ]; then
    die '--purge-config requires --uninstall' 2
fi

require_python

if [ "$uninstall" -eq 1 ]; then
    if ! managed_install_exists; then
        if [ "$purge_config" -eq 1 ]; then
            remove_tree "$CONFIG_DIR"
        fi
        note 'No prior installation found'
        exit 0
    fi
    cleanup_managed_install
    if [ "$purge_config" -eq 1 ]; then
        remove_tree "$CONFIG_DIR"
    fi
    if [ "$dry_run" -eq 1 ]; then
        note 'Dry run complete; no files were modified.'
    else
        if [ "$purge_config" -eq 1 ]; then
            note 'Removed toolkit-managed installation paths, managed blocks, and local-agent configuration.'
        else
            note 'Removed toolkit-managed installation paths and managed blocks (configuration was kept).'
        fi
    fi
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

validate_instruction_sources
if managed_install_exists; then
    if [ ! -t 0 ] || [ ! -t 1 ]; then
        note 'Managed installation already exists; reinstall confirmation requires an interactive terminal. Leaving the existing installation unchanged.'
        exit 0
    fi
    if ! confirm_reinstall; then
        exit 0
    fi
    cleanup_managed_install
fi
assert_install_target_available
install_managed_binary
ensure_public_symlink
install_path_block

case "$instructions" in
    codex|both)
        install_instruction_block "${HOME}/.codex/AGENTS.md" "${SOURCE_DIR}/instructions/AGENTS-snippet.md"
        ;;
esac
case "$instructions" in
    claude|both)
        install_instruction_block "${HOME}/.claude/CLAUDE.md" "${SOURCE_DIR}/instructions/CLAUDE-snippet.md"
        ;;
esac

write_install_state

if [ "$dry_run" -eq 1 ]; then
    note 'Dry run complete; no files were modified.'
    exit 0
fi

note "Installed managed binary at $MANAGED_BIN"
note "Linked public command at $PUBLIC_BIN"
note 'Open a new shell or run: source ~/.zshrc'
if [ "$instructions" != "none" ]; then
    note 'Restart existing Codex or Claude sessions to load updated instructions.'
fi
if [ -t 0 ] && [ -t 1 ]; then
    "$PUBLIC_BIN" configure || printf "Configuration skipped; run \`local-agent configure\` after Ollama is available.\n" >&2
fi

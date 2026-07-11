#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_ROOT="${HOME}/.local/share/local-agent-toolkit"
MANAGED_BIN="${INSTALL_ROOT}/bin/local-agent"
PUBLIC_BIN="${HOME}/.local/bin/local-agent"
STATE_FILE="${INSTALL_ROOT}/install-state.json"
CONFIG_DIR="${HOME}/.config/local-agent"
CACHE_DIR="${HOME}/.cache/local-agent"
ZSHRC="${HOME}/.zshrc"
LOCK_DIR="${HOME}/.local/state/local-agent-toolkit/install.lock"

SKILL_SOURCE_DIR="${SOURCE_DIR}/skills/local-agent-toolkit"
CODEX_SKILL_DEST="${HOME}/.agents/skills/local-agent-toolkit"
CLAUDE_SKILL_DEST="${HOME}/.claude/skills/local-agent-toolkit"
CODEX_GLOBAL_FILE="${HOME}/.codex/AGENTS.md"
CLAUDE_GLOBAL_FILE="${HOME}/.claude/CLAUDE.md"

PATH_BLOCK_START='# BEGIN LOCAL-AGENT TOOLKIT PATH'
PATH_BLOCK_END='# END LOCAL-AGENT TOOLKIT PATH'
PATH_EXPORT="export PATH=\"\$HOME/.local/bin:\$PATH\""

INSTRUCTION_START='<!-- BEGIN LOCAL-AGENT TOOLKIT -->'
INSTRUCTION_END='<!-- END LOCAL-AGENT TOOLKIT -->'

usage() {
    printf 'Usage: %s [--skills codex|claude|both|none] [--instructions codex|claude|both|none] [--uninstall] [--purge-config] [--dry-run]\n' "$0" >&2
}

die() {
    printf '%s\n' "$1" >&2
    exit "${2:-1}"
}

note() {
    printf '%s\n' "$1"
}

warn() {
    printf '%s\n' "$1" >&2
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

file_has_marker() {
    local target="$1"
    local marker="$2"
    [ -f "$target" ] && grep -Fq "$marker" "$target"
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

remove_owned_path_block() {
    manage_block "$ZSHRC" uninstall "$PATH_BLOCK_START" "$PATH_BLOCK_END" text ""
}

remove_block_bytes() {
    local target="$1"
    note "Inspecting managed block in: $target"
    if [ "$dry_run" -eq 1 ]; then
        note "Would uninstall managed block in $target"
        return 3
    fi
    python3 - "$target" "$INSTRUCTION_START" "$INSTRUCTION_END" <<'PY'
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

target = Path(sys.argv[1])
start_marker = sys.argv[2].encode("ascii")
end_marker = sys.argv[3].encode("ascii")

if not target.exists():
    raise SystemExit(3)

data = target.read_bytes()
lines = data.splitlines(keepends=True)
start_index = None
end_index = None
for index, line in enumerate(lines):
    stripped = line.rstrip(b"\r\n")
    if start_index is None and stripped == start_marker:
        start_index = index
        continue
    if start_index is not None and stripped == end_marker:
        end_index = index
        break

if start_index is None or end_index is None:
    raise SystemExit(3)

updated = b"".join(lines[:start_index] + lines[end_index + 1 :])
if updated == data:
    raise SystemExit(3)

mode = stat.S_IMODE(target.stat().st_mode)
fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
try:
    with os.fdopen(fd, "wb") as handle:
        handle.write(updated)
    os.chmod(temporary, mode)
    os.replace(temporary, target)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
    return $?
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

validate_skill_source() {
    note "Validating canonical skill source: $SKILL_SOURCE_DIR"
    python3 "${SOURCE_DIR}/scripts/validate_skill.py" "$SKILL_SOURCE_DIR" >/dev/null
}

acquire_lock() {
    if [ "$dry_run" -eq 1 ]; then
        return 0
    fi
    local parent
    parent="$(dirname "$LOCK_DIR")"
    mkdir -p "$parent"
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM
        return 0
    fi
    die "Another local-agent-toolkit install is already running for ${HOME}" 1
}

confirm_reinstall() {
    if ! path_exists "$MANAGED_BIN"; then
        return 0
    fi
    if [ "$dry_run" -eq 1 ]; then
        note "Would prompt before reinstalling existing managed binary at $MANAGED_BIN"
        return 0
    fi
    if [ ! -t 0 ] || [ ! -t 1 ]; then
        note 'Existing managed installation detected; reinstall confirmation requires an interactive terminal.'
        return 1
    fi
    printf 'Existing managed installation detected.\n'
    while :; do
        read -r -p 'Type yes to reinstall or no to cancel: ' answer
        case "$answer" in
            yes) return 0 ;;
            no)
                note 'Reinstall cancelled; existing installation was left unchanged.'
                return 1
                ;;
            *) printf 'Please enter exact lowercase yes or no.\n' ;;
        esac
    done
}

skill_dest_for_target() {
    case "$1" in
        codex) printf '%s\n' "$CODEX_SKILL_DEST" ;;
        claude) printf '%s\n' "$CLAUDE_SKILL_DEST" ;;
        *) return 1 ;;
    esac
}

legacy_file_for_target() {
    case "$1" in
        codex) printf '%s\n' "$CODEX_GLOBAL_FILE" ;;
        claude) printf '%s\n' "$CLAUDE_GLOBAL_FILE" ;;
        *) return 1 ;;
    esac
}

target_requested() {
    case "$skills" in
        both) return 0 ;;
        "$1") return 0 ;;
        *) return 1 ;;
    esac
}

install_skill_directory() {
    local destination="$1"
    note "Inspecting skill destination: $destination"
    if [ "$dry_run" -eq 1 ]; then
        note "Would install skill from $SKILL_SOURCE_DIR to $destination"
        return 0
    fi
    python3 "${SOURCE_DIR}/scripts/install_skill.py" "$SKILL_SOURCE_DIR" "$destination"
}

skill_owned() {
    python3 - "$1" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

target = Path(sys.argv[1]).expanduser()
marker = target / ".local-agent-toolkit.json"
if target.exists() and target.is_dir() and marker.is_file():
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise SystemExit(1)
    if payload == {
        "schema_version": 1,
        "manager": "local-agent-toolkit",
        "skill": "local-agent-toolkit",
    }:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

write_install_state() {
    local codex_status="$1"
    local claude_status="$2"
    note "Inspecting state path: $STATE_FILE"
    if [ "$dry_run" -eq 1 ]; then
        note "Would write schema-2 install state to $STATE_FILE"
        return 0
    fi

    mkdir -p "$(dirname "$STATE_FILE")"
    python3 - "$STATE_FILE" "$MANAGED_BIN" "$PUBLIC_BIN" "$CODEX_SKILL_DEST" "$CLAUDE_SKILL_DEST" "$codex_status" "$claude_status" <<'PY'
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import sys

state_path = Path(sys.argv[1])
managed_binary = Path(sys.argv[2]).expanduser()
public_binary = Path(sys.argv[3]).expanduser()
codex_skill = Path(sys.argv[4]).expanduser()
claude_skill = Path(sys.argv[5]).expanduser()
codex_status = sys.argv[6]
claude_status = sys.argv[7]

marker = {
    "schema_version": 1,
    "manager": "local-agent-toolkit",
    "skill": "local-agent-toolkit",
}

def owned_skill(path: Path) -> str | None:
    marker_path = path / ".local-agent-toolkit.json"
    if not path.exists() or not path.is_dir() or not marker_path.is_file():
        return None
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload != marker:
        return None
    return str(path).replace(str(Path.home()), "~")

payload = {
    "schema_version": 2,
    "public_binary": str(public_binary).replace(str(Path.home()), "~"),
    "managed_binary": str(managed_binary).replace(str(Path.home()), "~"),
    "installed_skills": {
        "codex": owned_skill(codex_skill),
        "claude": owned_skill(claude_skill),
    },
    "legacy_instruction_migration": {
        "codex": codex_status,
        "claude": claude_status,
    },
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

prompt_for_skills() {
    if [ -z "$skills" ] && [ -t 0 ] && [ -t 1 ]; then
        printf 'Install personal skills?\n'
        printf '  codex  - %s\n' "$CODEX_SKILL_DEST"
        printf '  claude - %s\n' "$CLAUDE_SKILL_DEST"
        printf '  both\n'
        printf '  none\n'
        while :; do
            read -r -p 'Choose codex, claude, both, or none: ' skills
            case "$skills" in
                codex|claude|both|none) break ;;
                *) printf 'Please enter codex, claude, both, or none.\n' >&2 ;;
            esac
        done
    elif [ -z "$skills" ]; then
        skills=none
    fi
}

perform_target_install() {
    local target="$1"
    local destination
    local legacy_file
    local removal_status
    destination="$(skill_dest_for_target "$target")"
    legacy_file="$(legacy_file_for_target "$target")"

    if ! install_skill_directory "$destination"; then
        note "local-agent: ${target} skill installation failed."
        eval "${target}_migration=failed"
        overall_status=1
        return 0
    fi

    set +e
    remove_block_bytes "$legacy_file"
    removal_status=$?
    set -e
    if [ "$removal_status" -eq 0 ]; then
        eval "${target}_migration=removed"
        return 0
    fi
    case "$removal_status" in
        3)
            eval "${target}_migration=not_present"
            ;;
        *)
            eval "${target}_migration=failed"
            overall_status=1
            ;;
    esac
}

remove_owned_skill_dir() {
    local target="$1"
    local destination
    destination="$(skill_dest_for_target "$target")"
    note "Inspecting ${target} skill destination for uninstall: $destination"
    if ! skill_owned "$destination"; then
        note "local-agent: ${target} skill is not owned at ${destination}; leaving it untouched"
        return 1
    fi
    remove_tree "$destination"
    return 0
}

skills=""
uninstall=0
purge_config=0
dry_run=0
skills_flag_seen=0
instructions_flag_seen=0

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
        --skills)
            [ "$skills_flag_seen" -eq 0 ] || die 'Repeated --skills selector is not allowed' 2
            [ "$instructions_flag_seen" -eq 0 ] || die 'Use only one of --skills or --instructions' 2
            [ "$#" -ge 2 ] || die 'Missing value for --skills' 2
            skills="$2"
            skills_flag_seen=1
            shift 2
            ;;
        --skills=*)
            [ "$skills_flag_seen" -eq 0 ] || die 'Repeated --skills selector is not allowed' 2
            [ "$instructions_flag_seen" -eq 0 ] || die 'Use only one of --skills or --instructions' 2
            skills="${1#*=}"
            skills_flag_seen=1
            shift
            ;;
        --instructions)
            [ "$instructions_flag_seen" -eq 0 ] || die 'Repeated --instructions selector is not allowed' 2
            [ "$skills_flag_seen" -eq 0 ] || die 'Use only one of --skills or --instructions' 2
            [ "$#" -ge 2 ] || die 'Missing value for --instructions' 2
            skills="$2"
            instructions_flag_seen=1
            shift 2
            ;;
        --instructions=*)
            [ "$instructions_flag_seen" -eq 0 ] || die 'Repeated --instructions selector is not allowed' 2
            [ "$skills_flag_seen" -eq 0 ] || die 'Use only one of --skills or --instructions' 2
            skills="${1#*=}"
            instructions_flag_seen=1
            shift
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

case "$skills" in
    ""|codex|claude|both|none) ;;
    *)
        usage
        exit 2
        ;;
esac

if [ "$instructions_flag_seen" -eq 1 ]; then
    warn 'Warning: --instructions is deprecated and currently aliases --skills. Legacy instruction blocks are not reinstalled.'
fi

if [ "$purge_config" -eq 1 ] && [ "$uninstall" -ne 1 ]; then
    die '--purge-config requires --uninstall' 2
fi

if [ "$uninstall" -eq 1 ] && [ -n "$skills" ]; then
    die 'Skill selectors cannot be used with --uninstall' 2
fi

require_python

if [ "$uninstall" -eq 1 ]; then
    removed_any=0
    if is_owned_public_link; then
        remove_public_symlink_if_owned
        removed_any=1
    fi
    if path_exists "$INSTALL_ROOT"; then
        remove_tree "$INSTALL_ROOT"
        removed_any=1
    fi
    if remove_owned_skill_dir codex; then
        removed_any=1
    fi
    if remove_owned_skill_dir claude; then
        removed_any=1
    fi
    if remove_block_bytes "$CODEX_GLOBAL_FILE"; then
        removed_any=1
    fi
    if remove_block_bytes "$CLAUDE_GLOBAL_FILE"; then
        removed_any=1
    fi
    remove_owned_path_block
    if [ "$purge_config" -eq 1 ]; then
        if path_exists "$CONFIG_DIR"; then
            remove_tree "$CONFIG_DIR"
            removed_any=1
        fi
        if path_exists "$CACHE_DIR"; then
            remove_tree "$CACHE_DIR"
            removed_any=1
        fi
    fi
    if [ "$dry_run" -eq 1 ]; then
        note 'Dry run complete; no files were modified.'
    else
        if [ "$removed_any" -eq 0 ]; then
            note 'No prior installation found.'
        elif [ "$purge_config" -eq 1 ]; then
            note 'Removed toolkit-managed binary, owned skills, managed blocks, local-agent configuration, and cache.'
        else
            note 'Removed toolkit-managed binary, owned skills, and managed blocks (configuration and cache were kept).'
        fi
    fi
    exit 0
fi

prompt_for_skills

if [ "$skills" != "none" ]; then
    validate_skill_source
fi

assert_install_target_available
confirm_reinstall || exit 0
acquire_lock

install_managed_binary
ensure_public_symlink
install_path_block

codex_migration=not_requested
claude_migration=not_requested
overall_status=0

if target_requested codex; then
    perform_target_install codex
fi
if target_requested claude; then
    perform_target_install claude
fi

write_install_state "$codex_migration" "$claude_migration"

if [ "$dry_run" -eq 1 ]; then
    note 'Dry run complete; no files were modified.'
    exit "$overall_status"
fi

note "Installed managed binary at $MANAGED_BIN"
note "Linked public command at $PUBLIC_BIN"
note 'Open a new shell or run: source ~/.zshrc'
case "$skills" in
    codex)
        note "Installed Codex skill at $CODEX_SKILL_DEST"
        ;;
    claude)
        note "Installed Claude skill at $CLAUDE_SKILL_DEST"
        ;;
    both)
        note "Installed Codex skill target at $CODEX_SKILL_DEST"
        note "Installed Claude skill target at $CLAUDE_SKILL_DEST"
        ;;
esac
if [ "$skills" != "none" ]; then
    note 'Restart or refresh existing Codex and Claude sessions to pick up skill discovery changes.'
fi
if [ -t 0 ] && [ -t 1 ]; then
    "$PUBLIC_BIN" configure || printf "Configuration skipped; run \`local-agent configure\` after Ollama is available.\n" >&2
fi

exit "$overall_status"

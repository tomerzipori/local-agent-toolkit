#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

MARKER_FILE = ".local-agent-toolkit.json"
MARKER = {
    "schema_version": 1,
    "manager": "local-agent-toolkit",
    "skill": "local-agent-toolkit",
}
EXPECTED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/commands.md",
    "references/delegation-policy.md",
    "references/model-selection.md",
    "references/verification.md",
    "scripts/check_environment.py",
}
EXCLUDED_NAMES = {"__pycache__", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


class InstallError(RuntimeError):
    pass


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def validate_source_tree(source: Path) -> None:
    if not source.is_dir():
        raise InstallError(f"missing skill source: {source}")
    actual: set[str] = set()
    for entry in source.rglob("*"):
        relative = entry.relative_to(source).as_posix()
        if entry.is_symlink():
            raise InstallError(f"source contains a symlink: {relative}")
        if entry.is_dir():
            if entry.name in EXCLUDED_NAMES:
                raise InstallError(f"source contains a forbidden directory: {relative}")
            continue
        if entry.name in EXCLUDED_NAMES or entry.suffix in EXCLUDED_SUFFIXES:
            raise InstallError(f"source contains a forbidden generated file: {relative}")
        if relative == MARKER_FILE:
            raise InstallError("source must not contain an ownership marker")
        if relative not in EXPECTED_FILES:
            raise InstallError(f"unexpected source entry: {relative}")
        actual.add(relative)
    missing = EXPECTED_FILES - actual
    if missing:
        raise InstallError(f"missing required source entries: {', '.join(sorted(missing))}")


def load_marker(path: Path) -> dict[str, object]:
    marker_path = path / MARKER_FILE
    if not marker_path.is_file():
        raise InstallError(f"managed marker is missing at {marker_path}")
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"managed marker is malformed at {marker_path}: {exc}") from exc
    if payload != MARKER:
        raise InstallError(f"managed marker is malformed at {marker_path}")
    return payload


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for entry in source.rglob("*"):
        relative = entry.relative_to(source)
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if entry.suffix in EXCLUDED_SUFFIXES:
            continue
        target = destination / relative
        if entry.is_dir():
            target.mkdir(exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)
        if os.access(entry, os.X_OK):
            mode = stat.S_IMODE(target.stat().st_mode)
            target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_marker(destination: Path) -> None:
    marker_path = destination / MARKER_FILE
    marker_path.write_text(json.dumps(MARKER, indent=2) + "\n", encoding="utf-8")


def install_skill(source: Path, destination: Path) -> None:
    validate_source_tree(source)
    if destination.exists() and destination.is_symlink():
        raise InstallError(f"destination is a symlink: {destination}")
    if destination.is_file():
        raise InstallError(f"destination is not a directory: {destination}")
    if destination.exists():
        load_marker(destination)

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.stage.", dir=parent)
    os.close(fd)
    os.unlink(temporary_name)
    stage = Path(temporary_name)
    backup = parent / f".{destination.name}.backup.{os.getpid()}"

    try:
        copy_tree(source, stage)
        write_marker(stage)
        load_marker(stage)
        if destination.exists():
            os.replace(destination, backup)
        if os.environ.get("LOCAL_AGENT_TOOLKIT_TEST_PROMOTE_FAILURE") == "1":
            raise InstallError("simulated promotion failure")
        os.replace(stage, destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if backup.exists():
            os.replace(backup, destination)
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    if len(sys.argv) != 3:
        return fail("usage: install_skill.py <source> <destination>")
    source = Path(sys.argv[1]).expanduser().resolve(strict=False)
    destination = Path(sys.argv[2]).expanduser().resolve(strict=False)
    try:
        install_skill(source, destination)
    except InstallError as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "local-agent-toolkit"
EXPECTED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/commands.md",
    "references/delegation-policy.md",
    "references/model-selection.md",
    "references/verification.md",
    "scripts/check_environment.py",
}
FILE_SIZE_LIMITS = {
    "SKILL.md": 32768,
    "agents/openai.yaml": 4096,
    "references/commands.md": 32768,
    "references/delegation-policy.md": 16384,
    "references/model-selection.md": 16384,
    "references/verification.md": 16384,
    "scripts/check_environment.py": 32768,
}
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
REFERENCE_RE = re.compile(r"(references/[A-Za-z0-9._/-]+|scripts/[A-Za-z0-9._/-]+)")
MARKER_FILE = ".local-agent-toolkit.json"


class ValidationError(RuntimeError):
    pass


def parse_frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValidationError("SKILL.md is missing YAML frontmatter")
    data: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        if not raw_line.strip():
            continue
        if ":" not in raw_line:
            raise ValidationError(f"invalid frontmatter line: {raw_line}")
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValidationError(f"invalid frontmatter line: {raw_line}")
        data[key] = value
    return data


def parse_openai_yaml(path: Path) -> dict[str, dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    result: dict[str, dict[str, str]] = {}
    current_section: str | None = None
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("  "):
            if current_section is None or ":" not in line:
                raise ValidationError("agents/openai.yaml has invalid indentation")
            key, value = line.strip().split(":", 1)
            value = value.strip()
            if not (value.startswith('"') and value.endswith('"')):
                raise ValidationError("agents/openai.yaml values must be double-quoted strings")
            result[current_section][key] = ast.literal_eval(value)
            continue
        if line.startswith(" "):
            raise ValidationError("agents/openai.yaml uses unsupported indentation")
        if ":" not in line:
            raise ValidationError("agents/openai.yaml has an invalid top-level line")
        key, value = line.split(":", 1)
        if value.strip():
            raise ValidationError("agents/openai.yaml only supports mapping sections")
        current_section = key.strip()
        result[current_section] = {}
    return result


def compile_python(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")


def validate_tree(root: Path) -> None:
    if not root.is_dir():
        raise ValidationError(f"missing skill root: {root}")
    actual_files: set[str] = set()
    for entry in root.rglob("*"):
        relative = entry.relative_to(root).as_posix()
        if entry.is_symlink():
            raise ValidationError(f"source contains a symlink: {relative}")
        if entry.is_dir():
            if entry.name == "__pycache__":
                raise ValidationError(f"source contains a cache directory: {relative}")
            continue
        if entry.name == ".DS_Store":
            raise ValidationError(f"source contains a forbidden macOS metadata file: {relative}")
        if entry.suffix in {".pyc", ".pyo"}:
            raise ValidationError(f"source contains compiled Python: {relative}")
        if entry.name == MARKER_FILE:
            raise ValidationError(f"source contains an ownership marker: {relative}")
        if b"\0" in entry.read_bytes():
            raise ValidationError(f"source contains a binary file: {relative}")
        limit = FILE_SIZE_LIMITS.get(relative)
        if limit is None:
            raise ValidationError(f"unexpected source entry: {relative}")
        size = entry.stat().st_size
        if size > limit:
            raise ValidationError(
                f"{relative} exceeds the repository-defined size limit of {limit} bytes"
            )
        actual_files.add(relative)
    missing = EXPECTED_FILES - actual_files
    extra = actual_files - EXPECTED_FILES
    if missing:
        raise ValidationError(f"missing required files: {', '.join(sorted(missing))}")
    if extra:
        raise ValidationError(f"unexpected source entries: {', '.join(sorted(extra))}")


def validate_skill(root: Path) -> None:
    validate_tree(root)

    skill_md = root / "SKILL.md"
    frontmatter = parse_frontmatter(skill_md)
    if frontmatter.get("name") != "local-agent-toolkit":
        raise ValidationError("SKILL.md frontmatter name must be local-agent-toolkit")
    description = frontmatter.get("description", "")
    if not description:
        raise ValidationError("SKILL.md frontmatter description must be non-empty")
    if len(skill_md.read_text(encoding="utf-8").splitlines()) >= 500:
        raise ValidationError("SKILL.md must remain under 500 lines")

    metadata = parse_openai_yaml(root / "agents/openai.yaml")
    interface = metadata.get("interface")
    if interface != {
        "display_name": "Local Agent Toolkit",
        "short_description": "Delegate bounded coding work to local Ollama models",
    }:
        raise ValidationError(
            "agents/openai.yaml does not match the supported standalone Codex metadata shape"
        )

    referenced = set(REFERENCE_RE.findall(skill_md.read_text(encoding="utf-8")))
    missing_refs = [path for path in sorted(referenced) if not (root / path).is_file()]
    if missing_refs:
        raise ValidationError(f"SKILL.md references missing files: {', '.join(missing_refs)}")

    compile_python(root / "scripts/check_environment.py")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the canonical local-agent skill source.")
    parser.add_argument("path", nargs="?", default=str(SKILL_ROOT))
    parser.add_argument("--json", action="store_true", help="Print machine-readable status.")
    args = parser.parse_args()
    target = Path(args.path).expanduser().resolve(strict=False)
    try:
        validate_skill(target)
    except ValidationError as exc:
        if args.json:
            json.dump({"ok": False, "path": str(target), "error": str(exc)}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"invalid: {exc}", file=sys.stderr)
        return 1
    if args.json:
        json.dump({"ok": True, "path": str(target)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"valid: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

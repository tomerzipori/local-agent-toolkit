#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bin/local-agent"
MATCH = re.search(r'^VERSION = "([^"]+)"$', SOURCE.read_text(encoding="utf-8"), re.MULTILINE)

if MATCH is None:
    raise SystemExit(f"Could not extract VERSION from {SOURCE}")

print(MATCH.group(1))

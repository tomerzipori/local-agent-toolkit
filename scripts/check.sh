#!/bin/bash
set -euo pipefail

python3 scripts/validate_skill.py
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m py_compile scripts/read_version.py scripts/validate_skill.py scripts/install_skill.py
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m py_compile skills/local-agent-toolkit/scripts/check_environment.py
python3 -m unittest discover -s tests -v
python3 -m ruff check .
python3 -m ruff format --check .
bash -n install.sh
shellcheck install.sh

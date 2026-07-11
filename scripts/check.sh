#!/bin/bash
set -euo pipefail

python3 -m unittest discover -s tests -v
python3 -m ruff check .
python3 -m ruff format --check .
bash -n install.sh
shellcheck install.sh

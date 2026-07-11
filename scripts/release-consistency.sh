#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:?tag is required}"
VERSION="$(python3 "$ROOT/scripts/read_version.py")"

if [ "$TAG" != "v$VERSION" ]; then
    printf 'Tag %s does not match executable version v%s\n' "$TAG" "$VERSION" >&2
    exit 1
fi

grep -F "## $VERSION" "$ROOT/CHANGELOG.md" >/dev/null

for required_file in \
    README.md \
    LICENSE \
    CHANGELOG.md \
    CODE_OF_CONDUCT.md \
    CONTRIBUTING.md \
    SECURITY.md \
    SUPPORT.md
do
    test -f "$ROOT/$required_file"
done

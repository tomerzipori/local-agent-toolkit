#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:?tag is required}"
VERSION="$(python3 "$ROOT/scripts/read_version.py")"

if [ "$TAG" != "v$VERSION" ]; then
    printf 'Tag %s does not match executable version v%s\n' "$TAG" "$VERSION" >&2
    exit 1
fi

if ! grep -Eq "^## \\[$VERSION\\]( |$)" "$ROOT/CHANGELOG.md"; then
    printf 'CHANGELOG.md is missing a release heading for version %s\n' "$VERSION" >&2
    exit 1
fi

for required_file in \
    README.md \
    LICENSE \
    CHANGELOG.md \
    CODE_OF_CONDUCT.md \
    CONTRIBUTING.md \
    SECURITY.md \
    SUPPORT.md
do
    if [ ! -f "$ROOT/$required_file" ]; then
        printf 'Required release file is missing: %s\n' "$required_file" >&2
        exit 1
    fi
done

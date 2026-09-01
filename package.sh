#!/bin/bash
# Build a distributable hyprtile.equalize tarball.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"
PKG="hyprtile.equalize"

VERSION=$(
  python3 - "$ROOT/manifest.json" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
with path.open() as f:
    print(json.load(f).get("version", "0.0.0"))
PY
)

if [[ -z "$VERSION" ]]; then
  echo "Could not read version from manifest.json" >&2
  exit 1
fi

ARCHIVE="$DIST/${PKG}-${VERSION}.tar.gz"
FILES=(
  README.md
  manifest.json
  EqualizeToggle.qml
  install.sh
  scripts
)

mkdir -p "$DIST"

echo "Building $ARCHIVE"
tar -czf "$ARCHIVE" \
  --transform "s|^|${PKG}/|" \
  -C "$ROOT" \
  "${FILES[@]}"

echo "Created $(basename "$ARCHIVE")"
echo "Contents:"
tar -tzf "$ARCHIVE"

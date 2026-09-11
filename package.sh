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
  LICENSE
  manifest.json
  EqualizeToggle.qml
  Service.qml
  scripts
)

mkdir -p "$DIST"

# Stage in a temp dir so the working tree is left untouched while the
# distributed copy gets the version baked into EqualizeToggle.qml.
STAGE="$DIST/.stage-$PKG"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r -t "$STAGE" "${FILES[@]}"

python3 - "$STAGE/EqualizeToggle.qml" "$VERSION" <<'PY'
import pathlib, sys
qml = pathlib.Path(sys.argv[1])
version = sys.argv[2]
text = qml.read_text()
replaced = False

def bake(match):
    global replaced
    replaced = True
    return match.group(1) + version + match.group(2)

new = __import__("re").sub(
    r'(property string pluginVersion: ")[^"]*(")',
    bake,
    text,
)
if not replaced:
    raise SystemExit("package.sh: no pluginVersion property found in " + str(qml))
if new != text:
    qml.write_text(new)
PY

echo "Building $ARCHIVE"
tar -czf "$ARCHIVE" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --transform "s|^|${PKG}/|" \
  -C "$STAGE" \
  "${FILES[@]}"

rm -rf "$STAGE"

echo "Created $(basename "$ARCHIVE")"
echo "Contents:"
tar -tzf "$ARCHIVE"

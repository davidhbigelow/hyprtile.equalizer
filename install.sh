#!/bin/bash
# Install using a fixed interpreter; the helper does not resolve tools via PATH.

set -euo pipefail

readonly PYTHON=/usr/bin/python3
readonly SCRIPT_PATH=${BASH_SOURCE[0]}
if [[ "$SCRIPT_PATH" == */* ]]; then
  readonly SCRIPT_DIR=${SCRIPT_PATH%/*}
else
  readonly SCRIPT_DIR=.
fi

if [[ ! -x "$PYTHON" ]]; then
  printf 'error: required interpreter is unavailable: %s\n' "$PYTHON" >&2
  exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/scripts/_equalize_install.py" "$SCRIPT_DIR"

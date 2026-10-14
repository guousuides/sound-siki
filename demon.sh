#!/bin/sh
# Convenience launcher for macOS / Linux: ./demon.sh train cicada
here="$(cd "$(dirname "$0")" && pwd)"
py="$here/.venv/bin/python"
[ -x "$py" ] || py=python3
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
exec "$py" -m demon "$@"

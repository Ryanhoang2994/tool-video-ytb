#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && . .venv/bin/activate
python studio.py ui "$@"

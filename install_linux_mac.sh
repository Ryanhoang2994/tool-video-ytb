#!/usr/bin/env bash
set -e
command -v ffmpeg >/dev/null || echo "Hãy cài ffmpeg: sudo apt install ffmpeg  |  brew install ffmpeg"
python3 -m venv .venv && . .venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "Xong. Kích hoạt: . .venv/bin/activate ; chạy: python studio.py --help"

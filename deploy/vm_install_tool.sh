#!/usr/bin/env bash
# Chạy trong thư mục coldcase_studio trên VPS.
#   bash deploy/vm_install_tool.sh          # đầy đủ: cào + giọng + render
#   bash deploy/vm_install_tool.sh scrape   # NHẸ: chỉ cào tư liệu/ảnh/video (máy nhỏ e2-small/e2-medium là đủ)
set -e
if [ -d /var/log ] && [ -f /var/log/coldcase_setup_done ] || command -v ffmpeg >/dev/null; then :; else
  until [ -f /var/log/coldcase_setup_done ] || command -v ffmpeg >/dev/null; do echo "Đợi cài ffmpeg..."; sleep 10; done
fi
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
if [ "${1:-}" = "scrape" ]; then
  pip install -q -r requirements-scrape.txt
else
  pip install -q -r requirements.txt
fi
[ -f .env ] || cp .env.example .env
echo "Xong. Mỗi lần dùng: cd ~/coldcase_studio && . .venv/bin/activate"
echo "Chạy việc dài trong tmux:  tmux new -s job   (thoát: Ctrl+B rồi D, vào lại: tmux attach -t job)"

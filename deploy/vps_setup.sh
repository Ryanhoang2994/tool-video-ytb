#!/usr/bin/env bash
# Cài Cold Case Studio lên VPS Ubuntu (Google Cloud) - chạy 1 lần SAU KHI đã `gh auth login`:
#   bash vps_setup.sh
# Kết quả: tool ở ~/coldcase_studio, giao diện chạy nền 24/7 (tự bật lại khi khởi động máy) ở 127.0.0.1:7860,
# Claude Code đã cài (gõ `claude` 1 lần để đăng nhập tài khoản Claude).
set -euo pipefail
REPO="${REPO:-Ryanhoang2994/tool-video-ytb}"
DIR="$HOME/coldcase_studio"

echo "== 1. Gói hệ thống =="
sudo apt-get update -y
sudo apt-get install -y git gh ffmpeg python3-venv python3-pip tmux fonts-dejavu-core unzip curl

echo "== 2. Lấy tool từ GitHub =="
if [ ! -d "$DIR/.git" ]; then
  gh auth status >/dev/null 2>&1 || { echo "Chạy 'gh auth login' trước (chọn GitHub.com > HTTPS > Login with a web browser)"; exit 1; }
  gh repo clone "$REPO" "$DIR"
else
  git -C "$DIR" pull --ff-only
fi
cd "$DIR"

echo "== 3. Thư viện Python =="
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt || {
  echo "Cài chung lỗi - cài từng thư viện..."
  grep -vE '^\s*(#|$)' requirements.txt | awk '{print $1}' | while read -r p; do pip install -q "$p" || echo "  ! không cài được $p"; done
}
[ -f .env ] || cp .env.example .env

echo "== 4. Claude Code (viết kịch bản bằng gói Claude, không cần API key) =="
command -v claude >/dev/null || curl -fsSL https://claude.ai/install.sh | bash || true

echo "== 5. Giao diện chạy nền (systemd) =="
sudo tee /etc/systemd/system/coldcase-ui.service >/dev/null <<EOF
[Unit]
Description=Cold Case Studio UI
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
Environment=PATH=$HOME/.local/bin:$DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$DIR/.venv/bin/python studio.py ui --no-browser --host 127.0.0.1 --port 7860
Restart=always

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now coldcase-ui
sleep 3
systemctl --no-pager --lines=3 status coldcase-ui || true

cat <<'EOF'

== XONG ==
1) Đăng nhập Claude (1 lần):   ~/.local/bin/claude     -> chọn "Claude account with subscription" -> /exit
2) Trên MÁY CỦA BẠN mở giao diện qua đường hầm SSH (an toàn, không mở cổng ra Internet):
     gcloud compute ssh coldcase-vps --zone asia-southeast1-b -- -L 7860:localhost:7860
   rồi mở trình duyệt: http://127.0.0.1:7860   (giữ cửa sổ ssh đó mở trong lúc dùng)
3) Cập nhật tool: bấm nút cập nhật trong giao diện, rồi:  sudo systemctl restart coldcase-ui
EOF

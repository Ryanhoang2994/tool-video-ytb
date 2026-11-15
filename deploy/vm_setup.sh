#!/usr/bin/env bash
# Startup script: cài phần mềm hệ thống cho VPS (chạy 1 lần lúc tạo máy, quyền root).
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ffmpeg python3-venv python3-pip unzip tmux fonts-dejavu fonts-liberation fonts-roboto-unhinted
touch /var/log/coldcase_setup_done

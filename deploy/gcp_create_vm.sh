#!/usr/bin/env bash
# Tạo VPS Google Cloud để cào ảnh / research / tạo giọng / render (KHÔNG chạy CapCut - CapCut cần PC Windows).
# Chạy trên máy bạn (đã cài Google Cloud CLI, đã `gcloud auth login`, đã chọn project có bật thanh toán).
#   bash deploy/gcp_create_vm.sh            # máy nhỏ: cào ảnh + giọng + research (~25 USD/tháng nếu bật 24/7)
#   MACHINE=c2d-highcpu-8 bash deploy/gcp_create_vm.sh   # máy mạnh để render nhanh (~0.3 USD/giờ, nhớ TẮT khi xong)
set -euo pipefail
NAME="${NAME:-coldcase-vps}"
ZONE="${ZONE:-asia-southeast1-b}"          # Singapore - gần Việt Nam
MACHINE="${MACHINE:-e2-standard-4}"        # 4 vCPU, 16 GB RAM
DISK="${DISK:-80}"                          # GB
SPOT="${SPOT:-false}"                       # true = rẻ hơn ~60-70% nhưng Google có thể tắt máy bất cứ lúc nào

EXTRA=()
[ "$SPOT" = "true" ] && EXTRA+=(--provisioning-model=SPOT --instance-termination-action=STOP)

gcloud services enable compute.googleapis.com texttospeech.googleapis.com

gcloud compute instances create "$NAME" \
  --scopes=cloud-platform \
  --zone="$ZONE" --machine-type="$MACHINE" \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size="${DISK}GB" --boot-disk-type=pd-balanced \
  --metadata-from-file=startup-script="$(dirname "$0")/vm_setup.sh" \
  "${EXTRA[@]}"

echo
echo "Đợi ~3 phút cho máy cài xong, rồi:"
echo "  gcloud compute scp --zone $ZONE coldcase_studio.zip $NAME:~/"
echo "  gcloud compute ssh --zone $ZONE $NAME"
echo "  # trên VPS:  unzip coldcase_studio.zip && cd coldcase_studio && bash deploy/vm_install_tool.sh"
echo "Tắt máy khi không dùng (không mất dữ liệu, chỉ trả tiền ổ đĩa):"
echo "  gcloud compute instances stop --zone $ZONE $NAME"

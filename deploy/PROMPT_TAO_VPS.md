# Đoạn chat cho Claude in Chrome: tạo VPS Google Cloud chạy Cold Case Studio

Mở sẵn https://console.cloud.google.com (đã đăng nhập), dán nguyên đoạn dưới vào Claude in Chrome.
Xong thì tự đăng nhập Claude trên VPS (`~/.local/bin/claude`) và gửi lại BÁO CÁO VPS.

```
Bạn là trợ lý thao tác trên trình duyệt. Hãy giúp tôi tạo một máy chủ ảo (VPS) trên Google Cloud để chạy tool làm video "Cold Case Studio" (repo GitHub riêng: Ryanhoang2994/tool-video-ytb). Tôi đang đăng nhập sẵn Google Cloud Console.

QUY TẮC AN TOÀN (bắt buộc):
- KHÔNG nhập/sửa thông tin thẻ, KHÔNG nạp tiền, KHÔNG đổi tài khoản thanh toán. Nếu Google đòi bật thanh toán/xác minh thẻ thì DỪNG và báo tôi tự làm.
- KHÔNG tạo API key, service account key, KHÔNG mở cổng firewall ra Internet (không mở cổng 7860).
- KHÔNG chép mật khẩu, mã xác minh, token vào báo cáo. Bước nào cần đăng nhập/nhập mã thì hỏi tôi làm.
- Trước khi bấm Create máy, tóm tắt cấu hình + chi phí ước tính và hỏi tôi đồng ý.

VIỆC 1 – Tạo máy ảo
1. Vào Compute Engine → VM instances (nếu được hỏi bật Compute Engine API thì bật).
2. Create instance với cấu hình:
   - Name: coldcase-vps
   - Region: asia-southeast1 (Singapore), Zone: asia-southeast1-b
   - Machine type: e2-standard-8 (8 vCPU, 32 GB). Nếu báo hết tài nguyên/quota thì dùng e2-standard-4.
   - Boot disk: Ubuntu 24.04 LTS (x86/64), Balanced persistent disk, 100 GB
   - Firewall: KHÔNG tick Allow HTTP / HTTPS
3. Chờ máy chạy (Running).

VIỆC 2 – Cài tool trên máy (dùng nút SSH trong trình duyệt của Google Cloud)
Bấm nút SSH cạnh coldcase-vps, chờ cửa sổ dòng lệnh mở, rồi chạy lần lượt từng lệnh, chờ xong mới chạy lệnh tiếp:
   sudo apt-get update && sudo apt-get install -y gh
   gh auth login
     (chọn: GitHub.com → HTTPS → Y → Login with a web browser; lệnh sẽ hiện 1 MÃ 8 ký tự + link github.com/login/device. Đưa mã cho tôi và để TÔI tự nhập trên trang GitHub, rồi bấm Enter trong cửa sổ SSH.)
   gh repo clone Ryanhoang2994/tool-video-ytb coldcase_studio
   bash coldcase_studio/deploy/vps_setup.sh
     (mất 5–15 phút, chữ chạy liên tục là bình thường, chờ tới khi thấy "== XONG ==")
   systemctl is-active coldcase-ui
   ~/.local/bin/claude --version
Bước đăng nhập Claude (lệnh ~/.local/bin/claude) để TÔI tự làm, bạn không cần chạy.

VIỆC 3 – Báo cáo cuối (KHÔNG chứa mật khẩu/mã/token), đúng mẫu:
=== BÁO CÁO VPS ===
Tên máy: 
Zone: 
Loại máy: 
Ổ đĩa: 
Trạng thái máy: 
External IP: 
Kết quả gh repo clone: (thành công / lỗi gì)
Kết quả vps_setup.sh: (có thấy "== XONG ==" không; nếu lỗi: chép 20 dòng cuối)
systemctl is-active coldcase-ui: 
claude --version: 
Chi phí ước tính/giờ Google hiển thị: 
Ghi chú / bước nào phải dừng hỏi tôi: 
===================
```

# Hướng dẫn dựng VPS Google Cloud để chạy Cold Case Studio

Có 2 cách dùng VPS:

| Cách | VPS làm gì | Máy nên chọn | Chi phí tham khảo |
|---|---|---|---|
| **A. Chỉ cào ảnh + video** *(khuyên dùng)* | research, kịch bản, cào ảnh/video/ảnh AI → đóng gói gửi về PC | **e2-medium** (2 vCPU, 4 GB), ổ 40 GB | ~0,04 USD/giờ, bật 24/7 ~25-30 USD/tháng |
| B. Làm trọn gói | thêm giọng đọc + render MP4 | e2-standard-4 (4 vCPU, 16 GB), ổ 80 GB | ~0,15-0,20 USD/giờ |

Cách A: giọng đọc (VieNeu), render và CapCut chạy trên PC của bạn. VPS có IP riêng nên cào Wikimedia,
Library of Congress, Pexels... nhanh và ít bị chặn hơn.

## Cách A – VPS chỉ để cào ảnh + video (tóm tắt)

1. Làm mục 1 bên dưới (tài khoản, project, bật Compute Engine API).
2. Tạo VPS như mục 2 nhưng chọn **e2-medium** và ổ **40 GB** (không cần chọn full access API).
3. SSH vào → Upload `coldcase_studio.zip` → chạy:
```bash
sudo apt-get update && sudo apt-get install -y ffmpeg python3-venv unzip tmux
```
```bash
unzip -o coldcase_studio.zip && cd coldcase_studio && bash deploy/vm_install_tool.sh scrape
```
4. `nano .env` → điền `ANTHROPIC_API_KEY` (nếu viết kịch bản trên VPS), `PEXELS_API_KEY`, `PIXABAY_API_KEY`.
5. Cào (trong `tmux new -s job`, sau `. .venv/bin/activate`):
```bash
python studio.py new "Tên vụ án" --en "English keywords" --years 1970-1975
```
```bash
python studio.py script ten-vu-an
```
```bash
python studio.py media ten-vu-an
```
```bash
python studio.py pack ten-vu-an
```
   (Đã có kịch bản sẵn? Upload file JSON rồi `python studio.py script ten-vu-an --import-json kichban.json` thay cho lệnh `script`.)
   Muốn chỉ gom ảnh vào thư viện theo chủ đề: `python studio.py collect "Tên vụ án" --max 300`.
6. **Download file** → `/home/<tên_user>/coldcase_studio/ten-vu-an_pack.zip` về PC.
7. Trên PC (thư mục tool): giải nén gói rồi làm giọng, render, CapCut:
```bash
python studio.py unpack ten-vu-an_pack.zip
```
```bash
python studio.py all ten-vu-an
```
8. **Stop** VPS khi không cào (mục 9).

---

Phần dưới là hướng dẫn chi tiết (dùng chung cho cả 2 cách).

---

## 1. Tạo tài khoản và project (làm 1 lần)

1. Vào **https://console.cloud.google.com** → đăng nhập Gmail.
2. Bấm **"Dùng thử miễn phí / Start free"**: tài khoản mới được **300 USD dùng trong 90 ngày**.
   Cần thẻ Visa/Mastercard để xác minh; Google không tự trừ tiền khi hết dùng thử trừ khi bạn bấm nâng cấp.
3. Thanh trên cùng → **chọn project → New Project** → đặt tên `coldcase-studio` → **Create**.
4. Ô tìm kiếm trên cùng, lần lượt gõ và bấm **Enable (Bật)**:
   - **Compute Engine API** (bắt buộc – để tạo VPS)
   - **Cloud Text-to-Speech API** (chỉ khi muốn dùng giọng Google Chirp 3 HD)
5. **Đặt cảnh báo chi phí**: Menu ☰ → **Billing → Budgets & alerts → Create budget** → 20 USD →
   tick gửi email khi đạt 50% / 90% / 100%.

## 2. Tạo VPS

Menu ☰ → **Compute Engine → VM instances → Create instance**:

| Mục | Chọn |
|---|---|
| Name | `coldcase-vps` |
| Region / Zone | `asia-southeast1 (Singapore)` – gần Việt Nam |
| Machine configuration | **E2 → e2-standard-4** (4 vCPU, 16 GB RAM) |
| Boot disk → Change | **Ubuntu 24.04 LTS (x86/64)**, loại **Balanced persistent disk**, **80 GB** |
| Identity and API access → Access scopes | **Allow full access to all Cloud APIs** (để giọng Google chạy không cần key) |
| (Tuỳ chọn) Advanced → Management → VM provisioning model | **Spot** – rẻ hơn ~60-70% nhưng Google có thể tắt máy giữa chừng |

Bấm **Create**. Khoảng 1 phút là máy chạy.

> Chi phí tham khảo: e2-standard-4 ≈ 0,15-0,20 USD/giờ khi đang bật. Một video 40 phút
> (cào ảnh + giọng VieNeu + render) mất khoảng 2-3 giờ máy ≈ 0,5 USD. **Tắt máy khi không dùng**
> → chỉ còn tiền ổ đĩa ≈ 8 USD/tháng cho 80 GB.

## 3. Kết nối vào VPS

Trong danh sách VM instances, bấm nút **SSH** ở dòng `coldcase-vps` → mở cửa sổ dòng lệnh ngay trong trình duyệt.

## 4. Đưa tool lên và cài đặt

Trong cửa sổ SSH: bấm **⬆ UPLOAD FILE** (góc trên phải) → chọn `coldcase_studio.zip` trên máy bạn.
Rồi dán lần lượt các lệnh:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg python3-venv unzip tmux fonts-dejavu fonts-liberation fonts-roboto-unhinted
```
```bash
unzip -o coldcase_studio.zip && cd coldcase_studio && bash deploy/vm_install_tool.sh
```

Lần đầu cài mất ~5-10 phút (thư viện giọng VieNeu khá nặng).

## 5. Điền key

```bash
nano .env
```
Điền (không có key nào thì để trống dòng đó):
- `ANTHROPIC_API_KEY` – Claude viết kịch bản (console.anthropic.com)
- `PEXELS_API_KEY`, `PIXABAY_API_KEY` – video/ảnh B-roll (miễn phí)
- `POLLINATIONS_TOKEN` – ảnh AI đẹp hơn (miễn phí, auth.pollinations.ai)

Lưu: `Ctrl+O` → `Enter` → thoát: `Ctrl+X`.
Chỉnh cấu hình (giọng, phong cách...): `nano config.yaml`.

## 6. Chạy làm video

Luôn chạy trong **tmux** để đóng trình duyệt máy vẫn chạy tiếp:

```bash
tmux new -s job
```
```bash
cd ~/coldcase_studio && . .venv/bin/activate
```
```bash
python studio.py new "Tên vụ án" --en "English keywords" --years 1970-1975
```
```bash
python studio.py all ten-vu-an --skip-capcut
```

- Thoát tmux nhưng để máy chạy tiếp: bấm `Ctrl+B` rồi `D`.
- Mở lại để xem tiến độ (kể cả sau khi SSH lại): `tmux attach -t job`
- Nghe thử giọng trước: `python studio.py voices --vieneu`

## 7. Tải video về

Trong cửa sổ SSH: **⬇ DOWNLOAD FILE** → nhập đường dẫn, ví dụ:
```
/home/<tên_user>/coldcase_studio/projects/ten-vu-an/output/final.mp4
```
(`<tên_user>` xem bằng lệnh `whoami`). Làm tương tự với `thumbnail.jpg`, `youtube_upload.txt`, `credits.txt`.

## 8. (Tuỳ chọn) Mở trong CapCut để chỉnh tay

Trên VPS: `python studio.py pack ten-vu-an` → tải `ten-vu-an_pack.zip` về PC Windows (đã cài tool) →
```bash
python studio.py unpack ten-vu-an_pack.zip
```
```bash
python studio.py capcut ten-vu-an
```

## 9. TẮT MÁY khi xong

VM instances → dấu **⋮** ở dòng `coldcase-vps` → **Stop**. Dữ liệu vẫn còn nguyên, lần sau bấm **Start**.
Xoá hẳn (hết cả tiền ổ đĩa): **Delete**.

## Muốn render nhanh hơn?

- Edit VM (khi đang Stop) → đổi machine sang **c2d-highcpu-8** hoặc **e2-highcpu-16** → Start.
  Render nhanh gấp 2-4 lần, giá theo giờ cao hơn → chỉ bật lúc render.
- Giọng VieNeu chạy nhanh hơn nhiều trên GPU (máy có NVIDIA T4/L4) nhưng GPU đắt và tài khoản mới
  thường phải xin hạn mức (quota) GPU trước. CPU là đủ dùng.

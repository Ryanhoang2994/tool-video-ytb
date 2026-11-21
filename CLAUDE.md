# Ghi chú dự án cho Claude Code

Chủ kênh nói tiếng Việt: trả lời bằng tiếng Việt, ngắn gọn, từng bước, lệnh để trong khối riêng.
Máy chủ là Windows (PowerShell; chạy file .bat phải có `.\` ở đầu). Python trong `.venv` (`.\.venv\Scripts\python.exe`).
Viết kịch bản bằng gói Claude của chủ kênh qua `claude -p` (không có API key) – mọi việc gọi Claude đều tốn lượt của gói.

## 5 kênh (batch/queue.yaml)

| Kênh | Nền tảng | Ngôn ngữ | Độ dài | Preset |
|---|---|---|---|---|
| vu_an | YouTube Mỹ | tiếng Anh + bản dịch `-vi` để đọc hiểu | 30 phút | crime_doc |
| lich_su | YouTube Mỹ | tiếng Anh + `-vi` | 25 phút | crime_doc |
| tham_hoa | YouTube Mỹ | tiếng Anh + `-vi` | 25 phút | crime_doc |
| chuyen_ma | Facebook VN | tiếng Việt | 12 phút | mystery_horror (truyện hư cấu) |
| me_va_be | Facebook VN | tiếng Việt | 6 phút | psychology_2d |

Chưa đặt tên kênh: `channel_name: ""` → kịch bản chỉ nói "đăng ký kênh", không nêu tên nào.

## Việc thường làm

- Tiến độ: `.\.venv\Scripts\python.exe batch.py --status` (ghi ra `batch/TIEN_DO.txt`).
- Viết hàng loạt: `.\viet_kich_ban.bat` (hoặc `python batch.py --yes --channel <kênh>`). Bỏ qua tập đã có kịch bản,
  hết lượt Claude tự chờ tới giờ reset, Ctrl+C rồi chạy lại là tiếp tục. Nhật ký từng tập: `batch/logs/<slug>.log`.
- Thêm chủ đề: thêm dòng `Chủ đề | năm` vào `batch/topics/<kênh>.txt`.
- Làm 1 video: xem README mục 2 (`studio.py media / voice / timeline / render / check`), hoặc giao diện `start_ui.bat`.
- Cập nhật tool: `.\update.bat` (git pull + cài thư viện).

## Quy tắc nội dung (bắt buộc)

- Chỉ dùng nguồn ảnh có giấy phép (Wikimedia Commons, Library of Congress, Openverse…). Không cào ảnh/video từ
  YouTube, Facebook, TikTok, Google Images.
- Không vẽ mặt người thật / nạn nhân thật bằng AI; ảnh AI minh hoạ không được giả làm ảnh thật của sự kiện.
- Vụ án: không tả chi tiết ghê rợn, không hướng dẫn cách làm ma tuý; với người còn sống chỉ nói điều toà đã xác định.
- Lịch sử: không ca ngợi phát xít; tránh Chiến tranh Việt Nam, chiến tranh biên giới 1979 và chiến tranh đang diễn ra.
- Hiệu ứng hù doạ (jumpscare, flicker, giọng ma) CHỈ cho truyện hư cấu, không dùng cho sự kiện có nạn nhân thật.
- Mẹ và bé: chỉ theo WHO, UNICEF, Bộ Y tế, AAP; không chẩn đoán, không kê thuốc; giữ câu kết "Thông tin chỉ để tham khảo…".
- Kịch bản chỉ viết khi có nguồn Wikipedia (research tự dừng nếu Wikipedia không trả kết quả).

## Bảo mật

- Key (ElevenLabs, Google…) chỉ nằm trong `.env` trên máy hoặc ô Cài đặt của giao diện; `.env` không bao giờ đưa lên GitHub.
  Không in key ra màn hình, không dán key vào chat.
- Không nhập thông tin thẻ / thanh toán, không tạo key mới thay chủ kênh.

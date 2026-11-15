# Prompt cho Claude trên Chrome – dựng VPS Google Cloud và cào ảnh/video

Dán toàn bộ khối dưới đây vào Claude trên Chrome (đang mở tab console.cloud.google.com, đã đăng nhập).

```text
Bạn giúp tôi dựng 1 VPS trên Google Cloud để chạy tool "Cold Case Studio" (Python) CHỈ ĐỂ CÀO tư liệu,
ảnh và video cho video tài liệu vụ án. Làm từng bước, báo cho tôi sau mỗi bước.

QUY TẮC AN TOÀN (bắt buộc):
- KHÔNG nhập/sửa thông tin thẻ, KHÔNG bấm "Thực hiện thanh toán", KHÔNG nâng cấp tài khoản. Nếu cần → dừng và hỏi tôi.
- KHÔNG tạo máy có GPU, KHÔNG chọn máy lớn hơn e2-medium, KHÔNG tạo quá 1 máy.
- KHÔNG mở firewall, KHÔNG gắn IP tĩnh, KHÔNG bật API nào ngoài Compute Engine API.
- Gặp hộp thoại chọn file trên máy tính → dừng và nhờ tôi tự chọn file.
- Trước mỗi thao tác tốn tiền (tạo VM), tóm tắt cấu hình và đợi tôi trả lời "OK".

BƯỚC 1 – Kiểm tra
- Nếu trên cùng còn dải vàng "Gói dùng thử miễn phí yêu cầu thanh toán trước" → dừng, báo tôi.
- Vào Thanh toán → Tín dụng, cho tôi biết số tín dụng dùng thử còn lại.
- Vào Thanh toán → Ngân sách & giới hạn. Nếu chưa có ngân sách thì tạo ngân sách tên "canh-bao",
  số tiền 500.000 đ, cảnh báo email ở 50%, 90%, 100%.

BƯỚC 2 – Project và API
- Tạo (hoặc chọn nếu đã có) project tên "coldcase-studio".
- Mở https://console.cloud.google.com/apis/library/compute.googleapis.com và bấm Enable (Bật).

BƯỚC 3 – Tạo VPS (đợi tôi OK trước khi bấm Create)
Mở https://console.cloud.google.com/compute/instancesAdd và đặt:
- Name: coldcase-vps
- Region: asia-southeast1 (Singapore), Zone mặc định
- Machine: series E2, loại e2-medium (2 vCPU, 4 GB)
- OS and storage → Change: Ubuntu, Ubuntu 24.04 LTS x86/64, dung lượng 40 GB, Balanced persistent disk
- Các mục khác để mặc định.

BƯỚC 4 – Cài tool
- Ở dòng coldcase-vps bấm SSH (mở cửa sổ dòng lệnh trong trình duyệt), bấm Authorize nếu được hỏi.
- Bấm UPLOAD FILE → DỪNG LẠI và nhờ tôi chọn file coldcase_studio.zip.
- Sau khi tôi upload xong, gõ lần lượt từng lệnh, đợi lệnh trước chạy xong mới gõ lệnh sau:
    sudo apt-get update && sudo apt-get install -y ffmpeg python3-venv unzip tmux
    unzip -o coldcase_studio.zip && cd coldcase_studio && bash deploy/vm_install_tool.sh scrape
  Thành công khi thấy chữ "Xong.".

BƯỚC 5 – Cào thử (vụ Amelia Earhart, kịch bản có sẵn)
    tmux new -s job
    cd ~/coldcase_studio && . .venv/bin/activate
    python studio.py script amelia-earhart --import-json projects/_auto_test_earhart.json
    python studio.py media amelia-earhart
    python studio.py pack amelia-earhart
Trong lúc "media" chạy, cứ ~2 phút đọc màn hình và báo tôi tiến độ ([1/8], [2/8]...,
các dòng "+ video", "+ ảnh AI", "nhân vật ..."). Lệnh có thể chạy 5-20 phút, đừng ngắt.
Dòng "! ... lỗi" lẻ tẻ là bình thường (nguồn nào lỗi tool tự bỏ qua).

BƯỚC 6 – Tải kết quả và tắt máy
- Trong cửa sổ SSH bấm DOWNLOAD FILE, nhập đường dẫn: coldcase_studio/amelia-earhart_pack.zip
- Quay lại danh sách VM instances → dấu ⋮ ở dòng coldcase-vps → Stop (KHÔNG Delete).
- Báo cáo cho tôi: số ảnh, số video, số ảnh AI tool đã lấy, các lỗi lặp lại nhiều lần (nếu có),
  và xác nhận máy đã ở trạng thái Stopped.

CÁC TRANG TOOL ĐƯỢC PHÉP CÀO (tool tự gọi API, bạn KHÔNG cần mở các trang này;
đây là danh sách để bạn hiểu và kiểm tra log):
Ảnh tư liệu (public domain / Creative Commons, tool tự ghi credit):
- Wikipedia (ảnh trong bài viết về vụ án) – en.wikipedia.org, vi.wikipedia.org
- Wikimedia Commons – commons.wikimedia.org, upload.wikimedia.org
- Library of Congress (ảnh + trang báo Mỹ 1770-1963) – www.loc.gov, tile.loc.gov
- Openverse (ảnh CC tổng hợp) – api.openverse.org
- Europeana (kho lưu trữ châu Âu) – api.europeana.eu
- Smithsonian Open Access (CC0) – api.si.edu
- Flickr Commons (cần key) – api.flickr.com
- Internet Archive – archive.org
- Pexels, Pixabay, Unsplash (ảnh stock miễn phí, cần key)
Video:
- Wikimedia Commons video (phim thời sự cũ, tư liệu chính phủ Mỹ) – không cần key
- Pexels Video, Pixabay Video (B-roll, cần key)
- Internet Archive (phim public domain)
Ảnh AI:
- Pollinations – image.pollinations.ai (miễn phí)
TUYỆT ĐỐI KHÔNG cào ảnh/video từ YouTube, Facebook, TikTok, Google Images, báo điện tử hay kênh khác
(vi phạm bản quyền).
```

## Sau khi Claude trên Chrome làm xong
- File `amelia-earhart_pack.zip` sẽ nằm trong thư mục Tải xuống của bạn.
- Trên PC (thư mục tool): `python studio.py unpack amelia-earhart_pack.zip` → `python studio.py all amelia-earhart`.
- Lần sau cào vụ mới, đổi BƯỚC 5 thành:
  `python studio.py new "Tên vụ án" --en "English keywords" --years 1970-1975`
  → `python studio.py script <slug>` (cần ANTHROPIC_API_KEY trong .env) → `python studio.py media <slug>`
  → `python studio.py pack <slug>`.

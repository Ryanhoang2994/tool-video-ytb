# 🕵️ Cold Case Studio

Tool tự động làm video tài liệu **vụ án / thảm án / tin tức thời xưa** dài ~40 phút cho YouTube:

```
Chủ đề ─► Thu thập tư liệu ─► Viết kịch bản (Claude) ─► Tìm/tải ảnh + video + tạo ảnh AI
       ─► Giọng đọc (TTS mã nguồn mở) ─► Dựng timeline + phụ đề ─► MP4 hoàn chỉnh + Draft CapCut + Thumbnail
```

| Bước | Lệnh | Kết quả |
|---|---|---|
| 1. Tư liệu | `new` / `research` | `research.json` – Wikipedia (vi/en), báo Mỹ 1770-1963 (Chronicling America), Internet Archive, link báo bạn đưa vào |
| 2. Kịch bản | `script` | `script.json` + `script.md` – ~6.000 từ, 8 chương, mỗi cảnh có từ khoá tìm hình + prompt ảnh AI |
| 3. Hình ảnh | `media` | Ảnh từ Wikimedia, Library of Congress, Openverse, Pexels, Pixabay; video từ Pexels, Pixabay, Internet Archive; thiếu thì tạo ảnh AI |
| 4. Giọng đọc | `voice` | `audio/*.wav` – edge-tts / Piper / viXTTS (clone giọng) / bất kỳ tool nào |
| 5. Dựng | `render` | `output/final.mp4`, `thumbnail.jpg`, `subtitles.srt`, `youtube_upload.txt` (tiêu đề, mô tả, **mốc chương**, credit) |
| 6. CapCut | `capcut` | Draft mở thẳng trong CapCut PC (ảnh có Ken Burns, giọng, nhạc, phụ đề trên các track riêng) |

---

## 0. Chọn phong cách theo ngách (preset)

```bat
python studio.py presets
```
| Preset | Ngách | Hình | Ghi chú |
|---|---|---|---|
| `crime_doc` | Vụ án, thảm án, tin xưa | Ảnh tư liệu thật, tông tối, bảng điều tra | Mặc định |
| `ocean_creatures` | Khám phá đại dương & sinh vật (kiểu Depth Theory) | Ảnh/video thật đúng loài + sơ đồ so sánh kích thước, bản đồ độ sâu, thợ lặn 2D | Âm nền dưới nước |
| `psychology_2d` | Tâm lý học đời thường | Nhân vật 2D cố định (vẽ bằng code) đổi biểu cảm/tư thế, bong bóng suy nghĩ, từ khoá, "bên ngoài vs bên trong" | Phụ đề, nhạc nhẹ |
| `housing_finance_2d` | Nhà ở / bất động sản / tài chính | Nhân vật 2D + biểu đồ chi phí, bảng thuê vs mua dựng từ số liệu | Có quốc gia/tiền tệ/thời điểm dữ liệu, tự kiểm tra phép tính |
| `mystery_horror` | Bí ẩn / kinh dị | Minh hoạ tối đỏ-đen, nhân vật 2D, nhịp chậm | Chọn loại truyện: hư cấu / truyền thuyết / sự kiện thật; tự chèn thẻ "truyện hư cấu" |

**Quy trình chung** (mỗi bước lưu file riêng, sửa phần nào làm lại phần đó):
```
Chọn preset → Nhập chủ đề + nguồn → Dàn ý → Kịch bản → Chia cảnh (storyboard) → Lời đọc → Hình + chuyển động → Dựng → Kiểm tra → Xuất
```
```bat
python studio.py --preset housing_finance_2d new "Mua nhà 600.000 USD cần chuẩn bị gì?" --en "home buying costs" ^
    --country "Hoa Kỳ" --currency USD --data-date 2026-10 --audience "người trẻ lần đầu mua nhà" --minutes 10 --url https://...
python studio.py all mua-nha-600-000-usd-can-chuan-bi-gi
```
Project nhớ preset và thông số, các lệnh sau không cần ghi lại `--preset`. Video dài mặc định 16:9, 1080p, ~10 phút.

**Đầu ra** (`projects/<slug>/`): `output/final.mp4`, `output/subtitles.srt`, `script.md`, **`storyboard.md` / `storyboard.csv`**
(mỗi cảnh: thời điểm, mục đích, lời đọc, hình, hành động, camera, chữ, âm thanh, nhân vật, số liệu, nguồn),
`output/credits.txt`, `output/thumbnail.jpg`, `output/youtube_upload.txt`, **`output/check_report.md`**.

### Video có CẢM XÚC (kiểu phim hoạt hình ngắn / phim tư liệu cắt dán)

Mỗi cảnh trong kịch bản có thêm các trường cảm xúc (Claude tự điền khi viết; tự viết JSON thì xem `examples/emotional_story.json`):

| Trường | Ý nghĩa |
|---|---|
| `mood` | ánh sáng: `night`, `rain` (có mưa rơi), `warm`, `phone` (tối, ánh điện thoại hắt lên mặt), `tense`, `sad`, `hopeful`, `dawn` |
| `music` | đổi nhạc theo cảm xúc: `calm`, `sad`, `tense`, `hopeful`, `dark`, `light`, `silence` (tắt nhạc trước câu chốt) |
| `pause_after` | giây im lặng sau câu đắt giá (0.8–1.5) |
| `hud` | bộ đếm góc màn hình xuyên suốt truyện (`SỐ DƯ 24.000.000đ`, `NGÀY KHÔNG CƯỢC: 90`) – đổi số thì tự chạy số |
| `insert` | màn hình chèn: `phone` (giờ + thông báo trượt xuống, có tiếng "ting"), `clock` (đồng hồ báo thức + tích tắc), `chat` (tin nhắn hiện lần lượt), `bank` (số dư) |
| `character.framing` | `closeup` = cận mặt (thấy rõ mắt thâm, nước mắt, mồ hôi); `auto` = tự cận mặt khi cảm xúc mạnh |
| `character.shadow` | "giọng nói trong đầu": bóng đen viền cam phát sáng + chữ viết tay màu cam |
| `fx` | nhấn nhá cả cảnh: `shudder` (man rợ: rung, lệch màu, chớp đỏ, "sting" ghê rợn, nhịp tim, nhạc kinh dị), `action` (nhạc trống dồn dập, giật camera + chớp trắng, tiếng va đập, cắt nhanh), `impact`, `reveal`, `glitch`; `auto` = tool tự đoán theo lời đọc (máu, xác, giết… / truy đuổi, nổ súng, lao vào…) |
| `emphasis` | cụm từ nguyên văn cần nhấn → đúng lúc giọng đọc tới (căn theo khoảng ngắt thật của file giọng): camera giật vào, "boom", chữ đập ra màn hình |
| `stat` | (kiểu cắt dán) con số lớn trên giấy đỏ, tự đếm lên: `{"value": 200000, "label": "ĐÔ LA TIỀN CHUỘC", "unit": "$"}` |

Biểu cảm mới: `tired, crying, anxious, panic, empty, determined, relieved, smirk`; tư thế mới: `phone, hug, cover, slump`.
Lúc dựng, nhân vật được tách lớp: thở nhẹ, chớp mắt, bật lên khi mới xuất hiện, nền trôi chậm phía sau.

- Chữ kể chuyện viết tay phía trên khung: `render.subtitle_style: story` (preset tâm lý & kinh dị đã bật).
- Tên video / tên chương: `render.chapter_style: overlay` (mặc định – hiện đè lên cảnh, lời kể KHÔNG dừng, có riser + boom),
  `card` (thẻ riêng kiểu cũ, có khoảng lặng), `none`. Tắt chữ nhấn đập ra màn hình: `edit.emphasis_text: false`;
  tắt tự đoán hiệu ứng: `edit.auto_fx: false`. Nhạc riêng cho hiệu ứng: `assets/music/action/`, `assets/music/horror/`.
- Nhạc thật theo cảm xúc: bỏ file vào `assets/music/sad/`, `assets/music/tense/`, `assets/music/hopeful/`, `assets/music/calm/`... (không có thì tool tự tạo nhạc đơn giản – nên thay bằng nhạc có bản quyền).
- Kiểu **cắt dán tư liệu** (nền giấy cũ, ảnh dán viền trắng + đỏ, ghim, chỉ đỏ, dải giấy ngày tháng, số lớn đếm lên):
  `python studio.py render <slug> --look collage` hoặc đặt `render.look: "collage"` trong preset.
  Cài thêm `pip install rembg` để tách nền người → hình cắt dán đúng dáng người như các kênh lớn.

### Brand kit (bộ nhận diện kênh)
`brand/<tên>.yaml`: thiết kế nhân vật (màu áo, quần, phụ kiện, độ dày nét), bảng màu, font, giọng đọc, phong cách nền.
Dùng: `new ... --brand <tên>` hoặc `render.brand` trong config. Nhân vật được **vẽ bằng code** nên giống hệt nhau ở mọi cảnh
(ảnh AI miễn phí không giữ được nhân vật nhất quán); AI chỉ vẽ nền. Biểu cảm: neutral, happy, smile, worried, sad, surprised,
thinking, smug, angry, nervous, scared. Tư thế: stand, wave, think, point, shrug, hold, cheer, sit.

### Sửa riêng một cảnh (không làm lại cả video)
```bat
python studio.py scene <slug> s012 --show
python studio.py scene <slug> s012 --narration "Lời mới" --rebuild          :: chỉ đọc lại cảnh này + dựng lại
python studio.py scene <slug> s012 --expression worried --pose think --thought "..." --keywords "A" "B" --rebuild
python studio.py scene <slug> s012 --prompt "new background ..." --regen-image --rebuild
python studio.py scene <slug> s012 --lock                                  :: giữ nguyên ảnh/giọng đã chọn
```
Khi dựng lại, tool chỉ render những đoạn đã thay đổi (đã test: sửa 1 cảnh → render 1/9 đoạn).

### Kiểm tra trước khi xuất
`python studio.py check <slug>` (tự chạy cuối lệnh `all`) → `output/check_report.md`: thời lượng, chính tả (Claude),
phát âm (số/viết tắt/ký hiệu), phụ đề, nhất quán nhân vật, **phép tính** (tính lại mọi `formula`), **số chưa xác minh /
thiếu nguồn**, khớp hình–lời, âm lượng (LUFS, đỉnh). Mục không tự kiểm được ghi "⬜ chưa kiểm tra được".

## 1a. Cài trên máy mới từ GitHub

Cần: Python 3.10+ (Windows: tick "Add to PATH"), Git, ffmpeg (script cài tự cài trên Windows bằng winget).

```bat
git clone https://github.com/<TÀI_KHOẢN>/<TÊN_REPO>.git coldcase_studio
cd coldcase_studio
install_windows.bat
```
Linux / macOS: `bash install_linux_mac.sh`.

Sau đó: mở `.env` điền API key (file này KHÔNG có trên GitHub, mỗi máy tự điền), sửa `capcut.drafts_dir` trong `config.yaml`.
Cập nhật tool khi có bản mới: `git pull` rồi `pip install -r requirements.txt`.

Dữ liệu video (thư mục `projects/`, `library/`) không đẩy lên GitHub vì rất nặng. Muốn mang một dự án sang máy khác:
`python studio.py pack <slug>` → chép file .zip sang máy mới → `python studio.py unpack <file.zip>`.

## 1. Cài đặt (Windows)

1. Cài **Python 3.10+** (python.org, tick *Add to PATH*) và **CapCut PC**.
2. Giải nén thư mục này, chạy `install_windows.bat` (tự cài ffmpeg + thư viện).
3. Mở `.env`, điền key:
   - `ANTHROPIC_API_KEY` – để Claude viết kịch bản (console.anthropic.com). Không có key thì dùng chế độ `--manual`.
   - `PEXELS_API_KEY`, `PIXABAY_API_KEY` – **miễn phí**, đăng ký ở pexels.com/api và pixabay.com/api/docs. Rất nên có (nguồn video B-roll chính).
4. Sửa `config.yaml`:
   - `capcut.drafts_dir` → thay `<TEN_USER>` bằng tên user Windows của bạn.
     (Trong CapCut: Cài đặt → *Draft location* để xem đúng đường dẫn.)
   - `channel.name` (đặt tên kênh của bạn), `voice.edge_voice`…
5. Bỏ vài file nhạc nền không bản quyền (YouTube Audio Library, Pixabay Music) vào `assets/music/`.

Mỗi lần dùng: mở CMD trong thư mục, chạy `.venv\Scripts\activate.bat`.

## 2. Làm một video (kênh tiếng Anh – mặc định)

```bat
:: 1) Tạo project + thu thập tư liệu (Wikipedia EN, báo Mỹ cũ, Internet Archive, link bạn đưa vào)
python studio.py new "The Lizzie Borden Murders" --years 1892-1893 ^
    --url https://link-bai-bao-1 https://link-bai-bao-2 --notes notes.txt

:: 2) Viết kịch bản tiếng Anh (~5.800 từ ≈ 40 phút). Đọc lại script.md, sửa script.json nếu cần!
python studio.py script the-lizzie-borden-murders

:: 3) Tìm ảnh/video cho từng cảnh
python studio.py media the-lizzie-borden-murders

:: 4) Giọng đọc
python studio.py voice the-lizzie-borden-murders

:: 5) Xem thử nhanh 12 shot đầu, rồi render đầy đủ
python studio.py render the-lizzie-borden-murders --preview
python studio.py render the-lizzie-borden-murders

:: 6) Xuất sang CapCut để chỉnh tay
python studio.py capcut the-lizzie-borden-murders
```

Hoặc chạy một mạch sau bước `new`: `python studio.py all <slug>`

Mọi bước đều **chạy tiếp được** nếu bị ngắt (đã làm xong thì bỏ qua), và file nằm trong `projects/<slug>/`.
Muốn làm video tiếng Việt: `config.yaml` → `channel.language: "vi"`, `words_per_minute: 155`,
`wikipedia_langs: ["vi","en"]`, `edge_voice: "vi-VN-NamMinhNeural"`.

### Sửa từng phần
```bat
:: tìm lại hình cho vài cảnh (sau khi sửa search_queries_en trong script.json)
python studio.py media <slug> --only s012 s013
:: gán ảnh/video bạn tự có (ảnh scan, ảnh mua bản quyền...) cho 1 cảnh
python studio.py media <slug> --scene s012 --add D:\anh\hien_truong.jpg D:\clip\police.mp4
:: tải 1 đoạn video từ link (CHỈ video Creative Commons / public domain / bạn được phép dùng)
python studio.py media <slug> --scene s020 --url https://... --start 1:05 --end 1:15
:: đọc lại vài cảnh sau khi sửa lời
python studio.py voice <slug> --redo s007
:: phong cách hình: vintage | noir (đen trắng) | clean ; in phụ đề cứng
python studio.py render <slug> --look noir --burn-subs
```

### Quy trình transcript → kịch bản mới → prompt ảnh → ảnh AI

```bat
:: transcript lấy từ youtube-transcript.io, lưu thành transcript.txt (chỉ làm THAM KHẢO sự kiện)
python studio.py new "The Lizzie Borden Murders" --reference transcript.txt
python studio.py script <slug>            :: viết kịch bản MỚI (đối chiếu Wikipedia/báo cũ, không chép câu chữ)
python studio.py imageprompts <slug>      :: "prompt 2": style bible + nhân vật cố định + prompt cho từng shot
python studio.py media <slug> --ai-only   :: tự tạo ảnh (Pollinations/Flux miễn phí, hoặc Stable Diffusion local)
:: ...hoặc tự tạo ảnh ở ChatGPT/Midjourney theo image_prompts.txt, đặt tên s001_1.png, s001_2.png...
python studio.py media <slug> --import-dir D:\anh_ai
python studio.py voice <slug>
python studio.py render <slug>  &  python studio.py capcut <slug>
```
Muốn kênh luôn dùng toàn ảnh AI: `config.yaml → media.mode: "ai_only"`.
Không có API key: `imageprompts <slug> --manual` xuất prompt để dán vào chatbot, rồi `--import-txt`.

### Không có API key Claude?
```bat
python studio.py script <slug> --manual        :: tạo prompt_for_claude.txt -> dán vào claude.ai
python studio.py script <slug> --import-json ket_qua.json
```
Hoặc tự viết kịch bản (`# Tên chương` để chia chương, `[img: từ khoá tiếng Anh]` cuối đoạn để gợi ý hình):
```bat
python studio.py script <slug> --from-text kichban.txt --title "Tên video"
```

## 3. Giọng đọc

**Tiếng Việt – nên dùng (xếp theo độ tự nhiên):**
| Backend | Chi phí | Ghi chú |
|---|---|---|
| `vieneu` *(mặc định)* | miễn phí | VieNeu-TTS (github.com/pnnbao97/VieNeu-TTS), >20 giọng Việt dựng sẵn (Bắc/Trung/Nam, kể chuyện/tin tức), clone giọng bạn từ 3-8 giây. Chạy CPU ~1x thời gian thực. Nghe thử: `python studio.py voices --vieneu` |
| `google` | 1 triệu ký tự/tháng miễn phí, sau đó ~30 USD/1 triệu | Chirp 3 HD `vi-VN-Chirp3-HD-*`. Trên VPS Google Cloud chạy luôn không cần key |
| `elevenlabs` | ~0,10 USD/1.000 ký tự (~5-6 USD/video 40 phút) | `eleven_v3`, cần `ELEVENLABS_API_KEY` + `voice_id` |
| `edge` | miễn phí | Microsoft, ổn nhưng kém tự nhiên hơn |

`voice.polish: true` làm đẹp giọng kiểu phòng thu (EQ ấm, giảm xì, nén, chút không gian) cho mọi engine.
Kiểm tra giấy phép mô hình trước khi dùng cho kênh bật kiếm tiền.

### Tiếng Anh (tất cả mã nguồn mở trên GitHub)

| Backend | Repo | Ưu | Nhược |
|---|---|---|---|
| `edge` *(mặc định)* | github.com/rany2/edge-tts | Rất tự nhiên, miễn phí, không cần GPU. Giọng hợp true crime: `en-US-ChristopherNeural` (trầm), `en-GB-RyanNeural` (Anh), `en-US-AndrewNeural` | Cần Internet; nhiều kênh dùng chung giọng |
| `kokoro` | github.com/hexgrad/kokoro | **Offline, chất lượng gần ElevenLabs**, chạy CPU. Giọng: `am_michael`, `am_fenrir`, `bm_george`, `bm_lewis` | Cài thêm: `pip install kokoro soundfile` (+ espeak-ng trên Windows nếu báo lỗi) |
| `xtts` | coqui XTTS-v2 (huggingface `coqui/XTTS-v2`) | **Clone giọng riêng** từ file mẫu 6-15 giây → kênh có giọng độc quyền | Cần GPU NVIDIA, cài nặng; giấy phép CPML (đọc kỹ nếu kiếm tiền) |
| `api` | **VoiceStudio** – github.com/debpalash/VoiceStudio (app desktop, AGPL-3.0) | Giao diện dễ dùng, clone giọng / thiết kế giọng bằng mô tả, nhiều engine (OmniVoice, CosyVoice, VoxCPM2…), có API local chuẩn OpenAI → tool gọi thẳng | Engine mặc định OmniVoice có trọng số **CC-BY-NC (phi thương mại)** – xem mục 3b |
| `omnivoice` | github.com/k2-fsa/OmniVoice | Clone giọng 600+ ngôn ngữ, chạy thẳng bằng Python, không cần mở app | Cần GPU; cùng vấn đề giấy phép trọng số NC |
| `piper` | github.com/OHF-Voice/piper1-gpl | Offline, rất nhanh, nhẹ | Kém tự nhiên hơn (`en_US-ryan-high`) |
| `command` | F5-TTS, GPT-SoVITS… | Gọi bất kỳ tool nào qua dòng lệnh | Tự cấu hình |

```bat
python studio.py voices --list en                 :: liệt kê giọng edge tiếng Anh
python studio.py voice <slug> --voice en-GB-RyanNeural
pip install kokoro soundfile
python studio.py voice <slug> --backend kokoro    :: đổi giọng: config.yaml -> voice.kokoro_voice
python studio.py voices --piper en_US-ryan-high
pip install coqui-tts huggingface_hub & python studio.py voices --xtts   :: rồi đặt giọng mẫu vào voices/my_voice.wav
```
Gợi ý: nghe thử 2-3 giọng trên cùng 1 đoạn (`--redo s001`) rồi chọn. Giọng là "thương hiệu" của kênh – dùng cố định.

### 3b. Dùng VoiceStudio thay ElevenLabs

1. Cài VoiceStudio: tải bản Windows ở trang Releases của github.com/debpalash/VoiceStudio
   (hoặc PowerShell: `irm https://voicestudio.sh/install.ps1 | iex`).
2. Trong app: **Model Manager** → tải engine → **Voice cloning** → đưa file giọng mẫu sạch 10-20 giây
   → lưu thành *voice profile*, ví dụ tên `Narrator`.
3. `config.yaml`: `voice.backend: "api"`, `voice.api_voice: "Narrator"` (app chạy API ở `http://127.0.0.1:3900/v1`).
4. Mở app VoiceStudio, rồi chạy `python studio.py voice <slug>`.

⚠️ **Giấy phép, quan trọng nếu kênh bật kiếm tiền**: code VoiceStudio là AGPL-3.0 (được dùng thương mại).
Nhưng **trọng số model OmniVoice** (engine mặc định) được ghi là **CC-BY-NC = cấm dùng thương mại** (theo
`docs/model-credits.md` của VoiceStudio và model card k2-fsa/OmniVoice trên HuggingFace). Video YouTube có bật kiếm
tiền là sử dụng thương mại. Trước khi dùng cho kênh kiếm tiền, hãy mở **Model Manager**, xem giấy phép của từng
engine và chọn engine cho phép thương mại; hoặc dùng Kokoro (Apache-2.0) hay edge-tts.
Ngoài ra **chỉ clone giọng của chính bạn** hoặc giọng bạn có văn bản đồng ý (không clone giọng người nổi tiếng hay giọng
narrator của kênh khác).

## 3c. Cào & thu thập ảnh (thư viện dùng chung)

| Nguồn | Nội dung | Key |
|---|---|---|
| `wiki_article` | **Ảnh nằm trong chính bài Wikipedia về vụ án** (nhân vật, ngôi nhà, hiện trường thật) | – |
| `loc_news` | Trang báo Mỹ 1770-1963 scan (Library of Congress) → dựng thành "mẩu báo" | – |
| `wikimedia` / `loc` / `openverse` | Ảnh lịch sử public domain / CC | – |
| `europeana` | Kho lưu trữ châu Âu (ảnh cũ, tài liệu) | tuỳ chọn (có key demo) |
| `smithsonian` | Smithsonian Open Access (CC0) | tuỳ chọn (có DEMO_KEY) |
| `flickr` | Flickr Commons (bảo tàng, thư viện quốc gia) | `FLICKR_API_KEY` |
| `archive_img` | Internet Archive | – |
| `pexels` / `pixabay` / `unsplash` | Ảnh/video stock hiện đại (không khí, B-roll) | key miễn phí |

**Nguồn video** (`media.video_sources`): `wikimedia_video` (phim thời sự cũ, tư liệu chính phủ Mỹ, NASA, video CC –
**không cần key**), `loc_video` (phim Library of Congress), `pexels_video`, `pixabay_video` (cần key, nhiều B-roll
hiện đại nhất), `archive_video` (Internet Archive). Tool tự bỏ video quay dọc, chỉ cắt 1 đoạn ngắn (không tải cả phim
dài), đổi sang MP4 720p; video lệch tỉ lệ được đặt giữa trên nền mờ.

**Ảnh AI** (`media.ai_backend`):
| Backend | Chi phí | Ghi chú |
|---|---|---|
| `pollinations` | miễn phí | ~5 giây/ảnh. Bản free có logo → tool tự cắt; đăng ký token miễn phí (auth.pollinations.ai), đặt `POLLINATIONS_TOKEN` để dùng Flux, nét hơn |
| `openai` | trả phí/ảnh | gpt-image-1, đẹp và nghe lời prompt nhất. Cần `OPENAI_API_KEY` |
| `a1111` | miễn phí | Stable Diffusion WebUI / Forge (chạy Flux) trên máy có card NVIDIA |

Ảnh AI chỉ nên dùng cho **không khí** (đêm mưa, rừng, bóng người, đồ vật). Đừng dùng ảnh AI thay ảnh thật của người hay
sự kiện có thật; YouTube yêu cầu bật nhãn "nội dung đã chỉnh sửa/tổng hợp" nếu ảnh AI trông như thật.

```bat
python studio.py collect "Lizzie Borden" --query "Fall River 1892" "1890s police" --max 300   :: cào hàng loạt
python studio.py library                           :: thống kê thư viện
python studio.py library --search "1890s courtroom" --clip   :: tìm + xếp hạng bằng AI (cần sentence-transformers)
python studio.py library --gallery                 :: mở library/gallery.html xem toàn bộ ảnh
python studio.py media <slug> --candidates 12      :: mỗi cảnh lưu 12 ứng viên + tạo review.html
:: mở projects/<slug>/review.html -> click chọn ảnh theo thứ tự -> "Tải selection.json"
python studio.py media <slug> --apply selection.json
```
- Ảnh tải 1 lần, lưu ở `library/`, dùng lại cho mọi video. Ảnh trùng/gần trùng tự loại (giữ bản nét hơn).
- Ảnh "fair use / non-free" trên Wikipedia bị **bỏ qua** tự động. Credit + giấy phép ghi vào `output/credits.txt`.
- Chấm điểm ảnh: từ khoá + nguồn (ảnh bài Wikipedia vụ án được ưu tiên) + độ nét; cài `sentence-transformers` để AI CLIP
  "nhìn" ảnh và chọn ảnh khớp nội dung câu chuyện hơn.

## 3d. Kỹ năng dựng "kể chuyện bằng ảnh"

Mỗi cảnh được chia shot **cắt đúng cuối câu**, rồi tự chọn:

| Thành phần | Các kiểu |
|---|---|
| Chuyển động camera | `push_in` zoom vào điểm nhấn · `pull_out` lùi ra hé lộ · `pan_lr/rl` lia ngang · `tilt_down/up` lia dọc (đọc tài liệu, ảnh chân dung) · `punch` cận chi tiết · `snap_zoom` zoom nhanh khi lộ chi tiết · `float` ảnh in trôi trên bàn · `shake` rung máy nhẹ |
| Khung ảnh | ảnh phủ kín · ảnh dọc trên nền mờ · **ảnh in cũ / polaroid** trên mặt bàn gỗ · **mẩu báo cắt** ngả vàng mép giấy |
| Dùng 1 ảnh cho nhiều shot | toàn cảnh → cận chi tiết (crop quanh điểm nhấn: mặt người, chữ, vật thể) |
| Chuyển cảnh | hoà tan (fade) · **chớp trắng kiểu đèn flash** khi vào vật chứng / tờ báo · tối dần · cắt |
| Hiệu ứng | màu phim cũ / đen trắng, nhiễu hạt, vignette, **nhấp nháy máy chiếu**, ảnh ngả màu |
| Chữ | nhãn địa danh/năm **gõ từng chữ kiểu máy đánh chữ**, thẻ tên video & chương mờ vào/ra |

Chỉnh mọi thông số ở mục `edit:` trong `config.yaml` (độ zoom, tỉ lệ flash, tỉ lệ khung ảnh in, danh sách chuyển động được phép…).

### Bắt chước nhịp dựng của đối thủ
Tải 1 video mẫu về máy (video của bạn hoặc đối thủ, chỉ để **phân tích**, không dùng lại hình), rồi:
```bat
python studio.py analyze doi_thu.mp4 --minutes 10          :: đo nhịp cắt, % zoom vào/ra/lia, mức zoom, màu
python studio.py analyze doi_thu.mp4 --apply               :: ghi luôn số gợi ý vào config.yaml
```
Kết quả ở `analysis/<tên video>/`: `analysis.txt` + `keyframes.jpg` (lưới khung hình để xem bố cục, khung ảnh, kiểu chữ của họ).

## 3e. Phong cách "crime doc" tối (mặc định) + âm thanh

- `render.look: "dark"`: tông tối lạnh, khói trôi, thẻ tiêu đề chữ đứng **xám + đỏ** với bảng điều tra mờ bên phải,
  ảnh **ghim trên tường**, **bảng điều tra** nối dây đỏ, thumbnail chữ vàng + con dấu "CHƯA CÓ LỜI GIẢI".
- **Nhân vật xuất hiện ngay khi được nhắc tên**: Claude điền `entity` (tên, vai trò, từ khoá tìm ảnh) khi kịch bản
  giới thiệu người thật → màn hình hiện ảnh người đó + thẻ tên trượt vào. Tool **chỉ** nhận ảnh có tiêu đề chứa đúng
  họ tên người đó; không tìm thấy thì hiện bóng đen dấu hỏi (không bao giờ gắn nhầm mặt người khác).
- Tự chọn ảnh theo tên trong kịch bản: trường `"media": ["Wanted Poster", "Composite Sketch B"]` của mỗi cảnh
  (xem ví dụ `projects/d-b-cooper/kichban_vi.json`).
- **Hiệu ứng âm thanh tự động**: boom ở thẻ chương, whoosh khi thẻ tên trượt vào, màn trập máy ảnh khi chớp flash,
  tiếng gõ máy chữ khi hiện chữ. Muốn âm thanh xịn hơn: bỏ `hit.wav`, `whoosh.wav`, `flash.wav`, `type.wav` vào `assets/sfx/`.
- Chưa có nhạc trong `assets/music/` → tool tự tạo nhạc nền u tối (drone + nhịp tim). Nên thay bằng nhạc thật
  (YouTube Audio Library, Pixabay Music).
- Có card NVIDIA → `render.encoder: auto` tự dùng NVENC, mã hoá nhanh hơn nhiều.

## 3f. Cào data / render trên VPS Google Cloud

👉 **Hướng dẫn từng bước bằng giao diện web: `deploy/HUONG_DAN_GCP.md`**

Dùng được: VPS chạy **toàn bộ** quy trình (cào tư liệu, ảnh, video, ảnh AI, giọng, render ra MP4 hoàn chỉnh) rồi bạn
chỉ việc tải `final.mp4` + `thumbnail.jpg` + `youtube_upload.txt` về đăng. Lưu ý:
- **CapCut không chạy trên VPS Linux** → VPS làm: research, cào ảnh, tạo giọng, render MP4. CapCut làm trên PC Windows.
- IP Google Cloud là IP riêng của bạn → Wikimedia/LoC ít chặn hơn IP dùng chung. Nhưng **YouTube chặn mạnh IP
  cloud** (lấy transcript, yt-dlp hay bị lỗi) → phần lấy transcript nên làm trên máy nhà.
- Chi phí tham khảo: `e2-standard-2` (2 CPU, 8GB) ~25 USD/tháng nếu bật 24/7; máy render mạnh `c2d-highcpu-8`
  ~0,3 USD/giờ → bật khi render, **tắt ngay khi xong**. Spot VM rẻ hơn 60-70% nhưng có thể bị tắt ngang.

```bash
# trên máy bạn (đã cài Google Cloud CLI + gcloud auth login + project đã bật billing)
bash deploy/gcp_create_vm.sh
gcloud compute scp --zone asia-southeast1-b coldcase_studio.zip coldcase-vps:~/
gcloud compute ssh --zone asia-southeast1-b coldcase-vps
# trên VPS
unzip coldcase_studio.zip && cd coldcase_studio && bash deploy/vm_install_tool.sh
tmux new -s job
. .venv/bin/activate && python studio.py new "Tên vụ án" && python studio.py all <slug> --skip-capcut
python studio.py pack <slug>                       # -> <slug>_pack.zip (project + ảnh, không kèm file tạm)
```
Mang về PC Windows: `gcloud compute scp coldcase-vps:~/coldcase_studio/<slug>_pack.zip .` rồi
`python studio.py unpack <slug>_pack.zip` (tự sửa đường dẫn) → `python studio.py capcut <slug>`.

## 4. CapCut

`python studio.py capcut <slug>` tạo draft trực tiếp trong thư mục draft của CapCut (dùng thư viện
[pyCapCut](https://github.com/GuanYixuan/pyCapCut)). Mở CapCut → dự án mới xuất hiện → chỉnh → Export.

- **Phải chạy lệnh này trên chính máy Windows có CapCut** (draft lưu đường dẫn tuyệt đối tới file).
- Đã kiểm chứng với CapCut 8.x–9.x. Bản CapCut quá mới có thể mã hoá draft → nếu không mở được,
  dùng `output/final.mp4` (render bằng ffmpeg, không cần CapCut) rồi chỉ đưa vào CapCut để thêm hiệu ứng.
- Muốn thêm filter màu: `capcut.filter: "Gritty_Noir"` (một số filter/hiệu ứng là bản Pro).

## 5. Thời gian & chi phí ước tính (video 40 phút)

| Bước | Thời gian | Chi phí |
|---|---|---|
| Research | 1-3 phút | 0 |
| Kịch bản (Claude Opus 5.5) | 5-10 phút | ~1-3 USD tuỳ lượng tư liệu |
| Media (~350 shot) | 15-40 phút | 0 (Pexels/Pixabay/Pollinations miễn phí) |
| Giọng edge-tts / Kokoro | 5-20 phút | 0 |
| Render ffmpeg | 30-90 phút tuỳ CPU (shot đã render được cache) | 0 |

## 6. ⚠️ Đọc kỹ trước khi đăng – để kênh KHÔNG bị tắt kiếm tiền

1. **Đừng sao chép kênh đối thủ.** Học cách họ kể chuyện, nhịp, chọn vụ án – nhưng tên kênh, logo, kịch bản,
   hình thumbnail phải là của bạn. Sao chép dễ bị đánh gậy bản quyền / mạo danh.
2. **Chính sách "nội dung lặp lại / hàng loạt" của YouTube**: video slideshow ảnh stock + giọng AI + kịch bản AI
   không chỉnh sửa rất dễ bị từ chối YPP. Hãy **thêm giá trị riêng**: tự kiểm chứng dữ kiện, viết lại lời theo giọng
   của bạn, ưu tiên giọng clone riêng (viXTTS) hoặc tự thu âm, chỉnh dựng thêm trong CapCut.
3. **Bản quyền hình ảnh**: tool chỉ lấy nguồn có giấy phép (public domain / CC / Pexels / Pixabay) và tự ghi credit vào
   `output/credits.txt` + `youtube_upload.txt` → hãy dán credit vào mô tả. Ảnh CC-BY-SA bắt buộc ghi tên tác giả.
   **Không** tải video từ YouTube/TV/báo khác nếu không có quyền – đó là nguyên nhân số 1 bị gậy.
4. **Sự thật & con người thật**: luôn đọc lại `script.md` đối chiếu `research.json`. AI có thể sai. Với vụ chưa có
   kết luận, không gọi ai là hung thủ. Tôn trọng nạn nhân & gia đình (YouTube hạn chế quảng cáo với nội dung bạo lực
   chi tiết – kể bằng lời, tránh hình ảnh máu me thật).
5. Bật nhãn **"Nội dung được thay đổi/tổng hợp"** khi upload nếu dùng ảnh AI mô phỏng như thật.

## 7. Cấu trúc thư mục

```
coldcase_studio/
├─ studio.py            # lệnh chính
├─ config.yaml          # cấu hình
├─ core/
│  ├─ research.py       # thu thập tư liệu
│  ├─ scriptgen.py      # viết kịch bản (Claude API / manual / tự viết)
│  ├─ media.py          # tìm & tải ảnh/video + ảnh AI
│  ├─ tts.py            # giọng đọc
│  ├─ timeline.py       # timeline, phụ đề SRT, mốc chương
│  ├─ render.py         # dựng MP4 bằng ffmpeg
│  ├─ graphics.py       # thẻ tiêu đề/chương, nhãn chữ, thumbnail
│  └─ capcut.py         # xuất draft CapCut
├─ assets/music/        # nhạc nền của bạn
├─ voices/              # model giọng
└─ projects/<slug>/     # mỗi video 1 thư mục: research, script, media, audio, output
```

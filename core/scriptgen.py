"""Viết kịch bản ~40 phút từ tư liệu đã thu thập, dùng Claude API.

3 chế độ:
  1. auto   : gọi Claude API (cần ANTHROPIC_API_KEY) -> script.json
  2. manual : xuất prompt ra file để bạn dán vào claude.ai, rồi lưu kết quả JSON vào script.json
  3. text   : bạn tự viết kịch bản (file .txt) -> tool tự chia cảnh + tạo từ khoá tìm hình
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .util import Project, log, split_sentences

# --------- JSON schema cho structured outputs ---------

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "title_line1": {"type": "string"},
        "title_line2": {"type": "string"},
        "youtube_titles": {"type": "array", "items": {"type": "string"}},
        "thumbnail_text": {"type": "string"},
        "hook": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_facts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "summary", "key_facts"],
                "additionalProperties": False,
            },
        },
        "sources_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "title_line1", "title_line2", "youtube_titles", "thumbnail_text", "hook", "description", "tags", "chapters",
                 "sources_used"],
    "additionalProperties": False,
}

MOTION_ENUM = ["auto", "push_in", "pull_out", "pan_lr", "pan_rl", "tilt_down", "tilt_up", "punch", "snap_zoom",
               "float", "shake", "slam", "torch", "hold"]
SOUND_ENUM = ["none", "underwater", "rain", "wind", "office", "cafe", "city", "night", "footsteps", "door",
              "heartbeat", "riser", "whoosh", "silence"]
VISUAL_ENUM = ["archival_photo", "location", "document", "newspaper", "map", "atmosphere", "person", "evidence",
               "video_broll", "board", "quote", "character", "diagram", "species", "chart", "insert"]
MOOD_ENUM = ["auto", "neutral", "night", "rain", "warm", "phone", "tense", "sad", "hopeful", "dawn"]
MUSIC_ENUM = ["", "calm", "sad", "tense", "hopeful", "dark", "light", "silence"]
INSERT_ENUM = ["none", "phone", "clock", "chat", "bank"]
DIAGRAM_ENUM = ["none", "size_compare", "depth_chart", "cost_breakdown", "rent_vs_buy", "bar_chart", "timeline"]

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "purpose": {"type": "string"},
                    "on_screen_text": {"type": "string"},
                    "visual_type": {"type": "string", "enum": VISUAL_ENUM},
                    "action": {"type": "string"},
                    "camera": {"type": "string", "enum": MOTION_ENUM},
                    "sound": {"type": "string", "enum": SOUND_ENUM},
                    "entity": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "role": {"type": "string"},
                                       "search_query_en": {"type": "string"}},
                        "required": ["name", "role", "search_query_en"], "additionalProperties": False,
                    },
                    "character": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"}, "pose": {"type": "string"},
                            "position": {"type": "string", "enum": ["left", "center", "right"]},
                            "thought": {"type": "string"}, "outside": {"type": "string"}, "inside": {"type": "string"},
                            "keywords": {"type": "array", "items": {"type": "string"}},
                            "framing": {"type": "string", "enum": ["auto", "wide", "closeup"]},
                            "shadow": {"type": "string"},
                        },
                        "required": ["expression", "pose", "position", "thought", "outside", "inside", "keywords",
                                     "framing", "shadow"],
                        "additionalProperties": False,
                    },
                    "figures": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"label": {"type": "string"}, "value": {"type": "number"},
                                           "unit": {"type": "string"}, "formula": {"type": "string"},
                                           "source": {"type": "string"}, "verified": {"type": "boolean"}},
                            "required": ["label", "value", "unit", "formula", "source", "verified"],
                            "additionalProperties": False,
                        },
                    },
                    "diagram": {
                        "type": "object",
                        "properties": {"type": {"type": "string", "enum": DIAGRAM_ENUM}, "subject": {"type": "string"},
                                       "size_m": {"type": "number"}, "depth_m": {"type": "number"}},
                        "required": ["type", "subject", "size_m", "depth_m"], "additionalProperties": False,
                    },
                    "stat": {"type": "object",
                             "properties": {"value": {"type": "number"}, "label": {"type": "string"},
                                            "unit": {"type": "string"}},
                             "required": ["value", "label", "unit"], "additionalProperties": False},
                    "fx": {"type": "string", "enum": ["auto", "none", "shudder", "action", "impact", "reveal",
                                                      "glitch"]},
                    "emphasis": {"type": "array", "items": {"type": "string"}},
                    "mood": {"type": "string", "enum": MOOD_ENUM},
                    "music": {"type": "string", "enum": MUSIC_ENUM},
                    "hud": {"type": "string"},
                    "pause_after": {"type": "number"},
                    "insert": {
                        "type": "object",
                        "properties": {"type": {"type": "string", "enum": INSERT_ENUM}, "time": {"type": "string"},
                                       "date": {"type": "string"}, "app": {"type": "string"},
                                       "text": {"type": "string"},
                                       "messages": {"type": "array", "items": {
                                           "type": "object",
                                           "properties": {"from": {"type": "string", "enum": ["me", "them"]},
                                                          "text": {"type": "string"}},
                                           "required": ["from", "text"], "additionalProperties": False}}},
                        "required": ["type", "time", "date", "app", "text", "messages"], "additionalProperties": False,
                    },
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "search_queries_en": {"type": "array", "items": {"type": "string"}},
                    "image_prompt_en": {"type": "string"},
                },
                "required": ["narration", "purpose", "on_screen_text", "visual_type", "action", "camera", "sound",
                             "entity", "character", "figures", "diagram", "stat", "fx", "emphasis", "mood", "music", "hud", "pause_after",
                             "insert", "sources", "search_queries_en", "image_prompt_en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}

STORYBOARD_RULES = """STORYBOARD - mỗi scene điền đủ:
- purpose: mục đích cảnh (vd "hook", "giới thiệu nhân vật", "giải thích cơ chế", "so sánh", "kết luận").
- action: nhân vật/vật thể làm gì trong khung hình. camera: chuyển động camera phục vụ lời kể
  (push_in nhấn mạnh, pull_out hé lộ quy mô, pan lia, hold giữ yên để người xem quan sát, "auto" để tool chọn).
- sound: âm nền/hiệu ứng của cảnh (underwater, rain, footsteps, door, heartbeat, riser, silence...), "none" nếu không.
- sources: nguồn (tiêu đề/URL trong tư liệu) cho dữ kiện trong cảnh; [] nếu cảnh không nêu dữ kiện.
- character: chỉ khi visual_type = "character" (nhân vật linh vật 2D): expression (neutral, happy, smile, worried, sad,
  surprised, thinking, smug, angry, nervous, scared, tired, crying, anxious, panic, empty, determined, relieved,
  smirk), pose (stand, wave, think, point, shrug, hold, cheer, sit, phone, hug, cover, slump),
  position, thought (bong bóng suy nghĩ ngắn, "" nếu không), keywords (1-3 từ khoá hiện đúng lúc, ngắn),
  outside/inside (biểu cảm cho màn so sánh "bên ngoài vs bên trong", "" nếu không dùng),
  framing (auto | wide toàn thân | closeup cận mặt cho khoảnh khắc cảm xúc mạnh),
  shadow: câu "giọng nói trong đầu" / cám dỗ do BÓNG ĐEN phát sáng nói (chữ thường, ngắn, vd "chỉ một lần nữa thôi"),
  "" nếu không. Cảnh không dùng nhân vật: mọi trường character để "" và keywords [].
- CẢM XÚC (rất quan trọng, video phải có cảm xúc chứ không chỉ đọc thông tin):
  mood: ánh sáng cảnh - night (đêm), rain (mưa, buồn), warm (đèn vàng ấm áp/cám dỗ), phone (tối, chỉ ánh điện thoại
  hắt lên mặt), tense (căng thẳng, ánh đỏ), sad (lạnh, nhạt màu), hopeful (nắng, hi vọng), dawn (bình minh), neutral.
  music: đổi nhạc khi cảm xúc đổi (calm, sad, tense, hopeful, dark, light, silence = tắt nhạc trước câu chốt); "" = giữ.
  hud: bộ đếm góc màn hình theo dõi 1 con số xuyên suốt câu chuyện (vd "SỐ DƯ $2.400", "NGÀY THỨ 68"); đổi số khi
  câu chuyện đổi -> tool tự chạy số; "" = giữ nguyên; "none" = ẩn.
  fx: nhấn nhá hình + tiếng cho cả cảnh - shudder (cảnh man rợ/ghê rợn: rùng mình, chớp đỏ, nhạc kinh dị),
  action (hành động: truy đuổi, nổ súng, nhảy dù... -> nhạc trống dồn dập, giật camera), impact (chấn động),
  reveal (tiết lộ bất ngờ), glitch (bí ẩn, ký ức chập chờn), none, auto (tool tự đoán theo lời đọc).
  emphasis: 1-2 cụm từ NGUYÊN VĂN trong narration cần nhấn (con số gây sốc, tên hung thủ, chi tiết đắt giá) -> đúng
  lúc đọc tới: camera giật vào, "boom", chữ đập ra màn hình. Không lạm dụng: tối đa 1 cảnh nhấn / 3-4 cảnh.
  pause_after: giây im lặng sau câu chốt để người xem thấm (0 bình thường, 0.8-1.5 sau câu đắt giá).
  stat: con số gây ấn tượng của cảnh (value là SỐ, label ngắn vd "NGƯỜI ĐƯỢC CỨU", unit vd "m", "%"); value 0 nếu không.
  insert: màn hình chèn khi lời kể nhắc tới - phone (giờ + thông báo: time, date, app, text), clock (đồng hồ báo
  thức: time, text), chat (tin nhắn: messages), bank (số dư: app, text); type "none" nếu không.
- figures: mọi con số xuất hiện trong cảnh (label, value là SỐ, unit, formula = phép tính bằng các số khác nếu là số
  tính ra, vd "600000*0.2"; source; verified=true chỉ khi số có trong tư liệu). Không có số thì [].
- diagram: chỉ khi visual_type = "diagram"/"chart": type (size_compare, depth_chart, cost_breakdown, rent_vs_buy,
  bar_chart, timeline), subject, size_m (chiều dài sinh vật, m), depth_m (độ sâu, m); không dùng thì type "none", số 0.
- image_prompt_en: mô tả hình bằng tiếng Anh. Với cảnh "character": CHỈ mô tả NỀN/BỐI CẢNH (không có người, không
  nhân vật) vì nhân vật được tool vẽ riêng. Với "species": tên loài chính xác để tìm ảnh thật."""

LANG_NAME = {"vi": "tiếng Việt", "en": "English"}

SYSTEM = """Bạn là biên kịch chính của một kênh YouTube phim tài liệu về các vụ án có thật, thảm án và tin tức thời xưa.
Nguyên tắc bắt buộc:
- Chỉ dùng dữ kiện có trong TƯ LIỆU được cung cấp. Không bịa tên, ngày, con số. Khi tư liệu mâu thuẫn, nói rõ "theo báo X..." .
- Phân biệt rõ sự thật đã được xác nhận và giả thuyết/tin đồn.
- Không buộc tội người chưa bị toà kết án; với vụ chưa có lời giải dùng "nghi phạm", "người bị tình nghi".
- Tôn trọng nạn nhân và gia đình: không mô tả chi tiết bạo lực ghê rợn, không câu view bằng máu me.
- Nguồn có origin="REFERENCE" là transcript video của kênh khác. CHỈ dùng nó để biết vụ việc gồm những sự kiện nào
  và để đối chiếu. TUYỆT ĐỐI không chép hay diễn đạt lại sát câu chữ, không bám theo thứ tự đoạn/ví von/câu mở đầu
  của nó. Viết lời dẫn hoàn toàn mới, góc nhìn riêng, ưu tiên dữ kiện từ các nguồn gốc khác (báo, Wikipedia, hồ sơ).
- Lời dẫn viết để ĐỌC THÀNH TIẾNG: câu ngắn-vừa, nhịp chậm, giàu hình ảnh, không dùng ký hiệu, không gạch đầu dòng,
  viết số và năm bằng chữ số bình thường, không viết tắt khó đọc.
"""


def _corpus(research: dict, max_chars: int = 400_000) -> str:
    parts = []
    for i, s in enumerate(research.get("sources", []), 1):
        parts.append(f"<source id=\"{i}\" origin=\"{s['source']}\" title=\"{s['title']}\" date=\"{s.get('date', '')}\" "
                     f"url=\"{s.get('url', '')}\">\n{s['text']}\n</source>")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        log(f"  ! Tư liệu dài {len(text):,} ký tự, chỉ dùng {max_chars:,} ký tự đầu (bớt nguồn nếu cần).")
        text = text[:max_chars]
    return text


EMOTION_RULES = """
KỂ CHUYỆN CÓ CẢM XÚC (video phải khiến người xem CẢM THẤY, không chỉ biết thêm thông tin):
- Câu mở ngắn, cụ thể, gợi tò mò (vd "Mọi chuyện bắt đầu với 10 đô."). Không chào hỏi, không giới thiệu kênh.
- Đi theo MỘT con người cụ thể (tên, tuổi, hoàn cảnh, điều họ muốn, điều họ sợ) để người xem lo cho họ.
- Chi tiết cụ thể làm câu chuyện thật: giờ giấc (23:48), số tiền, đồ vật, thời tiết, âm thanh.
- Câu ngắn, nhịp như phim. Mỗi cảnh 1 ý. Có nhịp lên xuống: bình yên -> biến cố -> giằng xé -> hậu quả
  -> khoảnh khắc nhận ra -> thay đổi / dư âm.
- Cho thấy bằng hành động và chi tiết thay vì kể lể ("anh úp điện thoại xuống, rồi lại lật lên" thay vì "anh nghiện").
- Trước câu chốt quan trọng: music "silence" hoặc pause_after 1-1.5 giây để câu đó "rơi" xuống.
- Đổi mood/music theo cảm xúc từng chương, đừng giữ một màu suốt video.
- Cảnh man rợ/ghê rợn -> fx "shudder"; cảnh hành động (truy đuổi, đột kích, nhảy, nổ súng) -> fx "action";
  câu tiết lộ -> fx "reveal". Mỗi 3-4 cảnh có 1 cụm emphasis (con số sốc, tên, chi tiết đắt giá) để video có nhấn nhá.
- Kết: không giảng đạo; để câu chuyện tự dẫn tới ý nghĩa, kết bằng hi vọng hoặc một câu hỏi chạm tới người xem."""

EMOTION_2D = """
VỚI NHÂN VẬT 2D:
- Biểu cảm đổi theo từng cảnh (tired, anxious, crying, smirk, empty, relieved...) và tư thế phù hợp (phone khi cầm
  điện thoại, hug khi lo âu, cover khi khóc/xấu hổ, slump khi kiệt sức).
- framing "closeup" cho khoảnh khắc cảm xúc mạnh (nhận ra sự thật, bật khóc, cám dỗ).
- character.shadow: "giọng nói trong đầu" (cám dỗ, tự biện minh, nỗi sợ) do một bóng đen phát sáng nói - chữ thường,
  ngắn, như lời thì thầm. Dùng ở các khoảnh khắc giằng xé, không lạm dụng.
- insert phone/clock/chat/bank khi lời kể nhắc tới tin nhắn, giờ khuya, thông báo, số dư.
- hud: nếu câu chuyện xoay quanh 1 con số (tiền, số ngày, cân nặng...), đặt hud ở cảnh đầu và cập nhật khi số đổi."""


def system_prompt(cfg: dict) -> str:
    """Lời dặn biên kịch: preset theo ngách có thể thay (script.system) + quy tắc kể chuyện có cảm xúc."""
    base = (cfg.get("script", {}).get("system") or SYSTEM).strip()
    if cfg.get("script", {}).get("emotion", True):
        base += "\n" + EMOTION_RULES
        if "character" in (cfg.get("script", {}).get("visual_types") or []):
            base += "\n" + EMOTION_2D
    return base + "\n"


class ClaudeWriter:
    def __init__(self, cfg: dict):
        import anthropic

        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        sc = cfg.get("script", {})
        self.model = sc.get("model", "claude-opus-5-5")
        self.effort = sc.get("effort", "high")

    def ask_json(self, system: str, user: str, schema: dict) -> dict:
        kwargs = dict(
            model=self.model,
            max_tokens=48000,
            system=system,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user}],
        )
        # fallbacks: nếu model từ chối (refusal) vì nội dung án mạng, API tự chạy lại trên model dự phòng
        with self.client.beta.messages.stream(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise RuntimeError("Claude từ chối yêu cầu này (refusal). Hãy chỉnh lại chủ đề/tư liệu.")
        if msg.stop_reason == "max_tokens":
            raise RuntimeError("Kết quả bị cắt do max_tokens - giảm số từ mỗi chương hoặc tăng số chương.")
        text = next(b.text for b in msg.content if b.type == "text")
        return json.loads(text)


def allowed_visuals(cfg: dict) -> str:
    v = cfg.get("script", {}).get("visual_types")
    return f"- visual_type CHỈ dùng các loại: {', '.join(v)}." if v else ""


def project_context(cfg: dict) -> str:
    """Thông tin đầu vào của video (đối tượng xem, quốc gia, tiền tệ, thời điểm dữ liệu, loại truyện...)."""
    ctx = cfg.get("project", {}) or {}
    lines = [f"- {k}: {v}" for k, v in ctx.items() if v not in (None, "", [])]
    return ("THÔNG TIN VIDEO (bắt buộc tuân theo):\n" + "\n".join(lines)) if lines else ""


def build_outline_prompt(research: dict, cfg: dict) -> str:
    ch = cfg["channel"]
    sc = cfg["script"]
    lang = LANG_NAME.get(ch["language"], ch["language"])
    return f"""<tu_lieu>
{_corpus(research)}
</tu_lieu>

{project_context(cfg)}
Chủ đề video: {research['topic']}
Kênh: {ch['name']}. Ngôn ngữ lời dẫn: {lang}. Thời lượng mục tiêu: {ch['target_minutes']} phút.
Phong cách: {sc['style']}

Hãy lập DÀN Ý cho video gồm đúng {sc['chapters']} chương, kể theo trình tự lôi cuốn
(bối cảnh thời đại -> nhân vật -> sự việc -> điều tra -> bước ngoặt -> kết cục/bí ẩn còn lại -> di sản).
- hook: đoạn mở đầu 60-90 từ, gây tò mò mạnh, viết bằng {lang}.
- youtube_titles: 5 tiêu đề YouTube hấp dẫn nhưng trung thực ({lang}).
- thumbnail_text: 2-5 chữ in lên thumbnail.
- title_line1 / title_line2: tiêu đề 2 dòng cho thẻ mở đầu, dòng 1 ngắn màu xám (vd "VỤ KHÔNG TẶC"),
  dòng 2 là tên vụ án/nhân vật chính màu đỏ (vd "D. B. COOPER"), viết HOA, mỗi dòng tối đa ~22 ký tự.
- description: mô tả YouTube 150-250 từ ({lang}).
- tags: 15 tag.
- key_facts: các dữ kiện cụ thể (tên, ngày, địa điểm, con số) lấy từ tư liệu cho từng chương.
- sources_used: tiêu đề + url các nguồn đã dùng.
"""


def build_chapter_prompt(research: dict, outline: dict, idx: int, cfg: dict, prev_tail: str) -> str:
    ch = cfg["channel"]
    sc = cfg["script"]
    lang = LANG_NAME.get(ch["language"], ch["language"])
    total_words = ch["target_minutes"] * ch["words_per_minute"]
    words = int((total_words - 80) / sc["chapters"])
    chap = outline["chapters"][idx]
    shot = cfg["media"]["shot_seconds"]
    outline_txt = "\n".join(f"{i + 1}. {c['title']}: {c['summary']}" for i, c in enumerate(outline["chapters"]))
    return f"""<tu_lieu>
{_corpus(research)}
</tu_lieu>

<dan_y>
Tiêu đề: {outline['title']}
Hook: {outline['hook']}
{outline_txt}
</dan_y>

Viết lời dẫn cho CHƯƠNG {idx + 1}: "{chap['title']}"
Tóm tắt: {chap['summary']}
Dữ kiện cần có: {'; '.join(chap['key_facts'])}
Đoạn cuối chương trước (để nối mạch): "{prev_tail[-600:]}"

Yêu cầu:
- Tổng độ dài lời dẫn khoảng {words} từ bằng {lang}. Phong cách: {sc['style']}
- Chia thành các "scene", mỗi scene 40-80 từ (~{shot * 3}-{shot * 5} giây đọc), một ý/một hình ảnh chủ đạo.
- {"Scene đầu tiên của chương 1 chính là hook." if idx == 0 else "Không chào hỏi lại khán giả."}
- {"Kết chương bằng một câu treo (cliffhanger) dẫn sang chương sau." if idx < sc['chapters'] - 1 else "Kết thúc video: tổng kết, câu hỏi còn bỏ ngỏ, mời khán giả bình luận và đăng ký kênh " + ch['name'] + "."}
- entity: khi một NHÂN VẬT THẬT được nhắc tới lần đầu (nạn nhân, nghi phạm, điều tra viên, nhân chứng), điền
  name (VIẾT HOA, tên thật), role (vai trò ngắn gọn bằng ngôn ngữ lời dẫn, vd "Nghi phạm", "Tiếp viên hàng không"),
  search_query_en (tên để tìm ảnh, vd "Richard McCoy hijacker"). Màn hình sẽ hiện ảnh + thẻ tên người đó ngay lúc ấy.
  Scene không giới thiệu nhân vật mới: name, role, search_query_en đều là "".
- visual_type "quote": khi lời dẫn trích NGUYÊN VĂN một câu nói/ghi chú có thật (nhân chứng, nghi phạm, lá thư),
  đặt câu đó vào on_screen_text (ngắn, <= 25 từ) -> hiện thẻ trích dẫn gõ từng chữ VÀ được đọc bằng giọng riêng của
  nhân vật ngay sau lời dẫn. Vì vậy narration chỉ dẫn vào (vd "Hắn nghiêng người, thì thầm:") và KHÔNG lặp lại câu
  trích dẫn. Điền entity.name là người nói câu đó. Dùng 2-5 lần/video.
- visual_type "board": cảnh tổng kết/đặt câu hỏi -> bảng điều tra ghim nhiều ảnh nối dây đỏ (dùng 2-4 lần/video).
- on_screen_text: chữ hiện trên màn hình nếu cần (vd "Boston, 1962" hoặc tên nhân vật), để "" nếu không cần.
- search_queries_en: 3 cụm từ TIẾNG ANH ngắn (2-5 từ) để tìm ảnh/video tư liệu phù hợp trên Wikimedia/Pexels/LoC
  (vd "1960s police car", "old newspaper headline murder", "foggy forest night"). Cụm đầu cụ thể (tên người/địa danh nếu có ảnh lịch sử), các cụm sau chung chung hơn.
- image_prompt_en: prompt tiếng Anh tạo ảnh AI minh hoạ không khí scene (không vẽ mặt người thật cụ thể, không máu me).
{allowed_visuals(cfg)}
{STORYBOARD_RULES}
{project_context(cfg)}
"""


def write_script_auto(project: Project, cfg: dict) -> dict:
    research = project.read_json("research.json")
    if not research:
        raise SystemExit("Chưa có research.json - chạy lệnh research trước.")
    w = ClaudeWriter(cfg)
    outline = project.read_json("outline.json")
    if not outline:
        log(f"Claude ({w.model}) đang lập dàn ý...")
        outline = w.ask_json(system_prompt(cfg), build_outline_prompt(research, cfg), OUTLINE_SCHEMA)
        project.write_json("outline.json", outline)
    log(f"Dàn ý: {outline['title']} - {len(outline['chapters'])} chương")

    chapters = project.read_json("chapters_partial.json", [])
    prev_tail = chapters[-1]["scenes"][-1]["narration"] if chapters else ""
    for i in range(len(chapters), len(outline["chapters"])):
        log(f"Viết chương {i + 1}/{len(outline['chapters'])}: {outline['chapters'][i]['title']}")
        res = w.ask_json(system_prompt(cfg), build_chapter_prompt(research, outline, i, cfg, prev_tail), SCENE_SCHEMA)
        chapters.append({"title": outline["chapters"][i]["title"], "scenes": res["scenes"]})
        project.write_json("chapters_partial.json", chapters)  # lưu dần, lỗi giữa chừng chạy lại sẽ tiếp tục
        prev_tail = res["scenes"][-1]["narration"]

    script = finalize_script(outline, chapters)
    save_script(project, script)
    return script


def finalize_script(outline: dict, chapters: list[dict]) -> dict:
    n = 0
    for c in chapters:
        for s in c["scenes"]:
            n += 1
            s["id"] = f"s{n:03d}"
            ent = s.get("entity")
            if isinstance(ent, dict) and not (ent.get("name") or "").strip():
                s.pop("entity")
    meta = {k: v for k, v in outline.items() if k != "chapters"}
    return {**meta, "chapters": chapters}


SCENE_DEFAULTS = {"purpose": "", "action": "", "camera": "auto", "sound": "none", "sources": [], "figures": [],
                  "diagram": {"type": "none", "subject": "", "size_m": 0, "depth_m": 0},
                  "character": {"expression": "", "pose": "", "position": "left", "thought": "", "outside": "",
                                "inside": "", "keywords": [], "framing": "auto", "shadow": ""},
                  "mood": "auto", "music": "", "hud": "", "pause_after": 0,
                  "stat": {"value": 0, "label": "", "unit": ""}, "fx": "auto", "emphasis": [],
                  "insert": {"type": "none", "time": "", "date": "", "app": "", "text": "", "messages": []}}


def export_storyboard(project: Project, script: dict) -> None:
    """storyboard.md (đọc) + storyboard.csv (sửa trong Excel/Google Sheets)."""
    import csv

    tl = project.read_json("timeline.json", {}) or {}
    times = {it.get("id"): (it["start"], it["duration"]) for it in tl.get("items", []) if it.get("id")}

    def ts(t):
        return f"{int(t // 60)}:{int(t % 60):02d}"

    rows, md = [], [f"# Storyboard – {script['title']}\n"]
    for ci, c in enumerate(script["chapters"], 1):
        md.append(f"\n## Chương {ci}: {c['title']}\n")
        for sc in c["scenes"]:
            ch = sc.get("character") or {}
            dg = sc.get("diagram") or {}
            figs = "; ".join(f"{f['label']}={f['value']}{f.get('unit', '')}" + (f" ({f['formula']})" if f.get("formula") else "")
                             + ("" if f.get("verified") else " ⚠CHƯA XÁC MINH") for f in sc.get("figures") or [])
            st, du = times.get(sc["id"], (None, None))
            row = {"id": sc["id"], "time": f"{ts(st)} ({du:.1f}s)" if st is not None else "", "chapter": c["title"],
                   "purpose": sc.get("purpose", ""), "narration": sc["narration"], "visual_type": sc.get("visual_type", ""),
                   "visual": sc.get("image_prompt_en", ""), "action": sc.get("action", ""), "camera": sc.get("camera", ""),
                   "on_screen_text": sc.get("on_screen_text", ""), "sound": sc.get("sound", ""),
                   "character": " / ".join(x for x in [ch.get("expression", ""), ch.get("pose", ""), ch.get("thought", "")] if x),
                   "keywords": ", ".join(ch.get("keywords") or []),
                   "diagram": dg.get("type", "") if dg.get("type") not in (None, "none") else "",
                   "figures": figs, "sources": " | ".join(sc.get("sources") or []),
                   "entity": (sc.get("entity") or {}).get("name", ""),
                   "emotion": " · ".join(x for x in [
                       f"ánh sáng {sc['mood']}" if sc.get("mood") not in (None, "", "auto") else "",
                       f"nhạc {sc['music']}" if sc.get("music") else "",
                       f"cận mặt" if ch.get("framing") == "closeup" else "",
                       f"bóng đen: «{ch['shadow']}»" if (ch.get("shadow") or "").strip() else "",
                       f"đếm: {sc['hud']}" if sc.get("hud") else "",
                       f"chèn {(sc.get('insert') or {}).get('type')}" if (sc.get("insert") or {}).get("type") not in
                       (None, "", "none") else "",
                       f"lặng {sc['pause_after']}s" if sc.get("pause_after") else ""] if x)}
            rows.append(row)
            md.append(f"**[{sc['id']}]** {row['time']} · *{row['purpose']}* · `{row['visual_type']}` · camera `{row['camera']}`"
                      f" · âm thanh `{row['sound']}`\n\n> {sc['narration']}\n")
            for k, lab in (("visual", "Hình"), ("action", "Hành động"), ("on_screen_text", "Chữ"), ("character", "Nhân vật"),
                           ("keywords", "Từ khoá"), ("emotion", "Cảm xúc"), ("diagram", "Sơ đồ"), ("figures", "Số liệu"), ("sources", "Nguồn")):
                if row[k]:
                    md.append(f"- {lab}: {row[k]}")
            md.append("")
    project.path("storyboard.md").write_text("\n".join(md), encoding="utf-8")
    with open(project.path("storyboard.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)


def save_script(project: Project, script: dict) -> None:
    import copy

    for c in script["chapters"]:
        for sc in c["scenes"]:
            for k, v in SCENE_DEFAULTS.items():
                if k not in sc:
                    sc[k] = copy.deepcopy(v)
    project.write_json("script.json", script)
    export_storyboard(project, script)
    words = 0
    md = [f"# {script['title']}\n"]
    for i, c in enumerate(script["chapters"], 1):
        md.append(f"\n## Chương {i}: {c['title']}\n")
        for s in c["scenes"]:
            words += len(s["narration"].split())
            md.append(f"**[{s['id']}]** {s['narration']}\n")
            md.append(f"> 🎞 {s['visual_type']} | {', '.join(s['search_queries_en'])}"
                      + (f" | chữ: {s['on_screen_text']}" if s.get("on_screen_text") else "") + "\n")
    project.path("script.md").write_text("\n".join(md), encoding="utf-8")
    log(f"✓ Kịch bản: {words:,} từ (~{words / 150:.0f} phút) -> script.json / script.md")


# --------- Chế độ manual (không có API key) ---------

MANUAL_SCENE_EXAMPLE = {
    "narration": "lời đọc của cảnh, 25-70 từ, viết số bằng chữ", "purpose": "hook", "on_screen_text": "",
    "visual_type": "archival_photo", "action": "", "camera": "auto", "sound": "none",
    "entity": {"name": "", "role": "", "search_query_en": ""},
    "character": {"expression": "", "pose": "", "position": "left", "thought": "", "outside": "", "inside": "",
                  "keywords": [], "framing": "auto", "shadow": ""},
    "figures": [], "diagram": {"type": "none", "subject": "", "size_m": 0, "depth_m": 0},
    "stat": {"value": 0, "label": "", "unit": ""}, "fx": "auto", "emphasis": [], "mood": "auto", "music": "",
    "hud": "", "pause_after": 0,
    "insert": {"type": "none", "time": "", "date": "", "app": "", "text": "", "messages": []},
    "sources": [], "search_queries_en": ["english search words"], "image_prompt_en": "english image description"}


def manual_prompt_text(project: Project, cfg: dict) -> str:
    """Lời nhắc đầy đủ để dán vào claude.ai (không cần API key)."""
    research = project.read_json("research.json")
    if not research:
        raise SystemExit("Chưa có research.json - chạy bước Tư liệu trước.")
    ch = cfg["channel"]
    total_words = ch["target_minutes"] * ch["words_per_minute"]
    example = json.dumps(MANUAL_SCENE_EXAMPLE, ensure_ascii=False)
    return system_prompt(cfg) + "\n" + build_outline_prompt(research, cfg) + f"""

{allowed_visuals(cfg)}
{STORYBOARD_RULES}

SAU ĐÓ viết luôn TOÀN BỘ kịch bản (~{total_words} từ lời đọc, {cfg["script"].get("chapters", 6)} chương) và trả về
MỘT khối JSON duy nhất (không giải thích gì thêm) theo cấu trúc:
{{"title": "...", "title_line1": "dòng nhỏ", "title_line2": "TIÊU ĐỀ LỚN", "youtube_titles": ["...", "..."],
  "thumbnail_text": "...", "hook": "...", "description": "...", "tags": ["..."], "sources_used": ["..."],
  "chapters": [{{"title": "...", "scenes": [ <scene>, <scene>, ... ]}}]}}
Mỗi <scene> có đủ các trường như ví dụ:
{example}
Nếu quá dài cho một lần trả lời: trả JSON chương 1 trước (cùng cấu trúc, chỉ chứa chương 1), tôi sẽ nói "tiếp"
để bạn trả các chương sau dạng {{"title": "...", "scenes": [...]}}; tôi tự ghép lại.
"""


def write_manual_prompt(project: Project, cfg: dict) -> Path:
    prompt = manual_prompt_text(project, cfg)
    p = project.path("prompt_for_claude.txt")
    p.write_text(prompt, encoding="utf-8")
    log(f"✓ Đã xuất prompt -> {p}\n  Dán vào claude.ai, lưu JSON trả về thành {project.path('script.json')}"
        f"\n  rồi chạy: python studio.py script {project.slug} --import-json <file.json>")
    return p


def parse_pasted_json(text: str) -> dict:
    """Ghép JSON dán từ claude.ai: chấp nhận ```json``` , nhiều khối (chương 1, rồi các chương sau)."""
    text = re.sub(r"```(?:json)?", "", text)
    dec = json.JSONDecoder()
    objs, i = [], 0
    while True:
        k = text.find("{", i)
        if k < 0:
            break
        try:
            o, end = dec.raw_decode(text, k)
        except ValueError:
            i = k + 1
            continue
        objs.append(o)
        i = end
    base = None
    for o in objs:
        if not isinstance(o, dict):
            continue
        if "chapters" in o:
            if base is None:
                base = o
            else:
                base["chapters"] += o["chapters"]
        elif "scenes" in o and base is not None:
            base["chapters"].append(o)
    if not base or not base.get("chapters"):
        raise ValueError("Không thấy JSON kịch bản (cần có \"chapters\") trong nội dung đã dán")
    base.setdefault("title", base["chapters"][0].get("title", "Video"))
    return base


def import_json(project: Project, path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    script = finalize_script({k: v for k, v in data.items() if k != "chapters"} | {"chapters": []}, data["chapters"])
    for k in ("youtube_titles", "tags", "sources_used"):
        script.setdefault(k, [])
    for k in ("thumbnail_text", "hook", "description"):
        script.setdefault(k, "")
    for c in script["chapters"]:
        for s in c["scenes"]:
            s.setdefault("on_screen_text", "")
            s.setdefault("visual_type", "archival_photo")
            s.setdefault("search_queries_en", [])
            s.setdefault("image_prompt_en", "")
    save_script(project, script)
    return script


# --------- Chế độ text (bạn tự viết kịch bản) ---------

STOP = set("""the a an of and or to in on at for with from by is was were be been this that these those it its as
into over after before than then there their they them his her he she we you i our your not no but so if when
which who whom what where why how""".split())


def script_from_text(project: Project, text_path: str, title: str, cfg: dict) -> dict:
    """Kịch bản tự viết: dòng bắt đầu bằng '#' là tên chương; đoạn văn được gộp thành scene ~60 từ.
    Có thể ghi gợi ý hình ở cuối đoạn trong ngoặc vuông: [img: 1920s chicago street, police]"""
    raw = Path(text_path).read_text(encoding="utf-8")
    chapters: list[dict] = []
    cur = {"title": "Mở đầu", "scenes": []}
    buf = ""

    def flush(hint=""):
        nonlocal buf
        if buf.strip():
            cur["scenes"].append(_scene_from_text(buf.strip(), hint))
        buf = ""

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            flush()
            if cur["scenes"]:
                chapters.append(cur)
            cur = {"title": line.lstrip("#").strip(), "scenes": []}
            continue
        hint = ""
        m = re.search(r"\[img:\s*(.+?)\]\s*$", line)
        if m:
            hint, line = m.group(1), line[:m.start()].strip()
        for sent in split_sentences(line):
            buf += " " + sent
            if len(buf.split()) >= 60:
                flush(hint)
        if hint:
            flush(hint)
    flush()
    if cur["scenes"]:
        chapters.append(cur)
    script = finalize_script({"title": title, "youtube_titles": [title], "thumbnail_text": title[:30], "hook": "",
                              "description": "", "tags": [], "sources_used": []}, chapters)
    save_script(project, script)
    log("  Gợi ý: từ khoá tìm hình được tạo tự động (thô). Nên sửa search_queries_en trong script.json"
        " hoặc thêm [img: ...] vào cuối đoạn văn.")
    return script


def _scene_from_text(text: str, hint: str) -> dict:
    if hint:
        queries = [q.strip() for q in hint.split(",") if q.strip()][:3] or [hint]
    else:
        caps = re.findall(r"\b[A-Z][a-zA-Z]{3,}(?:\s+[A-Z][a-zA-Z]{3,})*", text)
        nums = re.findall(r"\b1[6-9]\d\d\b|\b20[0-2]\d\b", text)
        queries = [" ".join(caps[:2]) if caps else "", (nums[0] + " archival photo") if nums else "",
                   "dark mysterious night"]
        queries = [q for q in queries if q] or ["old archival photograph"]
    return {"narration": text, "on_screen_text": "", "visual_type": "archival_photo",
            "search_queries_en": queries, "image_prompt_en": (hint or queries[0]) + ", historical scene"}

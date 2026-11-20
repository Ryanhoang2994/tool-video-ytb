"""Dựng timeline chung (dùng cho cả render ffmpeg và xuất draft CapCut) + phụ đề SRT + mốc chương YouTube."""
from __future__ import annotations

import re
from pathlib import Path

from . import graphics
from .motion import plan_scene
from .util import Project, log, split_sentences

TITLE_CARD_SEC = 5.0
CHAPTER_CARD_SEC = 3.5


def _chunks(text: str, max_words: int = 12) -> list[str]:
    out = []
    for sent in split_sentences(text):
        words = sent.split()
        if len(words) <= max_words:
            out.append(sent)
            continue
        # chia câu dài theo dấu phẩy rồi theo số từ
        parts = re.split(r"(?<=[,;:])\s+", sent)
        buf: list[str] = []
        for p in parts:
            pw = p.split()
            if buf and len(buf) + len(pw) > max_words:
                out.append(" ".join(buf))
                buf = []
            while len(pw) > max_words:
                out.append(" ".join(pw[:max_words]))
                pw = pw[max_words:]
            buf += pw
        if buf:
            out.append(" ".join(buf))
    return out


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _yt(t: float) -> str:
    t = int(t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_timeline(project: Project, cfg: dict) -> dict:
    script = project.read_json("script.json")
    timing = project.read_json("timing.json")
    plan = project.read_json("media_plan.json", {})
    if not script or not timing:
        raise SystemExit("Cần script.json và timing.json (chạy lệnh voice trước).")
    rc, ch = cfg["render"], cfg["channel"]
    W, H = rc["width"], rc["height"]
    pause = cfg["voice"].get("pause_after_scene", 0.5)
    cards = project.path("cards")

    items: list[dict] = []   # các block nối tiếp nhau: card hoặc scene
    t = 0.0

    def add_card(img: Path, dur: float, kind: str, label: str):
        nonlocal t
        items.append({"type": kind, "start": t, "duration": dur, "label": label,
                      "shots": [{"kind": "image", "file": str(img), "start": t, "duration": dur, "zoom": 0.05,
                                 "motion": "push_in", "frame": "full", "transition": "cut", "focus": [0.5, 0.5]}]})
        t += dur

    mstate: dict = {}
    dark = rc.get("look") == "dark"
    vi = ch["language"] == "vi"

    def chap_media(ci: int) -> list[str]:
        out = []
        for sc in script["chapters"][ci]["scenes"]:
            out += [m["file"] for m in plan.get(sc["id"], []) if m["kind"] == "image" and Path(m["file"]).exists()]
        return out

    card_style = rc.get("card_style", "")

    def chapter_img(ci: int, chap: dict) -> Path:
        out = cards / f"chap{ci + 1:02d}.jpg"
        if rc.get("look") == "collage":
            from . import collage

            imgs = chap_media(ci)
            return collage.card(("CHƯƠNG " if vi else "CHAPTER ") + str(ci + 1), chap["title"],
                                out.with_name(f"collage_{out.name}"), Path(imgs[0]) if imgs else None, W, H, seed=ci)
        if card_style.startswith("bold"):
            imgs = chap_media(ci)
            return graphics.bold_card(("CHƯƠNG " if vi else "CHAPTER ") + str(ci + 1), chap["title"], out,
                                      Path(imgs[0]) if imgs else None, W, H, dark=card_style == "bold_dark", seed=ci)
        if dark:
            imgs = chap_media(ci)
            return graphics.crime_title_card(("CHƯƠNG " if vi else "CHAPTER ") + str(ci + 1), chap["title"], out,
                                             Path(imgs[0]) if imgs else None, W, H, seed=ci + 2)
        return graphics.chapter_card(ci + 1, chap["title"], out, W, H, font, ch["language"])

    def title_img() -> Path:
        out = cards / "title.jpg"
        if rc.get("look") == "collage":
            from . import collage

            imgs = chap_media(0)
            return collage.card(script.get("title_line1") or ch["name"], script.get("title_line2") or script["title"],
                                cards / "collage_title.jpg", Path(imgs[0]) if imgs else None, W, H, seed=99)
        if card_style.startswith("bold"):
            imgs = chap_media(0)
            return graphics.bold_card(script.get("title_line1") or "", script.get("title_line2") or script["title"],
                                      out, Path(imgs[0]) if imgs else None, W, H, dark=card_style == "bold_dark")
        if dark:
            allimgs = list(dict.fromkeys(f for i in range(len(script["chapters"])) for f in chap_media(i)))
            board = None
            if allimgs:
                board, _ = graphics.evidence_board(allimgs[:6], cards / "title_board.jpg", seed=7)
            l1 = script.get("title_line1") or ch["name"]
            l2 = script.get("title_line2") or script["title"]
            return graphics.crime_title_card(l1, l2, out, board, W, H, small=ch["name"])
        return graphics.title_card(script["title"], ch["name"], out, W, H, font)
    chapter_starts: list[float] = []
    is_short = float(ch.get("target_minutes") or 10) <= 1.5  # Shorts/Reels: không thẻ tiêu đề, không đuôi dài
    font = rc.get("font", "")
    # overlay: tên chương / tiêu đề hiện đè lên cảnh trong khi lời kể vẫn chạy (không ngắt nhịp)
    # card: thẻ riêng (kiểu cũ, có khoảng lặng) | none: không hiện
    chap_style = rc.get("chapter_style") or ("overlay" if rc.get("chapter_cards", True) else "none")
    pending: dict | None = None
    from . import fx as fxmod

    for ci, chap in enumerate(script["chapters"]):
        for si, s in enumerate(chap["scenes"]):
            if ci > 0 and si == 0:
                chapter_starts.append(t)
                if chap_style == "card":
                    add_card(chapter_img(ci, chap), CHAPTER_CARD_SEC, "chapter", chap["title"])
                elif chap_style == "overlay" and not pending:
                    pending = {"kind": "chapter", "small": ("CHƯƠNG " if vi else "CHAPTER ") + str(ci + 1),
                               "big": chap["title"]}
            elif ci == 0 and si == 0:
                chapter_starts.append(0.0)
                st = (cfg.get("project") or {}).get("story_type")
                if st == "fiction":  # truyện hư cấu: thẻ cảnh báo trước khi vào truyện
                    add_card(graphics.bold_card("", "Truyện hư cấu - mọi nhân vật và sự kiện đều do tưởng tượng" if vi
                                                else "A work of fiction - all characters and events are imaginary",
                                                cards / "fiction.jpg", None, W, H, dark=True), 3.0, "chapter", "fiction")

            dur = timing[s["id"]]["duration"] + pause + float(s.get("pause_after") or 0)  # khoảng lặng sau câu chốt
            if s.get("entity"):
                ef = (plan.get(f"{s['id']}:entity") or [{}])[0].get("file")
                if not ef or not Path(ef).exists():
                    ef = str(graphics.silhouette(cards / "silhouette.jpg")) if not (cards / "silhouette.jpg").exists() \
                        else str(cards / "silhouette.jpg")
                s = {**s, "entity": {**s["entity"], "file": ef}}
            media = [m for m in plan.get(s["id"], []) if Path(m["file"]).exists()]
            layered = s.get("visual_type") in ("character", "diagram", "chart", "insert")
            if not media and mstate.get("board_imgs") and not layered:  # không có hình: dựng bảng điều tra từ ảnh đã xuất hiện
                media = [{"kind": "image", "file": f, "credit": ""} for f in mstate["board_imgs"][-5:]]
                s = {**s, "visual_type": "board"}
            if not media and not layered:  # không có hình: dùng nền tối có chữ
                img = cards / f"fallback_{s['id']}.jpg"
                if not img.exists():
                    graphics.chapter_card(0, s.get("on_screen_text") or chap["title"], img, W, H, font, ch["language"])
                media = [{"kind": "image", "file": str(img), "credit": ""}]
            if si == 0:
                mstate["chapter_open"] = True
            if ci == 0 and si == 0:
                mstate["hook"] = True
            if s.get("visual_type") == "quote" and "quote_bg" not in mstate:
                qb = cards / "quote_bg.jpg"
                if not qb.exists():
                    graphics.dark_wall(int(W * 1.5), int(H * 1.5), 21).save(qb, quality=92)
                mstate["quote_bg"] = str(qb)
            fxk = fxmod.detect(s, cfg)
            if fxk == "jumpscare":  # hù doạ dày quá sẽ nhờn: giữ khoảng cách tối thiểu, cú thừa đổi thành dồn căng thẳng
                gap = cfg.get("edit", {}).get("jumpscare_gap", 40)
                if t - mstate.get("last_scare", -1e9) < gap:
                    fxk = "dread"
                else:
                    mstate["last_scare"] = t
            pts = fxmod.anchors(s["narration"], project.path("audio", f"{s['id']}.wav"), timing[s["id"]]["duration"])
            acc = fxmod.accents(s, fxk, timing[s["id"]]["duration"], pts)
            if fxk == "action":
                mstate["pace_once"] = 0.6  # hành động: cắt nhanh hơn
            shots = plan_scene(s, media, t, dur, cfg, mstate)
            shake = fxmod.shake_amount(fxk)
            for sh in shots:  # camera giật vào đúng nhịp nhấn
                pf = [round((t + a - sh["start"]) * rc["fps"]) for a in acc
                      if sh["start"] <= t + a < sh["start"] + sh["duration"]]
                if pf and sh.get("kind") == "image":
                    sh["punches"], sh["shake"] = pf, shake
                    sh["punch_amp"] = fxmod.punch_amount(fxk)
            hud_prev = mstate.get("hud", "")
            if s.get("hud"):  # bộ đếm góc màn hình giữ nguyên tới khi cảnh sau đổi; "none" = ẩn
                mstate["hud"] = "" if s["hud"] == "none" else s["hud"]
            hud_now = mstate.get("hud", "")
            if s.get("music"):
                mstate["music"] = s["music"]
            items.append({"type": "scene", "id": s["id"], "chapter": ci, "start": t, "duration": dur,
                          "audio": str(project.path("audio", f"{s['id']}.wav")),
                          "audio_dur": timing[s["id"]]["duration"], "text": s["narration"],
                          "label": "" if s.get("visual_type") in ("quote", "character", "diagram", "chart", "insert")
                          else s.get("on_screen_text", ""),
                          "keywords": (s.get("character") or {}).get("keywords") or [],
                          "sound": s.get("sound", ""),
                          "mood": s.get("mood") or "",
                          "music": s.get("music") or fxmod.FX_MUSIC.get(fxk) or mstate.get("music", ""),
                          "fx": fxk, "accents": acc,
                          "apparition": fxmod.apparition_kind(s) if fxk == "jumpscare" else "",
                          "emph": fxmod.phrases(s, pts) if cfg.get("edit", {}).get("emphasis_text", True) else [],
                          "anchors": pts,
                          "overlay": pending,
                          "hud": hud_now, "hud_prev": hud_prev,
                          "insert": (s.get("insert") or {}).get("type", "") if s.get("insert") else "",
                          "shots": shots})
            t += dur
            pending = None

            if ci == 0 and si == 0:  # sau hook: tên video (+ chương 1 nếu chương 1 còn tiếp)
                if chap_style == "card" and not is_short:
                    add_card(title_img(), TITLE_CARD_SEC, "title", script["title"])
                    if len(chap["scenes"]) > 1:
                        chapter_starts[0] = t
                        add_card(chapter_img(0, chap), CHAPTER_CARD_SEC, "chapter", chap["title"])
                elif not is_short:  # tiêu đề hiện đè lên cảnh kế tiếp, lời kể không dừng (video ngắn: bỏ, vào thẳng chuyện)
                    pending = {"kind": "title", "small": script.get("title_line1") or ch["name"],
                               "big": script.get("title_line2") or script["title"]}
                    if len(chap["scenes"]) > 1:
                        chapter_starts[0] = t

    # tail cho nhạc fade (video ngắn: 1 giây để không dư đuôi)
    tl = {"width": W, "height": H, "fps": rc["fps"], "duration": t + (1.0 if is_short else 3.0), "items": items,
          "chapter_starts": chapter_starts}
    project.write_json("timeline.json", tl)
    _write_srt(project, tl)
    _write_youtube_meta(project, script, tl, ch.get("language", "vi"))
    log(f"✓ Timeline: {len(items)} block, {sum(len(i['shots']) for i in items)} shot, {tl['duration'] / 60:.1f} phút")
    return tl


def _wrap2(c: str, limit: int = 44) -> str:
    """Câu dài -> 2 dòng cân nhau (ngắt ở khoảng trắng gần giữa nhất)."""
    if len(c) <= limit:
        return c
    mid = len(c) // 2
    sp = [i for i, ch in enumerate(c) if ch == " "]
    if not sp:
        return c
    k = min(sp, key=lambda i: abs(i - mid))
    return c[:k] + "\n" + c[k + 1:]


def _write_srt(project: Project, tl: dict) -> Path:
    last_end = 0.0
    lines, n = [], 0
    for it in tl["items"]:
        if it["type"] != "scene":
            continue
        chunks = _chunks(it["text"])
        total = sum(len(c) for c in chunks) or 1
        pts = it.get("anchors")
        if pts:  # căn theo khoảng lặng thật của giọng đọc
            from .fx import _norm, at_time

            norm = _norm(it["text"])
            pos = 0
            spans = []
            for c in chunks:
                i0 = norm.find(_norm(c), pos)
                i0 = pos if i0 < 0 else i0
                i1 = i0 + len(c)
                pos = i1
                spans.append([it["start"] + at_time(pts, i0), it["start"] + at_time(pts, min(i1, len(norm))), c])
            for k, (t0, t1, c) in enumerate(spans):  # không chồng lấn: bắt đầu sau dòng trước, kết thúc trước dòng sau
                t0 = max(t0, last_end + 0.01)
                nxt = spans[k + 1][0] if k + 1 < len(spans) else it["start"] + it["duration"]
                t1 = min(max(t0 + 0.4, t1 - 0.05), nxt - 0.02)
                if t1 <= t0:
                    t1 = t0 + 0.2
                n += 1
                lines.append(f"{n}\n{_ts(t0)} --> {_ts(t1)}\n{_wrap2(c)}\n")
                last_end = t1
            continue
        t = it["start"]
        for c in chunks:
            d = it["audio_dur"] * len(c) / total
            n += 1
            lines.append(f"{n}\n{_ts(t)} --> {_ts(t + d - 0.05)}\n{_wrap2(c)}\n")
            t += d
            last_end = t - 0.05
    p = project.path("output", "subtitles.srt")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def cfg_lang(project: Project) -> str:
    from .util import load_config

    return load_config().get("channel", {}).get("language", "en")


def _write_youtube_meta(project: Project, script: dict, tl: dict, lang: str = "") -> None:
    lang = lang or cfg_lang(project)
    intro = "Intro" if lang == "en" else "Mở đầu"
    chap_lines = [f"0:00 {intro}"] if tl["chapter_starts"] and tl["chapter_starts"][0] > 0 else []
    for c, t0 in zip(script["chapters"], tl["chapter_starts"]):
        chap_lines.append(f"{_yt(t0)} {c['title']}")
    credits = project.path("output", "credits.txt")
    credit_txt = credits.read_text(encoding="utf-8") if credits.exists() else ""
    srcs = "\n".join(f"- {s}" for s in script.get("sources_used", []))
    txt = f"""TIÊU ĐỀ GỢI Ý:
{chr(10).join('- ' + t for t in script.get('youtube_titles', [script['title']]))}

MÔ TẢ:
{script.get('description', '')}

CHƯƠNG:
{chr(10).join(chap_lines)}

NGUỒN TƯ LIỆU:
{srcs}

HÌNH ẢNH / VIDEO (credit):
{credit_txt}

TAGS:
{', '.join(script.get('tags', []))}
"""
    project.path("output", "youtube_upload.txt").write_text(txt, encoding="utf-8")

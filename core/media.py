"""Gán hình ảnh / video cho từng cảnh của kịch bản.

Ảnh được cào từ nhiều nguồn (xem core/sources.py) vào THƯ VIỆN chung (core/library.py), chấm điểm độ liên quan,
loại trùng, rồi chọn cho từng scene. Có trang review.html để bạn xem ứng viên & chọn tay.
Thiếu ảnh -> video B-roll -> ảnh AI -> thẻ chữ.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
import random
import re
import zlib
from pathlib import Path

from . import sources
from .library import Library, era_ok_strict, gallery, keyword_score
from .util import Project, download, http_json, log, run

VIDEO_HINT = {"video_broll", "atmosphere", "location"}
VISUAL_SOURCES = {"newspaper": ["loc_news"], "person": ["wiki_article"], "evidence": ["wiki_article"],
                  "archival_photo": ["wiki_article"], "location": ["wiki_article"], "document": ["loc_news"]}

# ---------------- Tải & chuẩn hoá ----------------

def _hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def fetch_image(c: dict, raw_dir: Path) -> Path | None:
    ext = os.path.splitext(c["url"].split("?")[0])[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".gif"):
        ext = ".jpg"
    dest = raw_dir / f"img_{_hash(c['url'])}{ext}"
    if dest.exists():
        return _to_jpg(dest)
    p = download(c["url"], dest, max_mb=40)
    return _to_jpg(p) if p else None


def _to_jpg(p: Path) -> Path | None:
    """Chuyển mọi định dạng sang JPG RGB (TIFF/WebP của LoC hay lỗi trong CapCut)."""
    from PIL import Image

    out = p.with_suffix(".jpg") if p.suffix.lower() != ".jpg" else p
    try:
        with Image.open(p) as im:
            if out != p or im.mode != "RGB":
                im = im.convert("RGB")
                if max(im.size) > 4000:
                    im.thumbnail((4000, 4000))
                im.save(out, quality=92)
        return out
    except Exception:  # noqa: BLE001
        return None


def has_burned_text(video: Path) -> bool:
    """Phát hiện phụ đề / chữ in sẵn ở 1/3 dưới khung hình (dải chữ trắng tương phản cao, nhiều nét dọc ngắn)."""
    import subprocess

    import numpy as np

    from .util import ffprobe_duration

    dur = ffprobe_duration(video)
    hits = 0
    for frac in (0.2, 0.5, 0.8):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur * frac:.2f}", "-i", str(video), "-frames:v", "1",
                            "-vf", "scale=480:270,format=gray", "-f", "rawvideo", "-"], capture_output=True)
        if len(r.stdout) < 480 * 270:
            continue
        f = np.frombuffer(r.stdout[:480 * 270], np.uint8).reshape(270, 480).astype(np.int16)
        dx = np.abs(np.diff(f, axis=1)) > 70  # biên ngang mạnh (nét chữ)
        rows = dx.mean(axis=1)
        band = rows[int(270 * 0.68):int(270 * 0.95)]
        top = rows[int(270 * 0.05):int(270 * 0.6)]
        bright = (f[int(270 * 0.68):int(270 * 0.95)] > 215).mean()
        # nhiều dòng liên tiếp có mật độ nét cao ở vùng dưới, cao hơn hẳn phần trên
        dense = (band > max(0.08, top.mean() * 2.5)).sum()
        if dense >= 6 and bright > 0.01:
            hits += 1
    return hits >= 2


def fetch_video_clip(c: dict, raw_dir: Path, seconds: float) -> Path | None:
    """Tải video -> cắt 1 đoạn (bỏ phần đầu/cuối thường là logo, chữ) -> MP4 H.264 720p không tiếng."""
    dest = raw_dir / f"vid_{_hash(c['url'])}.mp4"
    if dest.exists():
        return dest
    clip_len = max(seconds * 2.5, 12)
    try:
        if c.get("remote_cut"):
            dur = c.get("duration") or 300
            start = random.uniform(dur * 0.15, max(dur * 0.15 + 1, dur * 0.8 - clip_len))
            run(["ffmpeg", "-y", "-ss", f"{start:.1f}", "-i", c["url"], "-t", f"{clip_len:.1f}", "-an",
                 "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(dest)])
            return dest
        tmp = raw_dir / f"vid_{_hash(c['url'])}.src"
        ok = None
        for u in [c["url"]] + c.get("alt_urls", []) + ([c["fallback_url"]] if c.get("fallback_url") else []):
            ok = download(u, tmp, max_mb=120 if u == c.get("fallback_url") else 200)
            if ok:
                break
        if not ok:
            return None
        from .util import ffprobe_duration

        dur = ffprobe_duration(tmp)
        if dur < 2:
            tmp.unlink(missing_ok=True)
            return None
        start = 0.0 if dur <= clip_len + 2 else random.Random(c["url"]).uniform(dur * 0.1, dur * 0.85 - clip_len)
        run(["ffmpeg", "-y", "-ss", f"{max(0, start):.1f}", "-i", str(tmp), "-t", f"{clip_len:.1f}", "-an",
             "-vf", "scale=-2:'min(720,ih)',fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(dest)])
        tmp.unlink(missing_ok=True)
        if has_burned_text(dest):
            log(f"  - bỏ video có chữ/phụ đề in sẵn: {c.get('title', '')[:50]}")
            dest.unlink(missing_ok=True)
            return None
        return dest
    except Exception as e:  # noqa: BLE001
        log(f"  ! video lỗi: {str(e).splitlines()[0][:150]}")
        return None


# ---------------- Ảnh AI ----------------

def _finish_ai(dest: Path, crop_logo: bool, w: int) -> Path | None:
    """Chuẩn hoá ảnh AI: cắt logo góc dưới phải (Pollinations bản free), phóng lên 1920px, làm nét nhẹ."""
    from PIL import Image, ImageFilter

    try:
        with Image.open(dest) as im:
            im = im.convert("RGB")
            if crop_logo:  # logo nằm ở ~6% dưới cùng, góc phải -> cắt giữ nguyên tỉ lệ 16:9
                im = im.crop((0, 0, int(im.width * 0.91), int(im.height * 0.91)))
            if im.width < w:
                im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS).filter(
                    ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
            im.save(dest.with_suffix(".jpg"), quality=92)
        return dest.with_suffix(".jpg")
    except Exception as e:  # noqa: BLE001
        log(f"  ! ảnh AI hỏng: {e}")
        return None


def ai_image(prompt: str, dest: Path, cfg: dict, seed: int = 0, add_style: bool = True) -> Path | None:
    """Tạo ảnh AI. Backend (media.ai_backend):
      pollinations  miễn phí, không cần key (có logo -> tool tự cắt). Đăng ký token miễn phí tại auth.pollinations.ai
                    rồi đặt POLLINATIONS_TOKEN trong .env để dùng model Flux, ảnh nét hơn, không logo.
      openai        gpt-image-1 (đẹp nhất, có phí theo ảnh) - cần OPENAI_API_KEY.
      a1111         Stable Diffusion WebUI / Forge chạy trên máy bạn (Forge chạy được Flux) - cần card đồ hoạ.
    """
    import base64

    import requests

    mc = cfg["media"]
    backend = mc.get("ai_backend", "pollinations")
    prompt = re.sub(r"\s*--ar\s*\S+", "", prompt).strip()
    full = prompt + (mc.get("ai_style_suffix", "") if add_style else "")
    full = re.sub(r"\s+", " ", full).strip()[:900]  # bỏ xuống dòng / khoảng trắng thừa (gây lỗi 404), giới hạn độ dài
    w, h = cfg["render"]["width"], cfg["render"]["height"]
    dest = dest.with_suffix(".jpg")
    try:
        if backend == "pollinations":
            from urllib.parse import quote

            token = os.getenv("POLLINATIONS_TOKEN", "")
            url = (f"https://image.pollinations.ai/prompt/{quote(full)}?width={w}&height={h}"
                   f"&nologo=true&seed={seed}&model={mc.get('ai_model', 'flux')}&enhance=false")
            headers = {"Authorization": f"Bearer {token}"} if token else None
            if not download(url, dest, headers=headers, max_mb=20):
                return None
            return _finish_ai(dest, crop_logo=not token, w=w)
        if backend == "openai":
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                log("  ! thiếu OPENAI_API_KEY trong .env")
                return None
            r = requests.post("https://api.openai.com/v1/images/generations", timeout=300,
                              headers={"Authorization": f"Bearer {key}"},
                              json={"model": mc.get("ai_model_openai", "gpt-image-1"), "prompt": full,
                                    "size": "1536x1024", "quality": mc.get("ai_quality", "medium"), "n": 1})
            r.raise_for_status()
            dest.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
            return _finish_ai(dest, crop_logo=False, w=w)
        if backend == "a1111":
            r = requests.post(mc["a1111_url"].rstrip("/") + "/sdapi/v1/txt2img", json={
                "prompt": full, "negative_prompt": "text, watermark, gore, blood, deformed, cartoon",
                "width": 1344, "height": 768, "steps": 28, "seed": seed or -1}, timeout=600)
            r.raise_for_status()
            dest.write_bytes(base64.b64decode(r.json()["images"][0]))
            return _finish_ai(dest, crop_logo=False, w=w)
    except Exception as e:  # noqa: BLE001
        log(f"  ! AI image lỗi: {e}")
    return None


# ---------------- Gán media cho từng scene ----------------

def collect_ai_only(project: Project, cfg: dict, only: set[str] | None = None) -> dict:
    """Ảnh AI cho mọi cảnh (prompt từ image_prompts.json hoặc image_prompt_en).
    - Cảnh "character": AI chỉ vẽ NỀN trống (theo brand kit), nhân vật được vẽ bằng code ở bước dựng -> luôn nhất quán.
    - Cảnh "diagram"/"chart": không cần ảnh AI (sơ đồ dựng từ số liệu ở bước dựng).
    - Cảnh có scene["locked"] = true: giữ nguyên ảnh đã chọn."""
    from .mascot import brand_kit

    script = project.read_json("script.json")
    prompts = (project.read_json("image_prompts.json", {}) or {}).get("scenes", {})
    plan = project.read_json("media_plan.json", {})
    raw = project.path("media", "raw")
    wpm = cfg["channel"]["words_per_minute"]
    brand = brand_kit(cfg["render"].get("brand"))
    bg_style = brand.get("background_style") or ", 2D illustration background, empty scene with no people, no text"
    scenes = [s for c in script["chapters"] for s in c["scenes"]]
    bg_cache: dict[str, str] = {}
    for i, s in enumerate(scenes, 1):
        if only and s["id"] not in only:
            continue
        if s.get("locked") and plan.get(s["id"]):
            continue
        vt = s.get("visual_type", "")
        if vt in ("diagram", "chart"):
            plan[s["id"]] = []
            continue
        if vt in ("character", "insert"):
            need = 1  # 1 nền cho cả cảnh; biểu cảm/tư thế/từ khoá thay đổi ở bước dựng
            ps = [s["image_prompt_en"] + " " + bg_style]
            style_on = False
        else:
            ps = prompts.get(s["id"]) or [s["image_prompt_en"]]
            need = max(1, round(len(s["narration"].split()) / wpm * 60 / cfg["media"]["shot_seconds"]))
            need = max(need, len(ps)) if s["id"] in prompts else need
            style_on = s["id"] not in prompts
        log(f"[{i}/{len(scenes)}] {s['id']}: {need} ảnh AI" + (" (nền cho nhân vật)" if vt in ("character", "insert") else ""))
        items = []
        for k in range(need):
            dest = raw / f"ai_{s['id']}_{k + 1}.jpg"
            pr = ps[k % len(ps)]
            same = bg_cache.get(pr) if vt in ("character", "insert") else None
            if same and Path(same).exists() and not dest.exists():  # cùng bối cảnh -> cùng 1 căn phòng
                import shutil

                shutil.copy(same, dest)
            f = dest if dest.exists() else ai_image(
                pr, dest, cfg, seed=zlib.crc32(pr.encode()) % 100000 if vt in ("character", "insert")
                else zlib.crc32(f"{s['id']}{k}".encode()) % 100000, add_style=style_on)
            if f and vt in ("character", "insert"):
                bg_cache.setdefault(pr, str(f))
            if f:
                items.append({"kind": "image", "file": str(f), "credit": "AI-generated illustration", "page": "",
                              "w": 1920, "h": 1080})
        plan[s["id"]] = items
        project.write_json("media_plan.json", plan)
    log("✓ Xong ảnh AI")
    return plan


def find_entity_image(lib: Library, ent: dict, srcs: list[str]) -> dict | None:
    """Ảnh chân dung của 1 nhân vật thật. CHỈ nhận ảnh có tiêu đề chứa đủ họ tên người đó,
    để không bao giờ gắn nhầm mặt người khác vào tên nhân vật (rất nguy hiểm với phim tội phạm)."""
    import unicodedata

    def norm(x: str) -> str:
        x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9 ]", " ", x)

    name = norm(ent.get("name", ""))
    tokens = [t for t in name.split() if len(t) > 2]
    if not tokens:
        return None
    q = ent.get("search_query_en") or ent.get("name")

    def ok(r: dict) -> bool:
        t = norm(r["title"] + " " + r.get("page", ""))
        return all(tok in t for tok in tokens)

    pool = [r for r in lib.local_search(q, 40) if ok(r)]
    if not pool:
        try:
            pool = [r for r in lib.fetch(q, [x for x in ("wiki_article", "wikimedia", "loc") if x in srcs] or srcs,
                                         per_source=10, min_w=150) if ok(r)]
        except Exception as e:  # noqa: BLE001
            log(f"  ! tìm ảnh nhân vật lỗi: {e}")
    if not pool:
        return None
    # ưu tiên ảnh dọc/vuông (chân dung) và ảnh nằm trong bài Wikipedia
    pool.sort(key=lambda r: (r["src"].startswith("Wikipedia"), r["h"] >= r["w"] * 0.8, r["w"]), reverse=True)
    return pool[0]


def _need_shots(scene: dict, cfg: dict) -> int:
    est = len(scene["narration"].split()) / cfg["channel"]["words_per_minute"] * 60
    return max(1, round(est / cfg["media"]["shot_seconds"]))


def _scene_queries(scene: dict, topic_terms: str) -> list[str]:
    qs = [q for q in scene.get("search_queries_en", []) if q]
    # thêm truy vấn kèm tên vụ án để nguồn wiki_article / loc_news trúng hơn
    if topic_terms and qs and topic_terms.lower() not in qs[0].lower():
        qs.insert(1, f"{qs[0]} {topic_terms}")
    return qs or [topic_terms or "old archival photograph"]


def _hint_match(lib: Library, hint: str) -> dict | None:
    """Tìm ảnh trong thư viện theo tên file/tiêu đề (gợi ý 'media' trong kịch bản)."""
    h = hint.lower().replace("_", " ")
    best = None
    for r in lib.items.values():
        if r.get("dup_of") or not Path(r["file"]).exists():
            continue
        t = r["title"].lower().replace("_", " ")
        if h in t:
            score = (t.find(h) == 0, r["w"] * r["h"])
            if best is None or score > best[0]:
                best = (score, r)
    return best[1] if best else None


def apply_hints(project: Project, only: set[str] | None = None) -> dict:
    """Scene có trường "media": ["tên ảnh", ...] và "entity": {"media": "..."} -> gán đúng ảnh đó từ thư viện."""
    script = project.read_json("script.json")
    plan = project.read_json("media_plan.json", {})
    lib = Library()
    n = 0
    for c in script["chapters"]:
        for s in c["scenes"]:
            if only and s["id"] not in only:
                continue
            items = []
            for h in s.get("media", []):
                r = _hint_match(lib, h)
                if r and r["file"] not in [i["file"] for i in items]:
                    items.append(_rec_item(r))
            if items:
                plan[s["id"]] = items
                n += len(items)
            ent = s.get("entity")
            if ent and ent.get("media"):
                r = _hint_match(lib, ent["media"])
                if r:
                    plan[f"{s['id']}:entity"] = [_rec_item(r)]
    project.write_json("media_plan.json", plan)
    write_credits(project)
    log(f"✓ Gán {n} ảnh theo gợi ý trong kịch bản")
    return plan


def collect_media(project: Project, cfg: dict, only: set[str] | None = None, candidates: int = 0) -> dict:
    """Tạo media_plan.json. candidates>0: lưu thêm N ứng viên/scene và xuất review.html để chọn tay."""
    script = project.read_json("script.json")
    if not script:
        raise SystemExit("Chưa có script.json")
    mc = cfg["media"]
    lib = Library()
    raw = project.path("media", "raw")
    plan = project.read_json("media_plan.json", {})
    cand_store = project.read_json("candidates.json", {})
    used: set[str] = {m.get("lib_id") or m["file"] for v in plan.values() for m in v}
    research = project.read_json("research.json", {}) or {}
    topic_terms = research.get("en_query") or research.get("topic") or ""
    img_srcs = mc.get("image_sources", ["wiki_article", "wikimedia", "loc", "openverse"])
    # thời đại của vụ án (năm nhỏ nhất xuất hiện trong kịch bản) -> lọc ảnh/video lệch thời đại
    import itertools

    texts = itertools.chain([research.get("years", ""), script.get("title", ""), script.get("description", "")],
                            (s.get("on_screen_text", "") + " " + " ".join(s.get("search_queries_en", []))
                             for c in script["chapters"] for s in c["scenes"]))
    # thời đại = khoảng năm người dùng nhập (--years); không có thì lấy năm Ở GIỮA các năm trong kịch bản
    # (không lấy năm nhỏ nhất: kịch bản hay nhắc mốc lịch sử xa, vd "thị trấn lập năm 1870" trong vụ án 1912)
    ry = re.findall(r"\b(1[6-9]\d\d)\b", research.get("years", "") or "")
    yrs = sorted(int(y) for t in texts for y in re.findall(r"\b(1[6-9]\d\d)s?\b", t or ""))
    mid = int(ry[0]) if ry else (yrs[len(yrs) // 2] if yrs else 0)
    era = str(mid) if mid and mid < 1990 else ""
    if era:
        log(f"Thời đại vụ án: ~{era} -> bỏ ảnh/video quá hiện đại")
    use_clip = mc.get("clip_rank", "auto")
    use_clip = (use_clip is True) or (use_clip == "auto" and _has_clip())

    # 0) ảnh của chính bài Wikipedia về vụ án - lấy 1 lần, dùng ưu tiên
    if topic_terms and "wiki_article" in img_srcs and not project.path("media", ".wiki_done").exists():
        log(f"Lấy ảnh từ bài Wikipedia: {topic_terms}")
        lib.fetch(topic_terms, ["wiki_article", "loc_news"], per_source=40, min_w=500)
        project.path("media", ".wiki_done").write_text("1")

    if any(s.get("media") or s.get("entity") for c in script["chapters"] for s in c["scenes"]):
        plan = apply_hints(project, only)
        used |= {m.get("lib_id") or m["file"] for v in plan.values() for m in v}
    scenes = [s for c in script["chapters"] for s in c["scenes"]]
    ai_ids: set[str] = set()
    for i, s in enumerate(scenes):
        if only and s["id"] not in only:
            continue
        # cảnh lớp 2D (nhân vật/sơ đồ/biểu đồ): KHÔNG lấy ảnh thật -> nền AI trống hoặc không ảnh
        # cảnh không có từ khoá tìm kiếm và không rõ chủ đề: tìm ảnh thật sẽ ra ảnh lạc đề -> dùng AI
        if s.get("visual_type") in ("character", "diagram", "chart", "insert") or \
                (not s.get("search_queries_en") and not topic_terms):
            if not (s["id"] in plan and plan[s["id"]] and not only):
                ai_ids.add(s["id"])
            continue
        ent = s.get("entity")
        if s["id"] in plan and plan[s["id"]] and not only:
            if ent and ent.get("name") and f"{s['id']}:entity" not in plan:
                r = find_entity_image(lib, ent, img_srcs)
                plan[f"{s['id']}:entity"] = [_rec_item(r)] if r else []
            continue
        if ent and ent.get("name") and not plan.get(f"{s['id']}:entity"):
            r = find_entity_image(lib, ent, img_srcs)
            if r:
                plan[f"{s['id']}:entity"] = [_rec_item(r)]
                log(f"  nhân vật {ent['name']}: {r['title'][:50]}")
            else:
                log(f"  nhân vật {ent['name']}: không có ảnh công khai -> dùng bóng đen dấu hỏi")
        need = _need_shots(s, cfg)
        uniq_target = max(1, math.ceil(need * mc.get("unique_ratio", 0.7)))  # phần còn lại: zoom chi tiết cùng ảnh
        want_video = round(need * mc.get("video_ratio", 0.3)) if s["visual_type"] in VIDEO_HINT or need > 2 else 0
        queries = _scene_queries(s, topic_terms)
        log(f"[{i + 1}/{len(scenes)}] {s['id']} {need} shot/{uniq_target} ảnh, {want_video} video: {queries[:3]}")
        picked: list[dict] = []

        # 1) video b-roll (chỉ nhận video có tiêu đề/mô tả khớp từ khoá, tối đa 4 ứng viên/từ khoá để đỡ tốn thời gian)
        min_rel = mc.get("video_min_relevance", 0.34)
        for q in queries[::-1]:
            if sum(p["kind"] == "video" for p in picked) >= want_video:
                break
            cands = [c for c in sources.search_videos(q, mc.get("video_sources", []))
                     if keyword_score(q, c["title"]) >= min_rel and c["url"] not in used
                     and era_ok_strict(f"{q} {era}", c["title"])]
            for c in sorted(cands, key=lambda c: -keyword_score(q, c["title"]))[:4]:
                f = fetch_video_clip(c, raw, mc["shot_seconds"])
                if f and str(f) not in used:
                    picked.append({"kind": "video", "file": str(f), "credit": c["credit"], "page": c["page"]})
                    used.add(str(f))
                    used.add(c["url"])
                    log(f"  + video: {c['title'][:60]}")
                    break

        # 2) ảnh: thư viện trước, thiếu thì cào thêm
        pool: dict[str, dict] = {}
        extra = VISUAL_SOURCES.get(s["visual_type"], [])
        for q in queries:
            for r in lib.local_search(q, 30, exclude=None):
                pool[r["id"]] = r
            if len([r for r in pool.values() if r["id"] not in used]) < max(uniq_target * 3, candidates):
                for r in lib.fetch(q, list(dict.fromkeys(extra + img_srcs)), per_source=10,
                                   min_w=mc.get("min_width", 900)):
                    pool[r["id"]] = r
        ranked = lib.rank(" ".join(queries[:2]) + " " + s.get("image_prompt_en", "")[:120],
                          [r for r in pool.values() if r["id"] not in used], use_clip=use_clip)
        # ảnh phải khớp NỘI DUNG CẢNH (từ khoá chính, không tính tên vụ án). Không khớp -> để ảnh AI bù.
        primary = (s.get("search_queries_en") or [""])[0]
        topic_words = set(re.findall(r"[a-z0-9]{3,}", topic_terms.lower()))
        prim = " ".join(w for w in re.findall(r"[a-zA-Z0-9]{3,}", primary) if w.lower() not in topic_words)
        if not prim.strip():  # truy vấn cảnh = đúng chủ đề (vd "Greenland shark") -> vẫn phải khớp chủ đề
            prim = primary
        min_img = mc.get("image_min_relevance", 0.34)

        common = {"The", "A", "An", "Of", "In", "On", "At", "And", "Old", "New", "Night", "Police", "Navy", "Army"}
        proper = [w.lower() for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}", prim) if w not in common]

        def relevant(r: dict) -> bool:
            text = r["title"] + " " + " ".join(r.get("queries", []))
            if s["visual_type"] in ("person", "board") or not prim:
                return True
            if proper and not all(pn in r["title"].lower() for pn in proper):
                return False  # tên riêng (địa danh, tên tàu...) phải có trong tiêu đề ảnh
            return keyword_score(prim, text) >= min_img or keyword_score(primary, r["title"]) >= 0.67

        ranked = [r for r in ranked if relevant(r) and era_ok_strict(f"{primary} {era}", r["title"])]
        for r in ranked:
            if sum(p["kind"] == "image" for p in picked) >= uniq_target - sum(p["kind"] == "video" for p in picked):
                break
            picked.append(_rec_item(r))
            used.add(r["id"])
            r.setdefault("used_in", []).append(project.slug)
        if candidates:
            cand_store[s["id"]] = [_rec_item(r) for r in ranked[:candidates]]

        # 3) ảnh AI: cảnh không khí luôn có 1 ảnh AI (đêm, rừng, bóng người...), cảnh khác chỉ bù khi thiếu ảnh thật
        ai_on = mc.get("ai_images") and mc.get("ai_backend") != "none" and s.get("image_prompt_en")
        want_ai = 0
        if ai_on:
            want_ai = max(0, min(uniq_target, need) - len(picked))
            if s["visual_type"] in mc.get("ai_for_visual_types", ["atmosphere"]) and want_ai == 0:
                want_ai = 1
        for k in range(want_ai):
            dest = raw / f"ai_{s['id']}_{k}.jpg"
            pr = s["image_prompt_en"] if k == 0 else f"{s['image_prompt_en']}, different angle, wide shot"
            f = dest if dest.exists() else ai_image(pr, dest, cfg, seed=zlib.crc32(s["id"].encode()) % 10000 + k)
            if f:
                item = {"kind": "image", "file": str(f), "credit": "AI-generated illustration", "page": "",
                        "w": 1920, "h": 1080}
                # ảnh AI không khí đặt lên đầu cảnh (mở cảnh), ảnh bù thì đặt cuối
                picked.insert(0, item) if s["visual_type"] in mc.get("ai_for_visual_types", ["atmosphere"]) \
                    else picked.append(item)
                log(f"  + ảnh AI: {pr[:60]}")
        plan[s["id"]] = picked
        project.write_json("media_plan.json", plan)
        if candidates:
            project.write_json("candidates.json", cand_store)
    lib.save()
    if ai_ids:
        project.write_json("media_plan.json", plan)
        plan = collect_ai_only(project, cfg, ai_ids)
    write_credits(project)
    if candidates:
        review_page(project)
    log(f"✓ media_plan.json ({sum(len(v) for v in plan.values())} file)")
    return plan


def _rec_item(r: dict) -> dict:
    return {"kind": "image", "file": r["file"], "credit": r["credit"], "page": r["page"], "lib_id": r["id"],
            "license": r.get("license", ""), "src": r["src"], "visual": r.get("visual", ""), "focus": r.get("focus"),
            "w": r.get("w", 0), "h": r.get("h", 0),
            "title": r.get("title", "")[:200]}


def _has_clip() -> bool:
    try:
        import sentence_transformers  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def write_credits(project: Project) -> None:
    plan = project.read_json("media_plan.json", {})
    lines = sorted({f"{m['credit']} - {m.get('page', '')}".strip(" -") for v in plan.values() for m in v
                    if m.get("credit") and m["credit"] not in ("imported", "own/licensed", "")})
    project.path("output", "credits.txt").write_text("\n".join(lines), encoding="utf-8")


def review_page(project: Project) -> Path:
    """review.html: mỗi scene hiện lời dẫn + ảnh đang chọn + ứng viên. Click để chọn/bỏ, kéo thứ tự bằng số,
    bấm 'Tải selection.json' rồi chạy: python studio.py media <slug> --apply selection.json"""
    script = project.read_json("script.json")
    plan = project.read_json("media_plan.json", {})
    cands = project.read_json("candidates.json", {})
    out = project.path("review.html")
    rows = []
    for c in script["chapters"]:
        rows.append(f"<h2>{html.escape(c['title'])}</h2>")
        for s in c["scenes"]:
            chosen = [m["file"] for m in plan.get(s["id"], [])]
            allf = chosen + [m["file"] for m in cands.get(s["id"], []) if m["file"] not in chosen]
            thumbs = []
            for f in allf:
                rel = os.path.relpath(f, out.parent).replace("\\", "/")
                is_vid = f.lower().endswith((".mp4", ".mov", ".webm"))
                tag = (f'<video src="{html.escape(rel)}" muted loop onmouseover="this.play()"></video>' if is_vid
                       else f'<img loading="lazy" src="{html.escape(rel)}">')
                thumbs.append(f'<div class="t{" on" if f in chosen else ""}" data-f="{html.escape(f)}" '
                              f'onclick="tog(this)">{tag}<span></span></div>')
            rows.append(f'<section data-id="{s["id"]}"><p><b>{s["id"]}</b> {html.escape(s["narration"])}<br>'
                        f'<i>{html.escape(", ".join(s.get("search_queries_en", [])))}</i></p>'
                        f'<div class="row">{"".join(thumbs)}</div></section>')
    out.write_text("""<!doctype html><meta charset="utf-8"><title>Review media</title><style>
body{background:#111;color:#ddd;font:14px system-ui;margin:16px 16px 80px}section{border-bottom:1px solid #333;padding:8px 0}
.row{display:flex;flex-wrap:wrap;gap:6px}.t{position:relative;width:200px;height:113px;border:3px solid transparent;
cursor:pointer;opacity:.55}.t.on{border-color:#e8c070;opacity:1}.t img,.t video{width:100%;height:100%;object-fit:cover}
.t span{position:absolute;top:2px;left:4px;color:#000;background:#e8c070;font-weight:bold;padding:0 5px}
.t:not(.on) span{display:none}i{color:#888}h2{color:#e8c070}
#bar{position:fixed;bottom:0;left:0;right:0;background:#222;padding:10px;text-align:center}
button{font-size:16px;padding:6px 18px}</style>""" + "".join(rows) + """
<div id="bar"><button onclick="save()">Tải selection.json</button> Click ảnh để chọn/bỏ. Thứ tự = thứ tự click.</div>
<script>
const order={};document.querySelectorAll('section').forEach(s=>{order[s.dataset.id]=[...s.querySelectorAll('.t.on')]
.map(t=>t.dataset.f);num(s)});
function num(s){const o=order[s.dataset.id];s.querySelectorAll('.t').forEach(t=>{const i=o.indexOf(t.dataset.f);
t.querySelector('span').textContent=i+1;t.classList.toggle('on',i>=0)})}
function tog(t){const s=t.closest('section'),o=order[s.dataset.id],i=o.indexOf(t.dataset.f);
i>=0?o.splice(i,1):o.push(t.dataset.f);num(s)}
function save(){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(order,null,1)],
{type:'application/json'}));a.download='selection.json';a.click()}
</script>""", "utf-8")
    log(f"✓ Mở để chọn ảnh: {out}")
    return out


def apply_selection(project: Project, path: str) -> None:
    sel = json.loads(Path(path).read_text("utf-8"))
    plan = project.read_json("media_plan.json", {})
    cands = project.read_json("candidates.json", {})
    for sid, files in sel.items():
        known = {m["file"]: m for m in plan.get(sid, []) + cands.get(sid, [])}
        plan[sid] = [known.get(f) or {"kind": "video" if f.lower().endswith((".mp4", ".mov")) else "image",
                                      "file": f, "credit": "own/licensed", "page": ""} for f in files]
    project.write_json("media_plan.json", plan)
    write_credits(project)
    log(f"✓ Áp dụng lựa chọn cho {len(sel)} scene")


def add_manual_media(project: Project, scene_id: str, files: list[str]) -> None:
    """Gán file của bạn (ảnh/video tự tìm, tự chụp, mua bản quyền...) vào một scene."""
    plan = project.read_json("media_plan.json", {})
    items = plan.setdefault(scene_id, [])
    for f in files:
        kind = "video" if Path(f).suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi") else "image"
        items.insert(0, {"kind": kind, "file": str(Path(f).resolve()), "credit": "own/licensed", "page": ""})
    project.write_json("media_plan.json", plan)
    log(f"✓ Đã thêm {len(files)} file vào {scene_id}")


def download_url_clip(project: Project, scene_id: str, url: str, start: str = "", end: str = "") -> None:
    """Tải đoạn video từ link (YouTube, Vimeo...) bằng yt-dlp. CHỈ dùng với video bạn có quyền sử dụng
    (Creative Commons, public domain, của bạn, hoặc đã xin phép)."""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        raise SystemExit("pip install yt-dlp")
    out = project.path("media", "raw", f"url_{_hash(url + start)}.%(ext)s")
    opts = {"outtmpl": str(out), "format": "bv*[height<=1080][ext=mp4]+ba/b[height<=1080]/b",
            "merge_output_format": "mp4", "quiet": True}
    if start or end:
        from yt_dlp.utils import download_range_func  # type: ignore

        def _t(x):
            parts = [float(p) for p in x.split(":")]
            return sum(v * 60 ** i for i, v in enumerate(reversed(parts)))

        opts["download_ranges"] = download_range_func(None, [(_t(start or "0"), _t(end) if end else 1e9)])
        opts["force_keyframes_at_cuts"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    path = str(Path(path).with_suffix(".mp4")) if not Path(path).exists() else path
    add_manual_media(project, scene_id, [path])
    lic = info.get("license") or "không rõ - hãy tự kiểm tra"
    credits = project.read_json("credits.json", {})
    credits[url] = f"{info.get('title', '')} - {info.get('uploader', '')} ({lic}) - {url}"
    project.write_json("credits.json", credits)
    log(f"  Giấy phép video: {lic}")

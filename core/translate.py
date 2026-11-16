"""Tạo bản ngôn ngữ khác của 1 video:  python studio.py translate <slug> --to en

- Dịch kịch bản theo TỪNG CẢNH (giữ nguyên số cảnh, mã cảnh, hiệu ứng, ánh sáng, nhạc, loại hình...)
- Dùng lại ảnh/video đã tìm của bản gốc (media_plan.json) -> không phải cào lại
- Project mới: <slug>-<lang> (vd tham-an-villisca-nam-1912-en), sau đó chỉ cần: voice -> render
"""
from __future__ import annotations

import copy
import json
import shutil

from .util import ROOT, Project, log

LANG = {"en": "English", "vi": "tiếng Việt"}

# trường chữ cần dịch: tên trong bản dịch -> đường dẫn trong cảnh
FIELDS = {"narration": ("narration",), "on_screen_text": ("on_screen_text",), "purpose": ("purpose",),
          "hud": ("hud",), "thought": ("character", "thought"), "shadow": ("character", "shadow"),
          "outside": ("character", "outside"), "inside": ("character", "inside"), "stat_label": ("stat", "label"),
          "insert_text": ("insert", "text"), "insert_date": ("insert", "date"), "entity_role": ("entity", "role")}

TR_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "narration": {"type": "string"}, "on_screen_text": {"type": "string"},
                    "purpose": {"type": "string"}, "hud": {"type": "string"},
                    "thought": {"type": "string"}, "shadow": {"type": "string"},
                    "outside": {"type": "string"}, "inside": {"type": "string"},
                    "stat_label": {"type": "string"}, "insert_text": {"type": "string"},
                    "insert_date": {"type": "string"}, "entity_role": {"type": "string"},
                    "emphasis": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "messages": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "narration", "on_screen_text", "purpose", "hud", "thought", "shadow", "outside",
                             "inside", "stat_label", "insert_text", "insert_date", "entity_role", "emphasis",
                             "keywords", "messages"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}
META_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"}, "title_line1": {"type": "string"}, "title_line2": {"type": "string"},
        "thumbnail_text": {"type": "string"}, "hook": {"type": "string"}, "description": {"type": "string"},
        "youtube_titles": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "chapter_titles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "title_line1", "title_line2", "thumbnail_text", "hook", "description", "youtube_titles",
                 "tags", "chapter_titles"],
    "additionalProperties": False,
}

SYSTEM = """You are a professional documentary script translator and YouTube narrator-writer.
Translate faithfully but naturally for voice-over in {lang}: short spoken sentences, same facts, same tone and
suspense, same number of scenes. Do NOT add or remove facts. Write all numbers, years and dates as words in
narration (they are read by a TTS voice). Keep personal names and place names in their original spelling.
"emphasis" items must be phrases that appear VERBATIM in your translated narration. Return only the JSON."""


def _get(d, path):
    for k in path:
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d or ""


def _set(d, path, v):
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = v


def translate_project(src_slug: str, lang: str, cfg: dict) -> Project:
    from .scriptgen import get_writer, save_script

    src = Project(src_slug)
    script = src.read_json("script.json")
    if not script:
        raise SystemExit("Bản gốc chưa có kịch bản")
    dst = Project(f"{src_slug}-{lang}")
    meta = src.read_json("project.json", {}) or {}
    meta.setdefault("project", {})["language"] = lang
    meta["translated_from"] = src_slug
    dst.write_json("project.json", meta)
    for f in ("research.json", "media_plan.json", "credits.json"):
        if src.path(f).exists():
            shutil.copy(src.path(f), dst.path(f))
    if src.path("output", "credits.txt").exists():
        shutil.copy(src.path("output", "credits.txt"), dst.path("output", "credits.txt"))

    w = get_writer(cfg)
    sysmsg = SYSTEM.format(lang=LANG.get(lang, lang))
    out = copy.deepcopy(script)
    done = dst.read_json("_translate_partial.json", {}) or {}  # dịch dở thì chạy lại sẽ tiếp tục
    for ci, chap in enumerate(out["chapters"]):
        if str(ci) in done:
            chap["scenes"] = done[str(ci)]
            continue
        log(f"Dịch chương {ci + 1}/{len(out['chapters'])}: {chap.get('title', '')}")
        payload = [{"id": sc["id"], **{k: _get(sc, path) for k, path in FIELDS.items()},
                    "emphasis": sc.get("emphasis") or [], "keywords": (sc.get("character") or {}).get("keywords") or [],
                    "messages": [m.get("text", "") for m in (sc.get("insert") or {}).get("messages") or []]}
                   for sc in chap["scenes"]]
        res = w.ask_json(sysmsg, f"Translate every text field of these {len(payload)} scenes into "
                                 f"{LANG.get(lang, lang)}. Keep the same ids and order.\n"
                         + json.dumps(payload, ensure_ascii=False), TR_SCHEMA)
        got = {x["id"]: x for x in res.get("scenes") or []}
        miss = [sc["id"] for sc in chap["scenes"] if sc["id"] not in got]
        if miss:
            raise SystemExit(f"Bản dịch thiếu cảnh {', '.join(miss[:5])} - chạy lại lệnh translate để thử lại")
        for sc in chap["scenes"]:
            t = got[sc["id"]]
            for k, path in FIELDS.items():
                if _get(sc, path) or t.get(k):
                    _set(sc, path, t.get(k, ""))
            sc["emphasis"] = t.get("emphasis") or []
            if sc.get("character"):
                sc["character"]["keywords"] = t.get("keywords") or []
            for m, tx in zip((sc.get("insert") or {}).get("messages") or [], t.get("messages") or []):
                m["text"] = tx
        done[str(ci)] = chap["scenes"]
        dst.write_json("_translate_partial.json", done)
    m = w.ask_json(sysmsg, "Translate the video metadata (titles, hook, description, tags, chapter titles in order). "
                           "Titles must be catchy YouTube titles in the target language.\n"
                   + json.dumps({k: script.get(k) for k in ("title", "title_line1", "title_line2", "thumbnail_text",
                                                             "hook", "description", "youtube_titles", "tags")}
                                | {"chapter_titles": [c.get("title", "") for c in script["chapters"]]},
                                ensure_ascii=False), META_SCHEMA)
    for k in ("title", "title_line1", "title_line2", "thumbnail_text", "hook", "description", "youtube_titles", "tags"):
        out[k] = m.get(k) or out.get(k)
    for c, t in zip(out["chapters"], m.get("chapter_titles") or []):
        c["title"] = t or c.get("title")
    save_script(dst, out)
    dst.path("_translate_partial.json").unlink(missing_ok=True)
    log(f"✓ Bản {LANG.get(lang, lang)}: {dst.slug} ({sum(len(c['scenes']) for c in out['chapters'])} cảnh, "
        f"dùng lại hình của bản gốc). Tiếp theo: voice -> render")
    return dst

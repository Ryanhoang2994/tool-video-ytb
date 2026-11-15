"""Sửa / khoá / tạo lại RIÊNG một cảnh mà không làm lại cả video.

  python studio.py scene <slug> s012 --show
  python studio.py scene <slug> s012 --narration "Lời mới..."        # chỉ cảnh này đọc lại
  python studio.py scene <slug> s012 --prompt "new background..." --regen-image
  python studio.py scene <slug> s012 --camera push_in --text "Boston, 1962"
  python studio.py scene <slug> s012 --expression worried --pose think --thought "..." --keywords "A" "B"
  python studio.py scene <slug> s012 --lock          # giữ nguyên ảnh/giọng đã chọn, các lệnh media/voice bỏ qua
  python studio.py scene <slug> s012 ... --rebuild   # làm luôn: đọc lại (nếu cần) + ảnh (nếu cần) + render
Render chỉ dựng lại những đoạn thay đổi (phần còn lại lấy từ cache).
"""
from __future__ import annotations

import json
from pathlib import Path

from .util import Project, log


def _find(script: dict, sid: str) -> dict:
    for c in script["chapters"]:
        for s in c["scenes"]:
            if s["id"] == sid:
                return s
    raise SystemExit(f"Không có cảnh {sid}")


def edit_scene(project: Project, sid: str, a) -> dict:
    from .scriptgen import save_script

    script = project.read_json("script.json")
    s = _find(script, sid)
    if a.show:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return {}
    need = {"voice": False, "media": False}
    if a.narration is not None:
        s["narration"] = a.narration
        need["voice"] = True
    if a.prompt is not None:
        s["image_prompt_en"] = a.prompt
        need["media"] = True
    if a.queries:
        s["search_queries_en"] = a.queries
        need["media"] = True
    if a.camera:
        s["camera"] = a.camera
    if a.text is not None:
        s["on_screen_text"] = a.text
        if s.get("visual_type") == "quote":
            need["voice"] = True
    if a.visual:
        s["visual_type"] = a.visual
        need["media"] = True
    ch = s.setdefault("character", {})
    for k in ("expression", "pose", "position", "thought", "outside", "inside"):
        v = getattr(a, k, None)
        if v is not None:
            ch[k] = v
    if a.keywords is not None:
        ch["keywords"] = a.keywords
    if a.lock:
        s["locked"] = True
    if a.unlock:
        s.pop("locked", None)
    if a.regen_image:
        need["media"] = True
    if a.regen_voice:
        need["voice"] = True
    save_script(project, script)
    if need["voice"]:
        project.path("audio", f"{sid}.wav").unlink(missing_ok=True)
        timing = project.read_json("timing.json", {})
        timing.pop(sid, None)
        project.write_json("timing.json", timing)
    if need["media"] and not s.get("locked"):
        plan = project.read_json("media_plan.json", {})
        for m in plan.pop(sid, []):
            if Path(m["file"]).name.startswith(f"ai_{sid}_"):
                Path(m["file"]).unlink(missing_ok=True)
        project.write_json("media_plan.json", plan)
    log(f"✓ Đã sửa {sid}" + (" | cần đọc lại" if need["voice"] else "") + (" | cần ảnh mới" if need["media"] else "")
        + (" | ĐÃ KHOÁ" if s.get("locked") else ""))
    return need


def rebuild_scene(project: Project, sid: str, cfg: dict, need: dict) -> None:
    from . import media, render, tts
    from .timeline import build_timeline

    if need.get("voice"):
        tts.make_voice(project, cfg, {sid})
    if need.get("media"):
        if cfg["media"].get("mode") == "ai_only":
            media.collect_ai_only(project, cfg, {sid})
        else:
            media.collect_media(project, cfg, {sid})
    build_timeline(project, cfg)
    render.render_video(project, cfg)

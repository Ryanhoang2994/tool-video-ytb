"""Bước "PROMPT 2": tạo prompt ảnh AI cho từng shot của kịch bản, giữ phong cách và nhân vật nhất quán.

  python studio.py imageprompts <slug>            # Claude tạo -> image_prompts.json + image_prompts.txt
  python studio.py imageprompts <slug> --manual   # xuất prompt để dán vào claude.ai / ChatGPT
Sau đó:
  python studio.py media <slug> --ai-only         # tự tạo ảnh bằng backend AI trong config
  hoặc tự tạo ảnh ở Midjourney/ChatGPT/Flux, đặt tên s001_1.png, s001_2.png... vào 1 thư mục rồi:
  python studio.py media <slug> --import-dir D:\\anh_ai
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import Project, log

SCHEMA = {
    "type": "object",
    "properties": {
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_id": {"type": "string"},
                    "prompts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["scene_id", "prompts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["shots"],
    "additionalProperties": False,
}

STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "style_bible": {"type": "string"},
        "characters": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "look": {"type": "string"}},
            "required": ["name", "look"], "additionalProperties": False}},
    },
    "required": ["style_bible", "characters"],
    "additionalProperties": False,
}

SYSTEM = """You are an expert AI image prompt designer for a true-crime / historical documentary YouTube channel.
You write realistic, cinematic, documentary-style prompts with historical accuracy: period-correct architecture,
clothing, vehicles, props, and lighting (chiaroscuro, moody, film grain). No text or typography in images.
No gore or depicted violence on bodies: suggest tension through environment, shadows, objects, aftermath, and faces.
Never depict an identifiable real person as committing a crime; show them from behind, in silhouette, or at a distance."""


def _need(scene: dict, cfg: dict) -> int:
    est = len(scene["narration"].split()) / cfg["channel"]["words_per_minute"] * 60
    return max(1, round(est / cfg["media"]["shot_seconds"]))


def _style_prompt(script: dict) -> str:
    outline = "\n".join(f"{i + 1}. {c['title']}: " + " ".join(s["narration"] for s in c["scenes"])[:1500]
                        for i, c in enumerate(script["chapters"]))
    return f"""Video: {script['title']}
<script_summary>
{outline}
</script_summary>
Write a short STYLE BIBLE (era, place, color palette, camera/lens, lighting, film look) that every image prompt will
share, and a list of recurring characters with a fixed physical description (age, build, hair, period clothing)
so they look the same in every image."""


def _chapter_prompt(script: dict, ci: int, style: dict, cfg: dict) -> str:
    chap = script["chapters"][ci]
    chars = "\n".join(f"- {c['name']}: {c['look']}" for c in style["characters"])
    scenes = "\n".join(f'<scene id="{s["id"]}" images="{_need(s, cfg)}">{s["narration"]}</scene>'
                       for s in chap["scenes"])
    return f"""STYLE BIBLE: {style['style_bible']}
CHARACTERS:
{chars}

Chapter {ci + 1}: {chap['title']}
{scenes}

For EVERY scene, write exactly the number of image prompts given in its `images` attribute, in story order.
Each prompt: one distinct moment/angle (wide establishing, medium, close-up detail, object insert, location),
40-80 words, English, includes the style bible keywords, describes characters using their fixed description,
ends with "--ar 16:9". Vary composition so consecutive images don't look the same."""


def generate(project: Project, cfg: dict) -> dict:
    from .scriptgen import get_writer

    script = project.read_json("script.json")
    if not script:
        raise SystemExit("Chưa có script.json")
    w = get_writer(cfg)
    data = project.read_json("image_prompts.json", {})
    if "style" not in data:
        log("Claude tạo style bible + nhân vật...")
        data["style"] = w.ask_json(SYSTEM, _style_prompt(script), STYLE_SCHEMA)
        project.write_json("image_prompts.json", data)
    data.setdefault("scenes", {})
    for ci, chap in enumerate(script["chapters"]):
        if all(s["id"] in data["scenes"] for s in chap["scenes"]):
            continue
        log(f"Prompt ảnh chương {ci + 1}/{len(script['chapters'])}")
        res = w.ask_json(SYSTEM, _chapter_prompt(script, ci, data["style"], cfg), SCHEMA)
        for item in res["shots"]:
            data["scenes"][item["scene_id"]] = item["prompts"]
        project.write_json("image_prompts.json", data)
    _write_txt(project, script, data)
    return data


def _write_txt(project: Project, script: dict, data: dict) -> None:
    lines = [f"STYLE: {data['style']['style_bible']}\n"]
    for c in script["chapters"]:
        lines.append(f"\n===== {c['title']} =====")
        for s in c["scenes"]:
            for k, p in enumerate(data["scenes"].get(s["id"], []), 1):
                lines.append(f"{s['id']}_{k}: {p}")
    p = project.path("image_prompts.txt")
    p.write_text("\n".join(lines), encoding="utf-8")
    n = sum(len(v) for v in data["scenes"].values())
    log(f"✓ {n} prompt ảnh -> {p}\n  Tên file ảnh nên đặt đúng mã ở đầu dòng (vd s001_1.png) để import tự động.")


def manual(project: Project, cfg: dict) -> Path:
    script = project.read_json("script.json")
    out = [SYSTEM, "", "STEP 1:", _style_prompt(script), "",
           "STEP 2: Then, for each chapter below, follow these rules and answer as lines `scene_id_N: prompt`."]
    fake_style = {"style_bible": "(use the style bible from step 1)", "characters": []}
    for ci in range(len(script["chapters"])):
        out += ["", f"--- CHAPTER {ci + 1} ---", _chapter_prompt(script, ci, fake_style, cfg)]
    p = project.path("prompt_images_for_chatbot.txt")
    p.write_text("\n".join(out), encoding="utf-8")
    log(f"✓ Đã xuất {p}. Dán kết quả (dạng `s001_1: ...`) vào image_prompts.txt rồi chạy "
        f"`python studio.py imageprompts {project.slug} --import-txt image_prompts.txt`")
    return p


def import_txt(project: Project, path: str) -> dict:
    data = project.read_json("image_prompts.json", {}) or {}
    data.setdefault("style", {"style_bible": "", "characters": []})
    data.setdefault("scenes", {})
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*\**(s\d{3})_(\d+)\**\s*[:\-–]\s*(.+)", line)
        if m:
            lst = data["scenes"].setdefault(m.group(1), [])
            lst.append(m.group(3).strip())
    project.write_json("image_prompts.json", data)
    log(f"✓ Nhập {sum(len(v) for v in data['scenes'].values())} prompt")
    return data


def import_dir(project: Project, folder: str) -> None:
    """Gán ảnh/video bạn tự tạo (đặt tên s001_1.png, s001_2.jpg, s014.mp4...) vào đúng scene."""
    plan = project.read_json("media_plan.json", {})
    touched: set[str] = set()
    n = 0
    for f in sorted(Path(folder).iterdir(), key=lambda f: (f.stem.split("_")[0], int((re.findall(r"_(\d+)", f.stem) or ["0"])[0]))):
        m = re.match(r"(s\d{3})(?:_(\d+))?$", f.stem, re.I)
        if not m or f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"):
            continue
        sid = m.group(1).lower()
        if sid not in touched:  # ảnh import thay thế media cũ của scene đó
            plan[sid] = []
            touched.add(sid)
        kind = "video" if f.suffix.lower() in (".mp4", ".mov") else "image"
        plan[sid].append({"kind": kind, "file": str(f.resolve()), "credit": "imported", "page": ""})
        n += 1
    project.write_json("media_plan.json", plan)
    log(f"✓ Đã gán {n} file vào {len(touched)} scene")

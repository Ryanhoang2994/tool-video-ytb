"""Chuyển project giữa các máy (VPS Linux -> PC Windows có CapCut).

  python studio.py pack <slug>       # trên VPS: đóng gói project + ảnh trong thư viện nó dùng -> <slug>_pack.zip
  python studio.py unpack file.zip   # trên PC: giải nén vào đúng chỗ + sửa đường dẫn
  python studio.py relink <slug>     # sửa đường dẫn tuyệt đối trong project cho khớp máy hiện tại
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from .util import ROOT, Project, log

MARKERS = ("library/images/", "projects/", "assets/")
JSON_FILES = ("media_plan.json", "candidates.json", "timeline.json", "timing.json", "image_prompts.json")


def _fix(v: str) -> str:
    s = v.replace("\\", "/")
    for m in MARKERS:
        i = s.find("/" + m) if not s.startswith(m) else -1
        if s.startswith(m):
            return str(ROOT / s)
        if i >= 0:
            return str(ROOT / s[i + 1:])
    return v


def _walk(o):
    if isinstance(o, dict):
        return {k: _walk(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(v) for v in o]
    if isinstance(o, str) and re.search(r"(library/images/|projects/|assets/)", o.replace("\\", "/")):
        return _fix(o)
    return o


def relink(project: Project) -> None:
    n = 0
    for name in JSON_FILES:
        p = project.path(name)
        if p.exists():
            data = json.loads(p.read_text("utf-8"))
            p.write_text(json.dumps(_walk(data), ensure_ascii=False, indent=2), "utf-8")
            n += 1
    # ảnh nhân vật / thư viện có index riêng
    idx = ROOT / "library" / "index.json"
    if idx.exists():
        d = json.loads(idx.read_text("utf-8"))
        idx.write_text(json.dumps(_walk(d), ensure_ascii=False, indent=1), "utf-8")
    log(f"✓ Đã sửa đường dẫn trong {n} file của {project.slug} cho máy này ({ROOT})")


def pack(project: Project, include_renders: bool = False) -> Path:
    out = ROOT / f"{project.slug}_pack.zip"
    plan = project.read_json("media_plan.json", {})
    files = {Path(m["file"]) for v in plan.values() for m in v if m.get("file")}
    lib_ids = {m.get("lib_id") for v in plan.values() for m in v if m.get("lib_id")}
    skip_dirs = {"shots", "plates"} if not include_renders else set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in project.dir.rglob("*"):
            rel = f.relative_to(ROOT)
            regen = f.name in ("voice_full.wav", "sfx_track.wav", "_voice_list.txt") or "_sil" in f.parts
            if f.is_file() and not regen and not (set(f.relative_to(project.dir).parts) & skip_dirs) and \
                    not (f.suffix == ".mp4" and f.parent.name == "output" and not include_renders):
                z.write(f, rel.as_posix())
        for f in files:
            if f.exists() and ROOT in f.parents and project.dir not in f.parents:
                z.write(f, f.relative_to(ROOT).as_posix())
        idx = ROOT / "library" / "index.json"
        if idx.exists():
            d = json.loads(idx.read_text("utf-8"))
            z.writestr("library/index_pack.json", json.dumps({k: v for k, v in d.items() if k in lib_ids},
                                                             ensure_ascii=False))
    log(f"✓ Đóng gói: {out} ({out.stat().st_size / 1e6:.0f} MB). Chép sang máy kia rồi chạy: "
        f"python studio.py unpack {out.name}")
    return out


def unpack(zip_path: str) -> None:
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(ROOT)
        names = z.namelist()
    pi = ROOT / "library" / "index_pack.json"
    if pi.exists():
        idx_p = ROOT / "library" / "index.json"
        cur = json.loads(idx_p.read_text("utf-8")) if idx_p.exists() else {}
        cur.update(json.loads(pi.read_text("utf-8")))
        idx_p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), "utf-8")
        pi.unlink()
    slugs = {n.split("/")[1] for n in names if n.startswith("projects/") and n.count("/") >= 2}
    for slug in slugs:
        relink(Project(slug))
    log(f"✓ Đã giải nén: {', '.join(slugs)}")

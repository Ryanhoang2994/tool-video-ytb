"""Giao diện web chạy trên máy:  python studio.py ui   ->  mở http://127.0.0.1:7860

Mọi việc nặng (research, giọng đọc, ảnh, dựng video) vẫn do studio.py làm: giao diện chỉ gọi lệnh,
hiện log trực tiếp, sửa storyboard từng cảnh và xem kết quả.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.util import list_presets, slugify  # noqa: E402

PROJECTS = ROOT / "projects"
LIBRARY = ROOT / "library"
STATIC = Path(__file__).resolve().parent / "static"

ENV_KEYS = [
    ("ANTHROPIC_API_KEY", "Claude – tự viết kịch bản, soát chính tả", "console.anthropic.com", "Trả phí"),
    ("PEXELS_API_KEY", "Ảnh + video có sẵn (Pexels)", "pexels.com/api", "Miễn phí"),
    ("PIXABAY_API_KEY", "Ảnh + video có sẵn (Pixabay)", "pixabay.com/api/docs", "Miễn phí"),
    ("POLLINATIONS_TOKEN", "Ảnh AI không logo, nhanh hơn", "auth.pollinations.ai", "Miễn phí"),
    ("FLICKR_API_KEY", "Ảnh Flickr (giấy phép mở)", "flickr.com/services/apps/create", "Miễn phí"),
    ("UNSPLASH_ACCESS_KEY", "Ảnh Unsplash", "unsplash.com/developers", "Miễn phí"),
    ("EUROPEANA_API_KEY", "Ảnh tư liệu châu Âu", "pro.europeana.eu/page/get-api", "Miễn phí"),
    ("SMITHSONIAN_API_KEY", "Ảnh bảo tàng Smithsonian", "api.data.gov/signup", "Miễn phí"),
    ("OPENAI_API_KEY", "Ảnh AI chất lượng cao (gpt-image-1)", "platform.openai.com", "Trả phí"),
    ("GOOGLE_TTS_API_KEY", "Giọng Google Chirp 3 HD", "console.cloud.google.com", "Có hạn mức miễn phí"),
    ("ELEVENLABS_API_KEY", "Giọng ElevenLabs", "elevenlabs.io", "Trả phí"),
]
STEP_CMDS = {
    "research": lambda slug, o: [["research", slug]],
    "script": lambda slug, o: [["script", slug] + (["--restart"] if o.get("restart") else [])],
    "voice": lambda slug, o: [["voice", slug] + (["--backend", o["backend"]] if o.get("backend") else [])
                              + (["--voice", o["voice"]] if o.get("voice") else [])],
    "media": lambda slug, o: [["media", slug]],
    "render": lambda slug, o: [["render", slug] + (["--look", o["look"]] if o.get("look") else [])
                               + (["--preview"] if o.get("preview") else [])],
    "check": lambda slug, o: [["check", slug]],
    "capcut": lambda slug, o: [["capcut", slug]],
}
ORDER = ["research", "script", "voice", "media", "render", "check"]

app = Flask(__name__, static_folder=None)
JOBS: dict[str, dict] = {}   # slug -> job
LOCK = threading.Lock()


# ------------------------------------------------------------------ tiện ích

def _safe_slug(slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-_]{0,80}", slug or ""):
        abort(400, "slug không hợp lệ")
    return slug


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _status(d: Path) -> dict:
    script = _read(d / "script.json")
    ids = [s["id"] for c in (script or {}).get("chapters", []) for s in c["scenes"]]
    timing = _read(d / "timing.json", {}) or {}
    plan = _read(d / "media_plan.json", {}) or {}
    fin = d / "output" / "final.mp4"
    return {
        "research": (d / "research.json").exists(),
        "script": bool(script),
        "voice": bool(ids) and all(i in timing for i in ids),
        "media": bool(ids) and all(i in plan for i in ids),
        "render": fin.exists(),
        "check": (d / "output" / "check_report.md").exists(),
        "capcut": (d / "output" / "capcut_drafts").exists(),
    }


def _summary(d: Path) -> dict:
    meta = _read(d / "project.json", {}) or {}
    script = _read(d / "script.json", {}) or {}
    tl = _read(d / "timeline.json", {}) or {}
    fin = d / "output" / "final.mp4"
    thumb = d / "output" / "thumbnail.jpg"
    job = JOBS.get(d.name)
    return {
        "slug": d.name,
        "title": script.get("title") or d.name.replace("-", " "),
        "preset": meta.get("preset") or "crime_doc",
        "project": meta.get("project", {}),
        "scenes": sum(len(c["scenes"]) for c in script.get("chapters", [])),
        "duration": tl.get("duration", 0),
        "status": _status(d),
        "thumb": f"/files/{d.name}/output/thumbnail.jpg?v={int(thumb.stat().st_mtime)}" if thumb.exists() else "",
        "video": f"/files/{d.name}/output/final.mp4?v={int(fin.stat().st_mtime)}" if fin.exists() else "",
        "updated": max((p.stat().st_mtime for p in [d / "script.json", fin, d / "project.json"] if p.exists()),
                       default=d.stat().st_mtime),
        "running": bool(job and job["running"]),
    }


def _media_url(path: str) -> str:
    return "/media?p=" + _q(path) if path else ""


def _q(s: str) -> str:
    from urllib.parse import quote

    return quote(s, safe="")


# ------------------------------------------------------------------ chạy lệnh nền

def _start_job(slug: str, cmds: list[list[str]], label: str) -> dict:
    with LOCK:
        cur = JOBS.get(slug)
        if cur and cur["running"]:
            abort(409, "Dự án đang chạy một việc khác - chờ xong hoặc bấm Dừng")
        d = PROJECTS / slug
        d.mkdir(parents=True, exist_ok=True)
        log_p = d / ".ui_job.log"
        log_p.write_text("", encoding="utf-8")
        job = {"slug": slug, "label": label, "cmds": cmds, "running": True, "ok": None, "log": str(log_p),
               "started": time.time(), "proc": None, "step": ""}
        JOBS[slug] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return {"label": label, "running": True}


def _run_job(job: dict) -> None:
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    with open(job["log"], "a", encoding="utf-8") as lf:
        for cmd in job["cmds"]:
            job["step"] = cmd[0]
            lf.write(f"\n$ python studio.py {' '.join(cmd)}\n")
            lf.flush()
            try:
                p = subprocess.Popen([sys.executable, "-u", str(ROOT / "studio.py"), *cmd], cwd=ROOT, env=env,
                                     stdout=lf, stderr=subprocess.STDOUT)
            except OSError as e:
                lf.write(f"Lỗi chạy lệnh: {e}\n")
                job.update(running=False, ok=False)
                return
            job["proc"] = p
            rc = p.wait()
            if rc != 0:
                lf.write(f"\n✗ Lệnh dừng với mã lỗi {rc}\n")
                job.update(running=False, ok=False, proc=None)
                return
        lf.write("\n✓ Xong\n")
    job.update(running=False, ok=True, proc=None)


# ------------------------------------------------------------------ trang

@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(STATIC, name)


@app.get("/files/<slug>/<path:rel>")
def project_file(slug, rel):
    d = (PROJECTS / _safe_slug(slug)).resolve()
    p = (d / rel).resolve()
    if not p.is_relative_to(d) or not p.is_file():
        abort(404)
    return send_file(p, conditional=True, as_attachment=request.args.get("dl") == "1")


@app.get("/media")
def media_file():
    p = Path(request.args.get("p", "")).resolve()
    if not (p.is_relative_to(PROJECTS.resolve()) or p.is_relative_to(LIBRARY.resolve())) or not p.is_file():
        abort(404)
    return send_file(p, conditional=True)


# ------------------------------------------------------------------ API

@app.get("/api/presets")
def api_presets():
    import yaml

    out = []
    for name, desc in list_presets().items():
        d = yaml.safe_load((ROOT / "presets" / f"{name}.yaml").read_text("utf-8")) or {}
        out.append({"id": name, "description": desc, "minutes": (d.get("channel") or {}).get("target_minutes"),
                    "look": (d.get("render") or {}).get("look"), "project": d.get("project") or {}})
    return jsonify(out)


@app.get("/api/projects")
def api_projects():
    PROJECTS.mkdir(exist_ok=True)
    items = [_summary(d) for d in PROJECTS.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))]
    items.sort(key=lambda x: -x["updated"])
    return jsonify(items)


@app.post("/api/projects")
def api_create():
    b = request.get_json(force=True) or {}
    topic = (b.get("topic") or "").strip()
    if not topic:
        abort(400, "Cần nhập chủ đề")
    slug = slugify(topic)
    d = PROJECTS / slug
    if (d / "script.json").exists() or (d / "research.json").exists():
        abort(409, f"Đã có dự án '{slug}' - mở dự án đó hoặc đổi tên chủ đề")
    preset = b.get("preset") or "crime_doc"
    pj = {k: b[k] for k in ("audience", "minutes", "language", "country", "currency", "data_date", "story_type",
                            "brand") if b.get(k) not in (None, "")}
    if pj.get("minutes"):
        pj["minutes"] = int(pj["minutes"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps({"preset": preset, "project": pj}, ensure_ascii=False, indent=1),
                                    "utf-8")
    cmds: list[list[str]] = []
    own = (b.get("own_script") or "").strip()
    if own:  # kịch bản có sẵn: JSON (theo mẫu examples/) hoặc văn bản
        if own.startswith("{"):
            f = d / "_ui_script.json"
            try:
                json.loads(own)
            except ValueError as e:
                abort(400, f"JSON kịch bản lỗi: {e}")
            f.write_text(own, "utf-8")
            cmds.append(["script", slug, "--import-json", str(f)])
        else:
            f = d / "_ui_script.txt"
            f.write_text(own, "utf-8")
            cmds.append(["script", slug, "--from-text", str(f), "--title", topic])
        if not (d / "research.json").exists():  # một số bước cần research.json (chỉ chủ đề, không tra cứu)
            (d / "research.json").write_text(json.dumps({"topic": topic, "en_query": b.get("en") or "",
                                                         "years": b.get("years") or "", "sources": []},
                                                        ensure_ascii=False), "utf-8")
    else:
        new = ["--preset", preset, "new", topic]
        for k, flag in (("en", "--en"), ("years", "--years")):
            if b.get(k):
                new += [flag, b[k]]
        urls = [u.strip() for u in (b.get("urls") or "").splitlines() if u.strip()]
        if urls:
            new += ["--url", *urls]
        if b.get("notes"):
            nf = d / "_ui_notes.txt"
            nf.write_text(b["notes"], "utf-8")
            new += ["--notes", str(nf)]
        cmds.append(new)
        if _has_claude():
            cmds.append(["script", slug])
        else:  # không có API key: xuất lời nhắc để dán vào claude.ai, chờ người dùng dán kết quả
            cmds.append(["script", slug, "--manual"])
            meta = _read(d / "project.json", {})
            meta["ui_after_script"] = (b.get("options") or {}) if b.get("run_all") else None
            (d / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
            b["run_all"] = False
    if b.get("run_all"):
        o = b.get("options") or {}
        for st in ("voice", "media", "render", "check"):
            cmds += STEP_CMDS[st](slug, o)
    job = _start_job(slug, cmds, "Tạo video mới")
    return jsonify({"slug": slug, "job": job})


@app.get("/api/projects/<slug>")
def api_project(slug):
    d = PROJECTS / _safe_slug(slug)
    if not d.is_dir():
        abort(404)
    s = _summary(d)
    script = _read(d / "script.json", {}) or {}
    plan = _read(d / "media_plan.json", {}) or {}
    tl = _read(d / "timeline.json", {}) or {}
    times = {it["id"]: [it["start"], it["duration"]] for it in tl.get("items", []) if it.get("id")}
    timing = _read(d / "timing.json", {}) or {}
    chapters = []
    for c in script.get("chapters", []):
        scenes = []
        for sc in c["scenes"]:
            m = [x for x in plan.get(sc["id"], []) if x.get("kind") == "image"]
            v = [x for x in plan.get(sc["id"], []) if x.get("kind") == "video"]
            scenes.append({**sc, "_time": times.get(sc["id"]), "_audio": (timing.get(sc["id"]) or {}).get("duration"),
                           "_thumb": _media_url(m[0]["file"]) if m else "",
                           "_media": [{"url": _media_url(x["file"]), "kind": x["kind"],
                                       "credit": x.get("credit", "")} for x in (m + v)[:6]],
                           "_audio_url": f"/files/{slug}/audio/{sc['id']}.wav"
                           if (d / "audio" / f"{sc['id']}.wav").exists() else ""})
        chapters.append({"title": c.get("title", ""), "scenes": scenes})
    out = {}
    for name, label in (("subtitles.srt", "Phụ đề .srt"), ("thumbnail.jpg", "Thumbnail"),
                        ("youtube_upload.txt", "Tiêu đề + mô tả YouTube"), ("credits.txt", "Nguồn ảnh (credit)"),
                        ("check_report.md", "Báo cáo kiểm tra"), ("preview.mp4", "Bản xem thử")):
        if (d / "output" / name).exists():
            out[name] = {"label": label, "url": f"/files/{slug}/output/{name}"}
    for name, label in (("storyboard.md", "Storyboard .md"), ("storyboard.csv", "Storyboard .csv"),
                        ("script.md", "Kịch bản .md")):
        if (d / name).exists():
            out[name] = {"label": label, "url": f"/files/{slug}/{name}"}
    rep = (d / "output" / "check_report.md")
    yt = (d / "output" / "youtube_upload.txt")
    return jsonify({**s, "has_claude_key": _has_claude(), "meta": _read(d / "project.json", {}), "script_meta": {
        k: v for k, v in script.items() if k != "chapters"}, "chapters": chapters, "outputs": out,
        "report": rep.read_text("utf-8") if rep.exists() else "",
        "youtube": yt.read_text("utf-8") if yt.exists() else ""})


@app.post("/api/projects/<slug>/run")
def api_run(slug):
    slug = _safe_slug(slug)
    b = request.get_json(force=True) or {}
    steps = b.get("steps") or []
    if steps == ["all"]:
        st = _status(PROJECTS / slug)
        steps = [x for x in ORDER if x != "research" or not st["research"]]
        if st["script"]:
            steps = [x for x in steps if x != "script"]
    if "script" in steps and not _has_claude():  # không key: chỉ làm tới bước tư liệu, kịch bản dán từ claude.ai
        if steps != ["script"] and not _status(PROJECTS / slug)["research"]:
            steps = ["research"]
        else:
            abort(400, "Chưa có ANTHROPIC_API_KEY - dùng khung 'Viết kịch bản bằng claude.ai' ngay bên dưới")
    cmds = []
    for st in steps:
        if st not in STEP_CMDS:
            abort(400, f"bước lạ: {st}")
        cmds += STEP_CMDS[st](slug, b.get("options") or {})
    return jsonify(_start_job(slug, cmds, b.get("label") or ", ".join(steps)))


@app.post("/api/projects/<slug>/stop")
def api_stop(slug):
    job = JOBS.get(_safe_slug(slug))
    if job and job.get("proc"):
        job["proc"].terminate()
        job["cmds"] = []
    return jsonify({"ok": True})


@app.get("/api/projects/<slug>/log")
def api_log(slug):
    slug = _safe_slug(slug)
    job = JOBS.get(slug)
    p = Path(job["log"]) if job else PROJECTS / slug / ".ui_job.log"
    off = int(request.args.get("from", 0))
    txt = ""
    if p.exists():
        with open(p, "rb") as f:
            f.seek(off)
            raw = f.read()
        txt = raw.decode("utf-8", "replace")
        off += len(raw)
    return jsonify({"text": txt, "offset": off, "running": bool(job and job["running"]),
                    "ok": job["ok"] if job else None, "label": job["label"] if job else "",
                    "step": job.get("step", "") if job else ""})


SCENE_FIELDS = {"narration", "on_screen_text", "visual_type", "image_prompt_en", "camera", "fx", "mood", "music",
                "hud", "pause_after", "emphasis", "locked", "sound"}
CHAR_FIELDS = {"expression", "pose", "position", "framing", "thought", "shadow", "keywords", "outside", "inside"}


@app.patch("/api/projects/<slug>/scenes/<sid>")
def api_scene(slug, sid):
    from core.scriptgen import save_script
    from core.util import Project

    slug = _safe_slug(slug)
    if not re.fullmatch(r"s\d{3,4}", sid):
        abort(400)
    job = JOBS.get(slug)
    if job and job["running"]:
        abort(409, "Đang chạy việc khác, chờ xong rồi sửa")
    p = Project(slug)
    script = p.read_json("script.json")
    sc = next((s for c in script["chapters"] for s in c["scenes"] if s["id"] == sid), None)
    if not sc:
        abort(404)
    b = request.get_json(force=True) or {}
    need = {"voice": False, "media": False}
    for k, v in b.items():
        if k in SCENE_FIELDS:
            if k == "pause_after":
                v = float(v or 0)
            if sc.get(k) != v:
                if k == "narration":
                    need["voice"] = True
                if k in ("visual_type", "image_prompt_en"):
                    need["media"] = True
                if v in (None, "") and k == "locked":
                    sc.pop(k, None)
                else:
                    sc[k] = v
        elif k == "character" and isinstance(v, dict):
            ch = sc.setdefault("character", {})
            for ck, cv in v.items():
                if ck in CHAR_FIELDS:
                    ch[ck] = cv
    save_script(p, script)
    if need["voice"]:
        p.path("audio", f"{sid}.wav").unlink(missing_ok=True)
        timing = p.read_json("timing.json", {}) or {}
        timing.pop(sid, None)
        p.write_json("timing.json", timing)
    if need["media"] and not sc.get("locked"):
        plan = p.read_json("media_plan.json", {}) or {}
        for m in plan.pop(sid, []):
            if Path(m["file"]).name.startswith(f"ai_{sid}_"):
                Path(m["file"]).unlink(missing_ok=True)
        p.write_json("media_plan.json", plan)
    return jsonify({"ok": True, "need": need})


@app.post("/api/projects/<slug>/scenes/<sid>/rebuild")
def api_scene_rebuild(slug, sid):
    slug = _safe_slug(slug)
    st = _status(PROJECTS / slug)
    cmds = []
    if not st["voice"]:
        cmds.append(["voice", slug])
    if not st["media"]:
        cmds.append(["media", slug, "--only", sid])
    cmds.append(["render", slug])
    return jsonify(_start_job(slug, cmds, f"Dựng lại cảnh {sid}"))


@app.get("/api/projects/<slug>/prompt")
def api_prompt(slug):
    """Lời nhắc viết kịch bản để dán vào claude.ai (không cần API key)."""
    slug = _safe_slug(slug)
    d = PROJECTS / slug
    if not (d / "research.json").exists():
        abort(400, "Chưa có tư liệu - chạy bước 1 (Tư liệu) trước")
    r = subprocess.run([sys.executable, str(ROOT / "studio.py"), "script", slug, "--manual"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    f = d / "prompt_for_claude.txt"
    if r.returncode != 0 or not f.exists():
        abort(500, (r.stdout + r.stderr)[-500:])
    return jsonify({"prompt": f.read_text("utf-8")})


@app.post("/api/projects/<slug>/script-json")
def api_script_json(slug):
    """Nhập kịch bản JSON dán từ claude.ai rồi (tuỳ chọn) chạy tiếp các bước."""
    from core.scriptgen import parse_pasted_json

    slug = _safe_slug(slug)
    d = PROJECTS / slug
    b = request.get_json(force=True) or {}
    try:
        data = parse_pasted_json(b.get("text") or "")
    except ValueError as e:
        abort(400, str(e))
    n = sum(len(c.get("scenes") or []) for c in data["chapters"])
    if not n:
        abort(400, "JSON không có cảnh nào (scenes rỗng)")
    f = d / "_ui_script.json"
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    if not (d / "research.json").exists():
        (d / "research.json").write_text(json.dumps({"topic": data.get("title", slug), "en_query": "", "years": "",
                                                     "sources": []}, ensure_ascii=False), "utf-8")
    cmds = [["script", slug, "--import-json", str(f)]]
    if b.get("run_all"):
        o = b.get("options") or (_read(d / "project.json", {}) or {}).get("ui_after_script") or {}
        for st in ("voice", "media", "render", "check"):
            cmds += STEP_CMDS[st](slug, o)
    job = _start_job(slug, cmds, f"Nhập kịch bản ({len(data['chapters'])} chương, {n} cảnh)")
    return jsonify({"chapters": len(data["chapters"]), "scenes": n, "job": job})


_VER: dict = {"t": 0, "behind": 0}


def _git(*args, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


@app.get("/api/version")
def api_version():
    """Phiên bản đang chạy + có bản mới trên GitHub không (kiểm tra tối đa 10 phút/lần)."""
    if not (ROOT / ".git").exists():
        return jsonify({"git": False})
    try:
        info = _git("log", "-1", "--format=%h|%cd", "--date=format:%d/%m/%Y %H:%M").stdout.strip().split("|")
        if time.time() - _VER["t"] > 600 or request.args.get("force"):
            _git("fetch", "-q", "origin", timeout=30)
            n = _git("rev-list", "--count", "HEAD..@{u}").stdout.strip()
            _VER.update(t=time.time(), behind=int(n or 0))
        return jsonify({"git": True, "commit": info[0], "date": info[1] if len(info) > 1 else "",
                        "behind": _VER["behind"]})
    except (OSError, subprocess.SubprocessError, ValueError):
        return jsonify({"git": True, "commit": "?", "behind": 0})


@app.post("/api/update")
def api_update():
    """Kéo bản mới từ GitHub (git pull) + cài thư viện mới nếu requirements.txt đổi."""
    if not (ROOT / ".git").exists():
        abort(400, "Thư mục này tải bằng ZIP nên không tự cập nhật được - hãy cài lại bằng git clone (xem README)")
    if any(j["running"] for j in JOBS.values()):
        abort(409, "Đang có việc chạy - chờ xong rồi cập nhật")
    before = _git("rev-parse", "HEAD").stdout.strip()
    r = _git("pull", "--ff-only", timeout=120)
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        abort(500, "git pull lỗi: " + out[-600:])
    after = _git("rev-parse", "HEAD").stdout.strip()
    changed = before != after
    if changed and "requirements.txt" in _git("diff", "--name-only", before, after).stdout:
        pr = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
                            cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=1800)
        out += "\n" + (pr.stdout + pr.stderr)[-1500:]
    log = _git("log", "--format=• %s", f"{before}..{after}").stdout if changed else ""
    _VER.update(t=0)
    return jsonify({"changed": changed, "output": out, "log": log})


def _has_claude() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or _env_values().get("ANTHROPIC_API_KEY"))


@app.get("/api/env")
def api_env_get():
    vals = _env_values()
    return jsonify([{"key": k, "desc": d, "where": w, "price": pr, "set": bool(vals.get(k))}
                    for k, d, w, pr in ENV_KEYS])


@app.post("/api/env")
def api_env_set():
    b = request.get_json(force=True) or {}
    allowed = {k for k, *_ in ENV_KEYS}
    vals = _env_values()
    for k, v in b.items():
        if k in allowed and isinstance(v, str):
            v = v.strip()
            if v == "__clear__":
                vals[k] = ""
            elif v:
                vals[k] = v
    lines = ["# Khoá API của Cold Case Studio - file này chỉ nằm trên máy bạn, KHÔNG đẩy lên GitHub"]
    lines += [f"{k}={vals.get(k, '')}" for k, *_ in ENV_KEYS]
    (ROOT / ".env").write_text("\n".join(lines) + "\n", "utf-8")
    for k in allowed:  # để các lệnh chạy sau dùng ngay
        if vals.get(k):
            os.environ[k] = vals[k]
    return jsonify({"ok": True})


def _env_values() -> dict:
    vals = {}
    p = ROOT / ".env"
    if p.exists():
        for ln in p.read_text("utf-8", errors="ignore").splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                vals[k.strip()] = v.strip()
    return vals


def run(host: str = "127.0.0.1", port: int = 7860, open_browser: bool = True) -> None:
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}"
    print(f"\n  Cold Case Studio đang chạy: {url}\n  (Ctrl+C để tắt)\n")
    if open_browser:
        threading.Timer(1.0, lambda: __import__("webbrowser").open(url)).start()
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    run()

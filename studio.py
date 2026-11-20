#!/usr/bin/env python3
"""COLD CASE STUDIO - tool làm video tài liệu vụ án dài ~40 phút.

Quy trình:
  1. research  : thu thập tư liệu (Wikipedia, báo cũ, Internet Archive, URL của bạn)
  2. script    : viết kịch bản bằng Claude (hoặc manual / tự viết)
  3. media     : tìm & tải ảnh, video, tạo ảnh AI theo từng cảnh
  4. voice     : đọc kịch bản bằng TTS (edge / piper / viXTTS / command)
  5. timeline  : dựng timeline + phụ đề + mốc chương YouTube
  6. render    : xuất MP4 hoàn chỉnh bằng ffmpeg
  7. capcut    : xuất draft CapCut để chỉnh tiếp
  all          : chạy từ 1 -> 7

Ví dụ:
  python studio.py new "The Zodiac Killer" --years 1968-1974
  python studio.py all the-zodiac-killer
"""
from __future__ import annotations

import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json  # noqa: E402

from core.util import ROOT, Project, list_presets, apply_project, load_config, log, slugify  # noqa: E402


def cmd_presets(a, cfg):
    for k, v in list_presets().items():
        print(f"  {k:20} {v}")
    print("\nDùng: python studio.py --preset <tên> new \"Chủ đề\"   (project nhớ preset cho các bước sau)")


def cmd_new(a, cfg):
    p = Project(slugify(a.topic))
    from core.research import run_research

    run_research(p, a.topic, cfg, en_query=a.en or "", urls=a.url, notes=a.notes, years=a.years or "",
                 references=a.reference)
    print(f"\nProject: {p.slug}\nTiếp theo: python studio.py script {p.slug}")


def cmd_research(a, cfg):
    from core.research import run_research

    p = Project(a.slug)
    old = p.read_json("research.json", {})
    topic = a.topic or old.get("topic") or a.slug
    run_research(p, topic, cfg, en_query=a.en or old.get("en_query", ""), urls=a.url, notes=a.notes,
                 years=a.years or old.get("years", ""), references=a.reference)


def cmd_script(a, cfg):
    from core import scriptgen

    p = Project(a.slug)
    if a.import_json:
        scriptgen.import_json(p, a.import_json)
    elif a.from_text:
        scriptgen.script_from_text(p, a.from_text, a.title or a.slug, cfg)
    elif a.manual:
        scriptgen.write_manual_prompt(p, cfg)
    else:
        if a.restart:
            for f in ("outline.json", "chapters_partial.json"):
                p.path(f).unlink(missing_ok=True)
        scriptgen.write_script_auto(p, cfg)


def cmd_media(a, cfg):
    from core import media

    p = Project(a.slug)
    if a.import_dir:
        from core.imageprompts import import_dir

        import_dir(p, a.import_dir)
    elif a.add:
        media.add_manual_media(p, a.scene, a.add)
    elif a.url:
        media.download_url_clip(p, a.scene, a.url, a.start or "", a.end or "")
    else:
        if a.no_ai:
            cfg["media"]["ai_images"] = False
        if a.apply:
            media.apply_selection(p, a.apply)
        elif a.review:
            media.review_page(p)
        elif a.ai_only or cfg["media"].get("mode") == "ai_only":
            media.collect_ai_only(p, cfg, set(a.only) if a.only else None)
        else:
            media.collect_media(p, cfg, set(a.only) if a.only else None, candidates=a.candidates)


def cmd_collect(a, cfg):
    from core.library import collect_topic

    if a.sources:
        cfg["media"]["image_sources"] = a.sources
    collect_topic(a.topic, a.query or [], cfg, a.max)


def cmd_library(a, cfg):
    from core.library import LIB, Library, gallery

    lib = Library()
    live = [r for r in lib.items.values() if not r.get("dup_of")]
    if a.search:
        recs = lib.rank(a.search, lib.local_search(a.search, 200), use_clip=a.clip)[:a.n]
        for r in recs:
            print(f"{r['id']}  {r['w']}x{r['h']}  {r['src'][:28]:28}  {r['title'][:80]}")
        gallery(lib, LIB / "search.html", recs=recs)
    elif a.gallery:
        gallery(lib, LIB / "gallery.html")
    else:
        by = {}
        for r in live:
            by[r["src"].split(":")[0]] = by.get(r["src"].split(":")[0], 0) + 1
        print(f"Thư viện: {len(live)} ảnh ({len(lib.items) - len(live)} ảnh trùng đã loại) tại {LIB}")
        for k, v in sorted(by.items(), key=lambda x: -x[1]):
            print(f"  {v:5}  {k}")


def cmd_pack(a, cfg):
    from core.portable import pack

    pack(Project(a.slug), a.with_renders)


def cmd_unpack(a, cfg):
    from core.portable import unpack

    unpack(a.zip)


def cmd_relink(a, cfg):
    from core.portable import relink

    relink(Project(a.slug))


def cmd_scene(a, cfg):
    from core.editor import edit_scene, rebuild_scene

    p = Project(a.slug)
    need = edit_scene(p, a.sid, a)
    if a.rebuild and not a.show:
        rebuild_scene(p, a.sid, cfg, need)


def cmd_check(a, cfg):
    from core.check import run_check
    from core.timeline import build_timeline

    p = Project(a.slug)
    if p.read_json("timing.json"):
        build_timeline(p, cfg)
    run_check(p, cfg)


def cmd_analyze(a, cfg):
    from pathlib import Path

    from core.analyze import analyze, apply_suggestions
    from core.util import ROOT

    out = ROOT / "analysis" / Path(a.video).stem
    rep = analyze(a.video, out, a.minutes)
    if a.apply:
        apply_suggestions(Path(a.config) if a.config else ROOT / "config.yaml", rep)


def cmd_imageprompts(a, cfg):
    from core import imageprompts

    p = Project(a.slug)
    if a.import_txt:
        imageprompts.import_txt(p, a.import_txt)
    elif a.manual:
        imageprompts.manual(p, cfg)
    else:
        imageprompts.generate(p, cfg)


def cmd_voice(a, cfg):
    from core import tts

    if a.backend:
        cfg["voice"]["backend"] = a.backend
    if a.voice:
        cfg["voice"]["edge_voice"] = a.voice
    tts.make_voice(Project(a.slug), cfg, set(a.redo) if a.redo else None)


def cmd_voices(a, cfg):
    from core import tts

    if a.vieneu:
        tts.list_vieneu_voices()
    if a.list:
        tts.list_edge_voices(a.list)
    if a.piper or a.vixtts or a.xtts:
        tts.download_voices(a.piper or "", a.vixtts, a.xtts)


def cmd_timeline(a, cfg):
    from core.timeline import build_timeline

    build_timeline(Project(a.slug), cfg)


def cmd_render(a, cfg):
    from core import render
    from core.timeline import build_timeline

    p = Project(a.slug)
    if a.look:
        cfg["render"]["look"] = a.look
    if a.burn_subs:
        cfg["render"]["burn_subtitles"] = True
    build_timeline(p, cfg)
    render.render_video(p, cfg, workers=a.workers, preview=a.preview)
    render.make_thumbnail(p, cfg)


def cmd_capcut(a, cfg):
    from core.capcut import export_capcut
    from core.timeline import build_timeline

    p = Project(a.slug)
    build_timeline(p, cfg)
    export_capcut(p, cfg, a.drafts_dir or "", a.name or "")


def cmd_all(a, cfg):
    from core import capcut, media, render, scriptgen, tts
    from core.timeline import build_timeline

    p = Project(a.slug)
    if not p.read_json("research.json"):
        raise SystemExit("Chưa có research. Dùng: python studio.py new \"<chủ đề>\"")
    if not p.read_json("script.json"):
        scriptgen.write_script_auto(p, cfg)
    if cfg["media"].get("mode") == "ai_only":
        from core import imageprompts

        from core.scriptgen import llm_backend

        if not p.read_json("image_prompts.json") and llm_backend(cfg) != "none":
            imageprompts.generate(p, cfg)
        media.collect_ai_only(p, cfg)
    else:
        media.collect_media(p, cfg)
    tts.make_voice(p, cfg)
    build_timeline(p, cfg)
    if not a.skip_render:
        render.render_video(p, cfg)
        render.make_thumbnail(p, cfg)
    try:
        from core.check import run_check

        run_check(p, cfg)
    except Exception as e:  # noqa: BLE001
        log(f"  ! kiểm tra lỗi: {e}")
    if not a.skip_capcut:
        try:
            capcut.export_capcut(p, cfg)
        except Exception as e:  # noqa: BLE001
            log(f"  ! CapCut export lỗi: {e}")
    log(f"XONG. Xem thư mục {p.path('output')}")


def cmd_translate(a, cfg):
    import subprocess

    from core.translate import translate_project

    dst = translate_project(a.slug, a.to, cfg)
    if a.all:
        for step in ("voice", "render", "check"):
            r = subprocess.run([sys.executable, str(ROOT / "studio.py"), step, dst.slug], cwd=ROOT)
            if r.returncode:
                raise SystemExit(r.returncode)


def cmd_ui(a, cfg):
    from webui.server import run

    run(a.host, a.port, open_browser=not a.no_browser)


def main():
    ap = argparse.ArgumentParser(description="Cold Case Studio")
    ap.add_argument("--config", default=None)
    ap.add_argument("--preset", default=None,
                    help="phong cách theo ngách: crime_doc | mystery_horror | cartoon_explainer (xem: studio.py presets)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("presets", help="liệt kê phong cách theo ngách")
    s.set_defaults(fn=cmd_presets)

    s = sub.add_parser("new", help="tạo project mới + research")
    s.add_argument("topic")
    s.add_argument("--en", help="từ khoá tiếng Anh (cho báo cũ/Wikipedia EN)")
    s.add_argument("--years", help="khoảng năm, vd 1920-1935")
    s.add_argument("--url", nargs="*", help="link bài báo/tư liệu thêm")
    s.add_argument("--notes", nargs="*", help="file ghi chú .txt/.md")
    s.add_argument("--reference", nargs="*", help="transcript video khác (.txt) - chỉ làm tham khảo sự kiện")
    s.add_argument("--audience", help="đối tượng xem, vd 'người 18-35 tuổi, chưa biết gì về chủ đề'")
    s.add_argument("--minutes", type=float,
                   help="thời lượng mong muốn, từ 0.5 (Shorts) tới 180 phút; số chương và nhịp kể tự chỉnh theo")
    s.add_argument("--aspect", choices=["16:9", "9:16", "1:1", "4:5"], help="khung hình (9:16 = video dọc Shorts/Reels/TikTok)")
    s.add_argument("--language", choices=["vi", "en"])
    s.add_argument("--country", help="(tài chính/nhà ở) quốc gia, vd 'Hoa Kỳ'")
    s.add_argument("--currency", help="(tài chính/nhà ở) đơn vị tiền tệ, vd USD")
    s.add_argument("--data-date", dest="data_date", help="(tài chính/nhà ở) thời điểm dữ liệu, vd 2026-10")
    s.add_argument("--story-type", dest="story_type", choices=["fiction", "legend", "real_event"],
                   help="(bí ẩn/kinh dị) hư cấu | truyền thuyết | sự kiện có thật")
    s.add_argument("--brand", help="tên brand kit trong brand/<tên>.yaml (nhân vật, màu, giọng của kênh)")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("research", help="research lại / bổ sung nguồn")
    s.add_argument("slug")
    s.add_argument("--topic")
    s.add_argument("--en")
    s.add_argument("--years")
    s.add_argument("--url", nargs="*")
    s.add_argument("--notes", nargs="*")
    s.add_argument("--reference", nargs="*")
    s.set_defaults(fn=cmd_research)

    s = sub.add_parser("script", help="viết kịch bản")
    s.add_argument("slug")
    s.add_argument("--manual", action="store_true", help="xuất prompt để dán vào claude.ai")
    s.add_argument("--import-json", help="nhập script JSON (từ claude.ai)")
    s.add_argument("--from-text", help="dùng kịch bản tự viết (.txt)")
    s.add_argument("--title")
    s.add_argument("--restart", action="store_true", help="viết lại từ đầu")
    s.set_defaults(fn=cmd_script)

    s = sub.add_parser("media", help="tìm/tải ảnh & video")
    s.add_argument("slug")
    s.add_argument("--only", nargs="*", help="chỉ làm lại các scene id, vd s003 s010")
    s.add_argument("--no-ai", action="store_true", help="không tạo ảnh AI")
    s.add_argument("--ai-only", action="store_true", help="toàn bộ shot là ảnh AI (dùng image_prompts.json)")
    s.add_argument("--import-dir", help="thư mục ảnh/video bạn tự tạo, tên file s001_1.png, s001_2.png...")
    s.add_argument("--candidates", type=int, default=0, help="lưu N ứng viên/scene + tạo review.html để chọn tay")
    s.add_argument("--review", action="store_true", help="tạo lại review.html")
    s.add_argument("--apply", help="áp dụng selection.json tải từ review.html")
    s.add_argument("--scene", help="scene id để gán file/URL")
    s.add_argument("--add", nargs="*", help="gán file của bạn vào --scene")
    s.add_argument("--url", help="tải đoạn video từ URL (yt-dlp) vào --scene - chỉ video bạn có quyền dùng")
    s.add_argument("--start")
    s.add_argument("--end")
    s.set_defaults(fn=cmd_media)

    s = sub.add_parser("collect", help="cào hàng loạt ảnh theo chủ đề vào thư viện")
    s.add_argument("topic")
    s.add_argument("--query", nargs="*", help="thêm từ khoá, vd \"1890s police\" \"Fall River\"")
    s.add_argument("--max", type=int, default=300)
    s.add_argument("--sources", nargs="*", help="chỉ dùng các nguồn này (xem config media.image_sources)")
    s.set_defaults(fn=cmd_collect)

    s = sub.add_parser("library", help="xem / tìm trong thư viện ảnh")
    s.add_argument("--search")
    s.add_argument("--n", type=int, default=40)
    s.add_argument("--clip", action="store_true", help="xếp hạng bằng AI CLIP")
    s.add_argument("--gallery", action="store_true")
    s.set_defaults(fn=cmd_library)

    s = sub.add_parser("pack", help="đóng gói project + ảnh để chuyển sang máy khác (VPS -> PC)")
    s.add_argument("slug")
    s.add_argument("--with-renders", action="store_true")
    s.set_defaults(fn=cmd_pack)

    s = sub.add_parser("unpack", help="giải nén gói project và sửa đường dẫn")
    s.add_argument("zip")
    s.set_defaults(fn=cmd_unpack)

    s = sub.add_parser("relink", help="sửa đường dẫn file trong project cho khớp máy hiện tại")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_relink)

    s = sub.add_parser("scene", help="sửa / khoá / tạo lại RIÊNG một cảnh")
    s.add_argument("slug")
    s.add_argument("sid", help="mã cảnh, vd s012")
    s.add_argument("--show", action="store_true", help="xem nội dung cảnh")
    s.add_argument("--narration", help="lời đọc mới")
    s.add_argument("--prompt", help="mô tả hình (image_prompt_en) mới")
    s.add_argument("--queries", nargs="*", help="từ khoá tìm ảnh mới")
    s.add_argument("--visual", help="đổi visual_type")
    s.add_argument("--camera", help="push_in | pull_out | pan_lr | pan_rl | hold | ...")
    s.add_argument("--text", help="chữ hiển thị (on_screen_text)")
    for k in ("expression", "pose", "position", "thought", "outside", "inside"):
        s.add_argument(f"--{k}")
    s.add_argument("--keywords", nargs="*")
    s.add_argument("--lock", action="store_true", help="khoá: giữ nguyên ảnh/giọng đã chọn")
    s.add_argument("--unlock", action="store_true")
    s.add_argument("--regen-image", dest="regen_image", action="store_true")
    s.add_argument("--regen-voice", dest="regen_voice", action="store_true")
    s.add_argument("--rebuild", action="store_true", help="làm luôn giọng/ảnh của cảnh + render lại (cache phần khác)")
    s.set_defaults(fn=cmd_scene)

    s = sub.add_parser("check", help="kiểm tra trước khi xuất -> output/check_report.md")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("analyze", help="đo nhịp cắt, chuyển động, màu của 1 video mẫu")
    s.add_argument("video")
    s.add_argument("--minutes", type=float, default=10)
    s.add_argument("--apply", action="store_true", help="ghi số gợi ý vào config.yaml")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("imageprompts", help="tạo prompt ảnh AI cho từng shot (bước prompt 2)")
    s.add_argument("slug")
    s.add_argument("--manual", action="store_true", help="xuất prompt để dán vào chatbot")
    s.add_argument("--import-txt", help="nhập file prompt dạng 's001_1: ...'")
    s.set_defaults(fn=cmd_imageprompts)

    s = sub.add_parser("voice", help="tạo giọng đọc")
    s.add_argument("slug")
    s.add_argument("--backend", choices=["vieneu", "google", "elevenlabs", "edge", "kokoro", "api", "omnivoice", "piper", "xtts", "command"])
    s.add_argument("--voice", help="tên giọng edge, vd en-GB-RyanNeural")
    s.add_argument("--redo", nargs="*", help="đọc lại các scene id")
    s.set_defaults(fn=cmd_voice)

    s = sub.add_parser("voices", help="liệt kê / tải model giọng")
    s.add_argument("--list", nargs="?", const="vi", help="liệt kê giọng edge theo ngôn ngữ (en, vi...)")
    s.add_argument("--piper", help="tải giọng piper, vd en_US-ryan-high")
    s.add_argument("--vixtts", action="store_true", help="tải model viXTTS (clone giọng tiếng Việt)")
    s.add_argument("--xtts", action="store_true", help="tải model XTTS-v2 (clone giọng tiếng Anh)")
    s.add_argument("--vieneu", action="store_true", help="liệt kê giọng VieNeu-TTS tiếng Việt")
    s.set_defaults(fn=cmd_voices)

    s = sub.add_parser("timeline", help="dựng timeline + phụ đề + mốc chương")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_timeline)

    s = sub.add_parser("render", help="xuất MP4 bằng ffmpeg")
    s.add_argument("slug")
    s.add_argument("--preview", action="store_true", help="chỉ render ~12 shot đầu để xem thử")
    s.add_argument("--look", choices=["vintage", "noir", "clean", "dark", "noir_red", "deep_blue", "bright", "collage"])
    s.add_argument("--burn-subs", action="store_true")
    s.add_argument("--workers", type=int, default=0)
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("capcut", help="xuất draft CapCut")
    s.add_argument("slug")
    s.add_argument("--drafts-dir")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_capcut)

    s = sub.add_parser("translate", help="tạo bản ngôn ngữ khác (dịch kịch bản, dùng lại hình) -> <slug>-<lang>")
    s.add_argument("slug")
    s.add_argument("--to", default="en", choices=["en", "vi"])
    s.add_argument("--all", action="store_true", help="dịch xong chạy luôn giọng đọc + dựng video + kiểm tra")
    s.set_defaults(fn=cmd_translate)

    s = sub.add_parser("ui", help="mở giao diện web trên máy (http://127.0.0.1:7860)")
    s.add_argument("--port", type=int, default=7860)
    s.add_argument("--host", default="127.0.0.1", help="0.0.0.0 để máy khác trong mạng LAN mở được")
    s.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    s.set_defaults(fn=cmd_ui)

    s = sub.add_parser("all", help="chạy toàn bộ pipeline")
    s.add_argument("slug")
    s.add_argument("--skip-render", action="store_true")
    s.add_argument("--skip-capcut", action="store_true")
    s.set_defaults(fn=cmd_all)

    a = ap.parse_args()
    preset = getattr(a, "preset", None)
    slug = getattr(a, "slug", None)
    if getattr(a, "cmd", "") == "new":
        slug = slugify(a.topic)
    meta_p = (ROOT / "projects" / slug / "project.json") if slug else None
    if not preset and meta_p and meta_p.exists():
        preset = json.loads(meta_p.read_text("utf-8")).get("preset")
    meta = json.loads(meta_p.read_text("utf-8")) if meta_p and meta_p.exists() else {}
    if getattr(a, "cmd", "") == "new":  # đầu vào của video lưu vào project.json
        meta.setdefault("project", {})
        for k in ("audience", "minutes", "aspect", "country", "currency", "data_date", "story_type", "language", "brand"):
            v = getattr(a, k, None)
            if v not in (None, ""):
                meta["project"][k] = v
    if preset:
        meta["preset"] = preset
    if meta_p and (preset or meta.get("project")):
        meta_p.parent.mkdir(parents=True, exist_ok=True)
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    cfg = load_config(a.config, preset)
    apply_project(cfg, meta.get("project", {}))
    if preset:
        log(f"Preset: {preset}")
    a.fn(a, cfg)


if __name__ == "__main__":
    main()

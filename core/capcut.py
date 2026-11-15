"""Xuất timeline thành DRAFT CapCut (github.com/GuanYixuan/pyCapCut) để mở trong CapCut PC và chỉnh tiếp.

Draft gồm:
  - Track video chính: toàn bộ ảnh/video theo đúng thời gian, ảnh có keyframe Ken Burns (zoom/lia)
  - Track text "labels": chữ địa danh / mốc thời gian
  - Track audio "voice": giọng đọc từng đoạn
  - Track audio "music": nhạc nền
  - Track text "subtitles": phụ đề từ file SRT
  - (tuỳ chọn) filter màu toàn video
LƯU Ý: chạy lệnh này TRÊN MÁY WINDOWS có CapCut, vì draft lưu đường dẫn tuyệt đối tới file media.
"""
from __future__ import annotations

from pathlib import Path

from .render import _music_file, _plate
from .util import ROOT, Project, ffprobe_duration, log, run

US = 1_000_000  # micro giây


def _prepare_video(src: str, dur: float, out_dir: Path, fps: int) -> str:
    """CapCut cần clip nguồn dài >= đoạn trên timeline -> lặp clip nếu ngắn."""
    if ffprobe_duration(src) >= dur + 0.1:
        return src
    out = out_dir / (Path(src).stem + f"_loop{int(dur * 10)}.mp4")
    if not out.exists():
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur + 0.5:.2f}", "-an", "-r", str(fps),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)])
    return str(out)


def _keyframes(seg, KP, motion: str, dur: int, focus, Z: float) -> None:
    """Chuyển các kiểu chuyển động sang keyframe CapCut (scale + vị trí). Đơn vị vị trí = nửa khung hình."""
    fx, fy = focus

    def pos(z: float, cx: float, cy: float) -> tuple[float, float]:
        # đưa điểm (cx,cy) của ảnh về giữa khung, không để lộ viền đen
        lim = z - 1
        x = max(-lim, min(lim, -(cx - 0.5) * 2 * z))
        y = max(-lim, min(lim, (cy - 0.5) * 2 * z))
        return x, y

    def key(t: int, z: float, cx: float, cy: float) -> None:
        x, y = pos(z, cx, cy)
        seg.add_keyframe(KP.uniform_scale, t, z)
        seg.add_keyframe(KP.position_x, t, x)
        seg.add_keyframe(KP.position_y, t, y)

    if motion == "push_in":
        key(0, 1.0, 0.5, 0.5); key(dur, 1 + Z, fx, fy)
    elif motion == "pull_out":
        key(0, 1 + Z, fx, fy); key(dur, 1.0, 0.5, 0.5)
    elif motion in ("pan_lr", "pan_rl"):
        z = 1 + Z * 1.1
        a, b = (0.0, 1.0) if motion == "pan_lr" else (1.0, 0.0)
        key(0, z, a, fy); key(dur, z, b, fy)
    elif motion in ("tilt_down", "tilt_up"):
        z = 1 + Z * 1.2
        a, b = (0.0, 1.0) if motion == "tilt_down" else (1.0, 0.0)
        key(0, z, fx, a); key(dur, z, fx, b)
    elif motion == "snap_zoom":
        key(0, 1.0, 0.5, 0.5); key(dur // 4, 1 + Z * 1.8, fx, fy); key(dur, 1 + Z * 2.0, fx, fy)
    elif motion == "punch":
        key(0, 1.04, fx, fy); key(dur, 1.04 + Z * 0.5, fx, fy)
    elif motion == "float":
        key(0, 1.06, 0.47, 0.53); key(dur, 1.06 + Z * 0.4, 0.53, 0.47)
    else:  # shake và mặc định: zoom nhẹ
        key(0, 1.08, 0.5, 0.5); key(dur, 1.12, 0.5, 0.5)


def export_capcut(project: Project, cfg: dict, drafts_dir: str = "", name: str = "") -> Path:
    import pycapcut as cc
    from pycapcut import KeyframeProperty as KP

    tl = project.read_json("timeline.json")
    if not tl:
        raise SystemExit("Chưa có timeline.json (chạy lệnh timeline/voice trước).")
    capcfg = cfg.get("capcut", {})
    ddir = Path(drafts_dir or capcfg.get("drafts_dir", ""))
    if not ddir.exists() or "<TEN_USER>" in str(ddir):
        ddir = project.path("output", "capcut_drafts")
        ddir.mkdir(parents=True, exist_ok=True)
        log(f"  ! Không thấy thư mục draft CapCut -> lưu tạm vào {ddir}. Sửa capcut.drafts_dir trong config.yaml.")
    name = name or f"{project.slug}"
    folder = cc.DraftFolder(str(ddir))
    W, H, fps = tl["width"], tl["height"], tl["fps"]
    script = folder.create_draft(name, W, H, fps, allow_replace=True)

    script.add_track(cc.TrackType.video)
    script.add_track(cc.TrackType.audio, "voice")
    script.add_track(cc.TrackType.audio, "music")
    script.add_track(cc.TrackType.text, "labels")
    script.add_track(cc.TrackType.text, "names")

    prep = project.path("media", "capcut")
    prep.mkdir(exist_ok=True)
    zoom_mult = float(capcfg.get("zoom_multiplier", 1.0))

    # Video track liên tục: tính micro giây theo mốc tuyệt đối để không có khe hở
    shots = [sh for it in tl["items"] for sh in it["shots"]]
    for i, sh in enumerate(shots):
        start = round(sh["start"] * US)
        end = round((sh["start"] + sh["duration"]) * US)
        dur = end - start
        tr = cc.Timerange(start, dur)
        if sh["kind"] == "image":
            plate, focus = _plate(sh, prep, W, H, cfg["render"].get("look") == "vintage")
            seg = cc.VideoSegment(str(plate), tr)
            _keyframes(seg, KP, sh.get("motion", "push_in"), dur, focus, sh.get("zoom", 0.14) * zoom_mult)
        else:
            src = _prepare_video(sh["file"], dur / US, prep, fps)
            seg = cc.VideoSegment(src, tr, source_timerange=cc.Timerange(0, dur), volume=0.0)
        script.add_segment(seg)

    # Giọng đọc + nhãn chữ
    for it in tl["items"]:
        if it["type"] != "scene":
            continue
        a_start = round(it["start"] * US)
        a_dur = int(min(ffprobe_duration(it["audio"]), it["audio_dur"]) * US) - 1000
        script.add_segment(cc.AudioSegment(it["audio"], cc.Timerange(a_start, a_dur)), "voice")
        nc = it["shots"][0].get("namecard") if it["shots"] else None
        if nc and nc[0]:
            script.add_segment(cc.TextSegment(
                f"{nc[0]}\n{nc[1]}", cc.Timerange(a_start, int(min(4.5, it["shots"][0]["duration"]) * US)),
                style=cc.TextStyle(size=9.0, bold=True, color=(0.95, 0.95, 0.95)),
                clip_settings=cc.ClipSettings(transform_x=-0.55, transform_y=-0.62)), "names")
        if it.get("label"):
            ldur = int(min(5.0, it["duration"] - 0.2) * US)
            script.add_segment(cc.TextSegment(
                it["label"], cc.Timerange(a_start, ldur),
                style=cc.TextStyle(size=6.0, color=(0.93, 0.9, 0.85)),
                background=cc.TextBackground(color="#0A0A0A", alpha=0.7),
                clip_settings=cc.ClipSettings(transform_x=-0.62, transform_y=-0.72)), "labels")

    # Nhạc nền lặp lại
    music = _music_file()
    total = round(tl["duration"] * US)
    if music:
        mlen = int(ffprobe_duration(music) * US) - 10_000
        t = 0
        vol = cfg["render"].get("music_volume", 0.1)
        while t < total and mlen > US:
            d = min(mlen, total - t)
            script.add_segment(cc.AudioSegment(str(music), cc.Timerange(t, d), volume=vol), "music")
            t += d

    # Phụ đề
    srt = project.path("output", "subtitles.srt")
    if srt.exists():
        script.import_srt(str(srt), track_name="subtitles",
                          text_style=cc.TextStyle(size=5.0, align=1, auto_wrapping=True),
                          clip_settings=cc.ClipSettings(transform_y=-0.82))

    # Filter tuỳ chọn
    fname = capcfg.get("filter", "")
    if fname:
        try:
            script.add_track(cc.TrackType.filter)
            script.add_filter(getattr(cc.FilterType, fname), cc.Timerange(0, total))
        except Exception as e:  # noqa: BLE001
            log(f"  ! Không thêm được filter {fname}: {e}")

    script.save()
    out = ddir / name
    log(f"✓ Draft CapCut: {out}\n  Mở CapCut PC -> draft '{name}' sẽ xuất hiện trong danh sách dự án -> chỉnh & Export.")
    return out

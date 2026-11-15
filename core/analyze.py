"""Phân tích phong cách dựng của 1 video mẫu (vd video đối thủ bạn đã tải về máy) để bắt chước NHỊP & CHUYỂN ĐỘNG.

  python studio.py analyze doi_thu.mp4 [--minutes 10]

Đo được:
  - Nhịp cắt cảnh: độ dài shot trung bình / trung vị, số shot mỗi phút
  - Chuyển động trong từng shot: zoom vào / zoom ra / lia ngang / lia dọc / đứng yên, mức zoom trung bình
  - Màu: độ bão hoà, độ sáng -> gợi ý look (noir / vintage / clean)
Xuất: output/analysis.txt, analysis.json, contact sheet keyframe (xem bố cục, khung ảnh, chữ của họ)
và đoạn cấu hình gợi ý để dán vào config.yaml.
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from .util import ffprobe_duration, log


def detect_cuts(video: str, max_sec: float, fps: int = 4) -> list[float]:
    """Phát hiện cả cắt cứng lẫn chuyển cảnh mờ (fade/dissolve): so sánh frame cách nhau 0.5s."""
    w, h = 160, 90
    res = subprocess.run(["ffmpeg", "-v", "error", "-t", str(max_sec), "-i", video, "-an", "-vf",
                          f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True)
    n = len(res.stdout) // (w * h)
    if n < 3:
        return []
    fr = np.frombuffer(res.stdout[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32)
    gap = max(1, fps // 2)
    d = np.zeros(n)
    for i in range(gap, n):
        a, b = fr[i - gap], fr[i]
        # so sánh cả cấu trúc (lệch trung bình) và histogram để bỏ qua zoom chậm
        ha = np.histogram(a, 32, (0, 255))[0]
        hb = np.histogram(b, 32, (0, 255))[0]
        d[i] = 0.5 * float(np.abs(a - b).mean()) + 0.5 * float(np.abs(ha - hb).sum()) / (w * h) * 50
    base = float(np.median(d[gap:])) if n > gap else 0
    thr = base * 2.5 + 4
    cuts, last = [], -10.0
    for i in range(gap + 1, n - 1):
        if d[i] > thr and d[i] >= d[i - 1] and d[i] >= d[i + 1]:
            t = (i - gap / 2) / fps
            if t - last >= 1.0:
                cuts.append(t)
                last = t
    return cuts


def grab(video: str, t: float, w: int = 320) -> np.ndarray | None:
    res = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                          f"scale={w}:-2,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    if not res.stdout:
        return None
    h = len(res.stdout) // w
    return np.frombuffer(res.stdout[: h * w], dtype=np.uint8).reshape(h, w).astype(np.float32)


def _crop_scale(img: np.ndarray, s: float, dx: float, dy: float) -> np.ndarray:
    """Crop vùng 1/s quanh tâm lệch (dx,dy) rồi phóng lại kích thước gốc."""
    h, w = img.shape
    cw, ch = w / s, h / s
    x0 = (w - cw) / 2 + dx * (w - cw) / 2
    y0 = (h - ch) / 2 + dy * (h - ch) / 2
    im = Image.fromarray(img.astype(np.uint8)).crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32)


def estimate_motion(a: np.ndarray, b: np.ndarray) -> tuple[str, float]:
    """So sánh frame đầu (a) và cuối (b) của 1 shot -> loại chuyển động + mức zoom."""
    if a.shape != b.shape:
        return "unknown", 0.0
    if float(np.abs(a - b).mean()) < 1.5:
        return "static", 0.0
    best = (1e9, 1.0, 0.0, 0.0, "in")
    for s in (1.0, 1.04, 1.08, 1.12, 1.17, 1.23, 1.3, 1.4):
        for dx in (-0.8, -0.4, 0, 0.4, 0.8):
            for dy in (-0.6, 0, 0.6):
                if s == 1.0 and (dx or dy):
                    continue
                e_in = float(np.abs(_crop_scale(a, s, dx, dy) - b).mean())   # b là phần phóng to của a
                e_out = float(np.abs(_crop_scale(b, s, dx, dy) - a).mean())  # a là phần phóng to của b
                if e_in < best[0]:
                    best = (e_in, s, dx, dy, "in")
                if e_out < best[0]:
                    best = (e_out, s, dx, dy, "out")
    # thử lia: dịch ngang/dọc ở cùng tỉ lệ
    h, w = a.shape
    pan_best = (1e9, 0, 0)
    for sx in range(-int(w * 0.2), int(w * 0.2) + 1, max(1, int(w * 0.02))):
        for sy in range(-int(h * 0.15), int(h * 0.15) + 1, max(1, int(h * 0.03))):
            if not sx and not sy:
                continue
            aa = a[max(0, sy):h + min(0, sy), max(0, sx):w + min(0, sx)]
            bb = b[max(0, -sy):h + min(0, -sy), max(0, -sx):w + min(0, -sx)]
            e = float(np.abs(aa - bb).mean())
            if e < pan_best[0]:
                pan_best = (e, sx, sy)
    err, s, dx, dy, d = best
    if pan_best[0] < err * 0.85 and (abs(pan_best[1]) > w * 0.03 or abs(pan_best[2]) > h * 0.03):
        return ("pan" if abs(pan_best[1]) >= abs(pan_best[2]) else "tilt"), 0.0
    if err > 40:
        return "video/complex", 0.0
    if s <= 1.02:
        return "static", 0.0
    return ("zoom_in" if d == "in" else "zoom_out"), s - 1


def analyze(video: str, out_dir: Path, minutes: float = 10, ) -> dict:
    dur = min(ffprobe_duration(video), minutes * 60)
    log(f"Phân tích {video} ({dur / 60:.1f} phút đầu)...")
    cuts = detect_cuts(video, dur)
    bounds = [0.0] + cuts + [dur]
    shots = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] - bounds[i] > 0.4]
    lens = [b - a for a, b in shots]
    log(f"  {len(shots)} shot, đo chuyển động...")
    motions, zooms, thumbs = [], [], []
    for a, b in shots:
        if b - a < 1.2:
            motions.append("quick")
            continue
        f0, f1 = grab(video, a + 0.25), grab(video, b - 0.25)
        if f0 is None or f1 is None:
            continue
        m, z = estimate_motion(f0, f1)
        motions.append(m)
        if z:
            zooms.append(z)
    for a, b in shots[:48]:
        res = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{(a + b) / 2:.2f}", "-i", video, "-frames:v", "1",
                              "-vf", "scale=320:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if res.stdout:
            import io

            thumbs.append(Image.open(io.BytesIO(res.stdout)).convert("RGB"))
    # màu
    st = subprocess.run(["ffmpeg", "-hide_banner", "-t", str(dur), "-i", video, "-an", "-vf",
                         "fps=1/5,scale=320:-2,signalstats,metadata=print", "-f", "null", "-"],
                        capture_output=True, text=True, encoding="utf-8", errors="ignore").stderr
    sat = [float(x) for x in re.findall(r"SATAVG=([\d.]+)", st)]
    yav = [float(x) for x in re.findall(r"YAVG=([\d.]+)", st)]
    sat_avg = statistics.mean(sat) if sat else 0
    y_avg = statistics.mean(yav) if yav else 0

    counts: dict[str, int] = {}
    for m in motions:
        counts[m] = counts.get(m, 0) + 1
    total = max(1, len(motions))
    med = statistics.median(lens) if lens else 0
    report = {
        "video": video, "analyzed_seconds": round(dur, 1), "shots": len(shots),
        "avg_shot_sec": round(statistics.mean(lens), 2) if lens else 0, "median_shot_sec": round(med, 2),
        "cuts_per_minute": round(len(shots) / (dur / 60), 1) if dur else 0,
        "motion_share": {k: round(v / total, 2) for k, v in sorted(counts.items(), key=lambda x: -x[1])},
        "avg_zoom_amount": round(statistics.mean(zooms), 3) if zooms else 0,
        "saturation_avg": round(sat_avg, 1), "brightness_avg": round(y_avg, 1),
    }
    look = "noir" if sat_avg < 3.5 else "vintage" if sat_avg < 35 else "clean"
    still = counts.get("static", 0) / total
    sugg = {
        "media.shot_seconds": round(max(2.5, min(12, med or 6)), 1),
        "edit.zoom": round(min(0.3, max(0.06, report["avg_zoom_amount"] or 0.12)), 2),
        "render.look": look,
        "media.video_ratio": round(min(0.8, counts.get("video/complex", 0) / total + 0.05), 2),
    }
    report["suggested_config"] = sugg
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), "utf-8")
    lines = [
        f"VIDEO: {video}", f"Đã phân tích: {dur / 60:.1f} phút, {len(shots)} shot",
        f"Độ dài shot: trung bình {report['avg_shot_sec']}s, trung vị {report['median_shot_sec']}s "
        f"({report['cuts_per_minute']} lần cắt/phút)",
        "Chuyển động: " + ", ".join(f"{k} {int(v * 100)}%" for k, v in report["motion_share"].items()),
        f"Mức zoom trung bình mỗi shot: {report['avg_zoom_amount'] * 100:.0f}%",
        f"Màu: bão hoà {sat_avg:.0f} (0 = đen trắng), độ sáng {y_avg:.0f}/255 -> look gợi ý: {look}",
        f"Tỉ lệ shot đứng yên: {still * 100:.0f}%",
        "", "GỢI Ý cho config.yaml:",
    ] + [f"  {k}: {v}" for k, v in sugg.items()]
    (out_dir / "analysis.txt").write_text("\n".join(lines), "utf-8")
    if thumbs:
        W, H = thumbs[0].size
        cols = 6
        sheet = Image.new("RGB", (W * cols, H * ((len(thumbs) + cols - 1) // cols)))
        for i, t in enumerate(thumbs):
            sheet.paste(t.resize((W, H)), ((i % cols) * W, (i // cols) * H))
        sheet.save(out_dir / "keyframes.jpg", quality=85)
    print("\n".join(lines))
    log(f"✓ Báo cáo: {out_dir / 'analysis.txt'} | keyframe: {out_dir / 'keyframes.jpg'}")
    return report


def apply_suggestions(cfg_path: Path, report: dict) -> None:
    """Ghi các con số gợi ý vào config.yaml (giữ nguyên chú thích)."""
    text = cfg_path.read_text("utf-8")
    for dotted, val in report["suggested_config"].items():
        key = dotted.split(".")[-1]
        v = f'"{val}"' if isinstance(val, str) else str(val)
        text = re.sub(rf"^(\s+{key}:\s*)([^#\n]*?)(\s*#.*)?$", lambda m: f"{m.group(1)}{v}{m.group(3) or ''}",
                      text, count=1, flags=re.M)
    cfg_path.write_text(text, "utf-8")
    log(f"✓ Đã cập nhật {cfg_path}")

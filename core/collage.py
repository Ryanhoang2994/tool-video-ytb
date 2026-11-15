"""Kiểu "cắt dán tư liệu" (collage documentary): nền giấy cũ + bản đồ, ảnh tư liệu cắt dán viền trắng + viền đỏ,
số lớn trên giấy đỏ xé (đếm lên), dải giấy ghi ngày/địa điểm gạch chân đỏ, ghim và chỉ đỏ nối các mảnh.
Mỗi mảnh là 1 lớp riêng -> lúc dựng lần lượt "bật" ra (phóng to có nảy), nền trôi chậm.

Bật bằng: render.look: "collage"  (preset crime_doc / ocean... hoặc --look collage)
Cảnh có thể thêm "stat": {"value": 75, "label": "NGƯỜI ĐƯỢC CỨU", "unit": ""} -> con số lớn trên giấy đỏ.
Có cài `rembg` (pip install rembg) thì ảnh người được tách nền thành hình cắt dán đúng dáng người.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

PAPER = (231, 222, 199)
RED = (200, 36, 36)
INK = (25, 22, 20)


def _noise(w: int, h: int, seed: int, scale: int = 4) -> Image.Image:
    rng = np.random.default_rng(seed)
    a = rng.normal(0, 1, (h // scale + 1, w // scale + 1)).astype(np.float32)
    im = Image.fromarray(((a - a.min()) / (a.max() - a.min() + 1e-6) * 255).astype(np.uint8))
    return im.resize((w, h), Image.BICUBIC)


def paper_bg(W: int, H: int, seed: int = 0) -> Image.Image:
    """Giấy cũ + lưới mờ + mẩu bản đồ/báo xé + băng dính."""
    rnd = random.Random(seed)
    base = Image.new("RGB", (W, H), PAPER)
    n = _noise(W, H, seed, 3).filter(ImageFilter.GaussianBlur(1))
    base = Image.blend(base, ImageOps.colorize(n, (205, 192, 165), (240, 233, 214)), 0.55)
    d = ImageDraw.Draw(base, "RGBA")
    step = int(H / 18)
    for x in range(0, W, step):  # lưới kẻ mờ
        d.line([(x, 0), (x, H)], fill=(150, 140, 120, 28), width=2)
    for y in range(0, H, step):
        d.line([(0, y), (W, y)], fill=(150, 140, 120, 28), width=2)
    for _ in range(rnd.randint(2, 3)):  # mẩu bản đồ xé (đường đồng mức)
        mw, mh = int(W * rnd.uniform(0.25, 0.4)), int(H * rnd.uniform(0.3, 0.5))
        scrap = Image.new("RGBA", (mw, mh), (206, 210, 190, 255))
        sd = ImageDraw.Draw(scrap)
        cx, cy = rnd.uniform(0.2, 0.8) * mw, rnd.uniform(0.2, 0.8) * mh
        for r in range(20, int(max(mw, mh)), 26):
            pts = [(cx + (r + 10 * math.sin(a * 3 + r)) * math.cos(a), cy + (r * 0.7 + 8 * math.cos(a * 2)) * math.sin(a))
                   for a in np.linspace(0, 2 * math.pi, 60)]
            sd.line(pts, fill=(130, 120, 92, 150), width=3)
        scrap = _torn(scrap, rnd.randint(0, 999))
        base.paste(scrap, (rnd.randint(-mw // 4, W - mw * 3 // 4), rnd.randint(-mh // 4, H - mh * 3 // 4)), scrap)
    for _ in range(rnd.randint(1, 2)):  # mẩu báo
        nw, nh = int(W * rnd.uniform(0.12, 0.2)), int(H * rnd.uniform(0.25, 0.4))
        news = Image.new("RGBA", (nw, nh), (226, 220, 204, 255))
        nd = ImageDraw.Draw(news)
        y = 14
        while y < nh - 10:
            nd.rectangle([10, y, nw - 10 - rnd.randint(0, nw // 3), y + 6], fill=(120, 112, 100, 150))
            y += 14
        news = _torn(news, rnd.randint(0, 999)).rotate(rnd.uniform(-8, 8), expand=True)
        base.paste(news, (rnd.choice([rnd.randint(0, W // 8), rnd.randint(W * 7 // 8 - nw, W - nw // 2)]),
                          rnd.randint(0, H - nh // 2)), news)
    v = Image.new("L", (W, H), 0)
    ImageDraw.Draw(v).ellipse([-W * 0.2, -H * 0.2, W * 1.2, H * 1.2], fill=255)
    v = v.filter(ImageFilter.GaussianBlur(W // 10))
    base = Image.composite(base, ImageEnhance.Brightness(base).enhance(0.72), v)
    return base


def _torn(img: Image.Image, seed: int, depth: int = 10) -> Image.Image:
    """Mép giấy xé răng cưa."""
    rnd = random.Random(seed)
    w, h = img.size
    m = Image.new("L", (w, h), 0)
    pts = []
    for x in range(0, w + 1, 12):
        pts.append((x, rnd.randint(0, depth)))
    for y in range(0, h + 1, 12):
        pts.append((w - rnd.randint(0, depth), y))
    for x in range(w, -1, -12):
        pts.append((x, h - rnd.randint(0, depth)))
    for y in range(h, -1, -12):
        pts.append((rnd.randint(0, depth), y))
    ImageDraw.Draw(m).polygon(pts, fill=255)
    out = img.convert("RGBA")
    out.putalpha(Image.fromarray(np.minimum(np.asarray(m), np.asarray(out.split()[3]))))
    return out


def _halftone(gray: Image.Image, cell: int = 6) -> Image.Image:
    """Lớp chấm in báo nhẹ để ảnh trông như cắt từ báo."""
    w, h = gray.size
    small = gray.resize((max(1, w // cell), max(1, h // cell)))
    dots = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(dots)
    px = small.load()
    for j in range(small.height):
        for i in range(small.width):
            r = (1 - px[i, j] / 255) * cell * 0.62
            if r > 0.4:
                cx, cy = i * cell + cell / 2, j * cell + cell / 2
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    return Image.blend(gray, dots, 0.28)


def _cutout_mask(img: Image.Image) -> Image.Image | None:
    try:
        from rembg import remove  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        return remove(img.convert("RGB")).split()[3]
    except Exception:  # noqa: BLE001
        return None


def sticker(src: Path, max_w: int, max_h: int, seed: int = 0, cutout: bool = True, color: bool = False) -> Image.Image:
    """Ảnh -> miếng dán: đen trắng chấm in, viền trắng + viền đỏ, đổ bóng, hơi xoay."""
    rnd = random.Random(seed)
    with Image.open(src) as im:
        im = im.convert("RGB")
    im = ImageOps.contain(im, (max_w, max_h), Image.LANCZOS)  # phóng/thu cho vừa khung dán
    g = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(1.15)
    photo = (im if color else _halftone(g).convert("RGB")).convert("RGBA")
    mask = _cutout_mask(im) if cutout else None
    if mask is not None and np.asarray(mask).mean() > 12:  # tách nền thành công -> viền theo dáng
        photo.putalpha(mask.point(lambda v: 255 if v > 110 else 0))
    pad = 44
    canvas = Image.new("RGBA", (photo.width + pad * 2, photo.height + pad * 2), (0, 0, 0, 0))
    canvas.alpha_composite(photo, (pad, pad))
    al = canvas.split()[3]
    white = al.filter(ImageFilter.MaxFilter(23))
    red = white.filter(ImageFilter.MaxFilter(13))
    out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", canvas.size, RED + (255,)), (0, 0), red)
    out.paste(Image.new("RGBA", canvas.size, (250, 248, 242, 255)), (0, 0), white)
    out.alpha_composite(canvas)
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    sh.putalpha(red.point(lambda v: int(v * 0.45)).filter(ImageFilter.GaussianBlur(10)))
    full = Image.new("RGBA", (out.width + 24, out.height + 24), (0, 0, 0, 0))
    full.alpha_composite(sh, (16, 18))
    full.alpha_composite(out, (0, 0))
    if rnd.random() < 0.7:  # băng dính
        tape = Image.new("RGBA", (int(full.width * 0.28), 46), (236, 226, 190, 175))
        tape = tape.rotate(rnd.uniform(-25, 25), expand=True)
        full.alpha_composite(tape, (int(full.width * rnd.uniform(0.1, 0.6)), 0))
    return full.rotate(rnd.uniform(-4, 4), expand=True, resample=Image.BICUBIC)


def stat_card(value: str, label: str, size: int) -> Image.Image:
    """Con số lớn trên giấy đỏ xé + nhãn nhỏ."""
    from .graphics import title_font

    f = title_font(int(size * 0.62))
    fl = title_font(int(size * 0.11))
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    tw = int(max(tmp.textlength(value, font=f), size * 0.7))
    w, h = tw + int(size * 0.3), int(size * 0.95)
    card = Image.new("RGBA", (w, h), RED + (255,))
    d = ImageDraw.Draw(card)
    d.text(((w - tmp.textlength(value, font=f)) / 2, h * 0.02), value, font=f, fill=(24, 18, 18))
    if label:
        lw = tmp.textlength(label.upper(), font=fl) + 30
        d.rectangle([(w - lw) / 2, h * 0.78, (w + lw) / 2, h * 0.78 + fl.size * 1.35], fill=(236, 228, 210))
        d.text(((w - lw) / 2 + 15, h * 0.78 + fl.size * 0.12), label.upper(), font=fl, fill=INK)
    card = _torn(card, len(value) * 7, depth=14)
    out = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    sh.putalpha(card.split()[3].point(lambda v: int(v * 0.4)))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (12, 14))
    out.alpha_composite(card, (0, 0))
    return out.rotate(random.Random(value).uniform(-3, 3), expand=True, resample=Image.BICUBIC)


def label_strip(text: str, size: int) -> Image.Image:
    """Dải giấy ghi ngày / địa điểm, chữ máy đánh chữ, gạch chân đỏ."""
    from .graphics import _font
    from .util import find_mono_font

    fp = find_mono_font()
    if fp:
        f = _font(fp, size)
    else:
        from .graphics import title_font

        f = title_font(size)
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    tw = int(tmp.textlength(text, font=f))
    w, h = tw + size * 2, int(size * 2.1)
    strip = Image.new("RGBA", (w, h), (238, 232, 216, 255))
    d = ImageDraw.Draw(strip)
    d.text((size, size * 0.35), text, font=f, fill=INK)
    d.line([(size, size * 1.6), (size + tw, size * 1.68)], fill=RED, width=max(4, size // 7))
    strip = _torn(strip, len(text), depth=8)
    return strip.rotate(random.Random(text).uniform(-2.5, 2.5), expand=True, resample=Image.BICUBIC)


def pin(size: int) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([size * 0.38, size * 0.55, size * 0.62, size * 0.7], fill=(0, 0, 0, 80))
    d.ellipse([size * 0.2, size * 0.1, size * 0.8, size * 0.7], fill=RED, outline=(120, 10, 10), width=3)
    d.ellipse([size * 0.32, size * 0.2, size * 0.48, size * 0.36], fill=(255, 140, 140))
    return im


def count_frames(value: float, label: str, unit: str, size: int, folder: Path, fps: int, sep: str = ".") -> tuple[str, int, int, int]:
    """Chuỗi PNG số đếm lên trên giấy đỏ (kích thước cố định theo giá trị cuối)."""
    folder.mkdir(parents=True, exist_ok=True)
    n = int(fps * 0.9)
    final = stat_card(_fmtv(value, unit, sep), label, size)
    W0, H0 = final.size
    if not (folder / f"f_{n:04d}.png").exists():
        for i in range(n + 1):
            k = 1 - (1 - i / n) ** 3
            v = value * k
            card = stat_card(_fmtv(v, unit, sep, ref=value), label, size)
            c = Image.new("RGBA", (W0, H0), (0, 0, 0, 0))
            c.alpha_composite(card.crop((0, 0, min(W0, card.width), min(H0, card.height))),
                              ((W0 - min(W0, card.width)) // 2, 0))
            c.save(folder / f"f_{i:04d}.png")
    return str(folder / "f_%04d.png"), n + 1, W0, H0


def _fmtv(v: float, unit: str, sep: str, ref: float | None = None) -> str:
    ref = v if ref is None else ref
    if abs(ref) >= 1000:
        s = f"{int(round(v)):,}".replace(",", sep)
    elif ref != int(ref):
        s = f"{v:.1f}".replace(".", "," if sep == "." else ".")
    else:
        s = str(int(round(v)))
    return s + (unit or "")


def compose(files: list[str], outbase: Path, W: int, H: int, seed: int = 0, label: str = "",
            stat: dict | None = None, fps: int = 30, color: bool = False) -> dict:
    """1 cảnh cắt dán: nền giấy (1.5x) + các lớp (toạ độ khung W x H).
    Lớp: photo (bật ra), pin, string (chỉ đỏ), stat (số đếm lên), label (dải giấy trượt vào)."""
    rnd = random.Random(seed)
    W2, H2 = int(W * 1.5), int(H * 1.5)
    bg_p = outbase.with_name(outbase.stem + "_bg.jpg")
    if not bg_p.exists():
        paper_bg(W2, H2, seed).save(bg_p, quality=90)
    layers: list[dict] = []

    def save(kind: str, im: Image.Image, x: int, y: int, t0: float, **kw):
        p = outbase.with_name(f"{outbase.stem}_{kind}{len(layers)}.png")
        im.save(p)
        layers.append({"kind": kind, "file": str(p), "x": int(x), "y": int(y), "w": im.width, "h": im.height,
                       "t0": t0, **kw})

    has_stat = bool(stat and stat.get("value") not in (None, ""))
    n = max(1, min(3, len(files)))
    photo_area_w = W * (0.55 if has_stat else 0.8)
    anchors = []
    for i, f in enumerate(files[:n]):
        mw = int(photo_area_w / n * (1.15 if n > 1 else 1))
        mh = int(H * (0.72 if n == 1 else 0.6))
        try:
            st = sticker(Path(f), mw, mh, seed + i, cutout=True, color=color)
        except Exception:  # noqa: BLE001
            continue
        cx = (W * 0.08 + photo_area_w * (i + 0.5) / n) if has_stat else W * (0.5 + (i - (n - 1) / 2) * 0.8 / n)
        cy = H * (0.52 + rnd.uniform(-0.05, 0.05))
        x, y = int(cx - st.width / 2), int(cy - st.height / 2)
        save("pop", st, x, y, 0.15 + 0.35 * i)
        anchors.append((x + st.width * rnd.uniform(0.35, 0.65), y + 26))
        pn = pin(56)
        save("pop", pn, anchors[-1][0] - 28, anchors[-1][1] - 30, 0.35 + 0.35 * i)
    if has_stat:
        try:
            val = float(str(stat["value"]).replace(",", "."))
        except ValueError:
            val = None
        size = int(H * 0.36)
        sx, sy = int(W * 0.7), int(H * 0.48)
        if val is not None:
            folder = outbase.with_name(outbase.stem + "_count")
            pat, nfr, w0, h0 = count_frames(val, stat.get("label", ""), stat.get("unit", ""), size, folder, fps)
            layers.append({"kind": "count", "file": pat, "frames": nfr, "x": sx - w0 // 2, "y": sy - h0 // 2,
                           "w": w0, "h": h0, "t0": 0.55})
        else:
            sc = stat_card(str(stat["value"]), stat.get("label", ""), size)
            save("pop", sc, sx - sc.width // 2, sy - sc.height // 2, 0.55)
        if anchors:  # chỉ đỏ từ ghim ảnh tới con số
            ln = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ln)
            ax, ay = anchors[0]
            d.line([(ax, ay), (sx - size * 0.15, sy - size * 0.3)], fill=RED + (230,), width=5)
            save("fade", ln, 0, 0, 0.9)
            pn = pin(56)
            save("pop", pn, int(sx - size * 0.15) - 28, int(sy - size * 0.3) - 30, 1.0)
    if label:
        ls = label_strip(label, int(H * 0.045))
        save("slide", ls, int(W * 0.06), int(H * 0.08), 0.5)
    meta = {"bg": str(bg_p), "focus": [0.5, 0.5], "layers": layers}
    outbase.with_name(outbase.stem + "_layers.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def card(small: str, big: str, out: Path, img: Path | None = None, W: int = 1920, H: int = 1080, seed: int = 0) -> Path:
    """Thẻ tiêu đề / chương kiểu cắt dán: nền giấy, chữ đen đậm trên giấy đỏ xé, 1 ảnh dán bên cạnh."""
    from .graphics import _wrap_fit, title_font

    base = paper_bg(W, H, seed + 50).convert("RGBA")
    if img and Path(img).exists():
        try:
            st = sticker(Path(img), int(W * 0.36), int(H * 0.62), seed, cutout=True)
            base.alpha_composite(st, (int(W * 0.6), int(H * 0.5 - st.height / 2)))
        except Exception:  # noqa: BLE001
            pass
    d = ImageDraw.Draw(base)
    f, lines, _ = _wrap_fit(d, big.upper(), title_font, int(W * 0.48), int(H * 0.13), int(H * 0.06), 3)
    lh = int(f.size * 1.08)
    bw = int(max(d.textlength(ln, font=f) for ln in lines) + W * 0.05)
    bh = lh * len(lines) + int(H * 0.05)
    red = Image.new("RGBA", (bw, bh), RED + (255,))
    rd = ImageDraw.Draw(red)
    for i, ln in enumerate(lines):
        rd.text((W * 0.025, H * 0.02 + i * lh), ln, font=f, fill=(20, 16, 16))
    red = _torn(red, seed + 3, depth=14).rotate(random.Random(seed).uniform(-2, 2), expand=True)
    x0, y0 = int(W * 0.06), int(H * 0.5 - red.height / 2)
    sh = Image.new("RGBA", red.size, (0, 0, 0, 0))
    sh.putalpha(red.split()[3].point(lambda v: int(v * 0.35)))
    base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (x0 + 12, y0 + 14))
    base.alpha_composite(red, (x0, y0))
    if small:
        ls = label_strip(small.upper(), int(H * 0.04))
        base.alpha_composite(ls, (x0, max(10, y0 - ls.height - 10)))
    base.convert("RGB").save(out, quality=92)
    return out

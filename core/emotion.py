"""Lớp "cảm xúc" cho video hoạt hình 2D (tham khảo cách kể chuyện của các kênh animated short film):

- mood (tâm trạng ánh sáng) cho từng cảnh: neutral | night | rain | warm | phone | tense | sad | hopeful | dawn
    -> chỉnh màu/độ sáng nền, vignette, ánh sáng hắt lên nhân vật (vd. ánh điện thoại hắt lên mặt lúc nửa đêm)
- framing: wide (toàn thân) | closeup (cận mặt, thấy rõ mắt thâm, nước mắt, mồ hôi)
- shadow: "bóng đen nội tâm" (cám dỗ / giọng nói trong đầu) viền phát sáng + chữ viết tay màu cam
- insert: màn hình điện thoại (giờ + thông báo), đồng hồ báo thức, tin nhắn, số dư tài khoản
- hud: bộ đếm góc màn hình (SỐ DƯ $2.400 / NGÀY THỨ 68...), đổi số thì chạy số
Nhân vật được tách lớp riêng khỏi nền -> lúc dựng: thở nhẹ, chớp mắt, bật lên khi xuất hiện, nền trôi chậm (parallax).
"""
from __future__ import annotations

import json
import math
import re
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import mascot
from .util import ROOT

HAND_FONT = ROOT / "assets" / "fonts" / "hand.ttf"
ACCENT = (255, 168, 38)  # cam phát sáng (bóng đen, chữ nội tâm)

MOODS = {
    #           tint RGB            sáng  bão hoà vignette  ánh sáng nhân vật
    "neutral": ((1.0, 1.0, 1.0), 1.0, 1.0, 0.25, (1.0, 1.0, 1.0)),
    "night": ((0.55, 0.65, 0.95), 0.55, 0.8, 0.6, (0.72, 0.76, 0.95)),
    "rain": ((0.6, 0.7, 0.85), 0.5, 0.55, 0.6, (0.72, 0.78, 0.9)),
    "warm": ((1.12, 0.93, 0.72), 0.85, 1.0, 0.45, (1.05, 0.95, 0.82)),
    "phone": ((0.45, 0.5, 0.72), 0.32, 0.7, 0.75, (0.55, 0.55, 0.65)),
    "tense": ((1.05, 0.62, 0.58), 0.6, 0.85, 0.65, (0.95, 0.75, 0.72)),
    "sad": ((0.82, 0.88, 1.0), 0.72, 0.45, 0.5, (0.85, 0.88, 0.95)),
    "hopeful": ((1.08, 1.0, 0.86), 1.05, 1.05, 0.15, (1.05, 1.0, 0.92)),
    "dawn": ((1.12, 0.86, 0.86), 0.9, 0.95, 0.3, (1.05, 0.92, 0.9)),
}


def hand_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(HAND_FONT), size)
    except OSError:
        from .graphics import title_font

        return title_font(size, False)


# ----------------------------------------------------------------- màu / ánh sáng

def grade(img: Image.Image, mood: str) -> Image.Image:
    tint, bright, sat, vig, _ = MOODS.get(mood or "neutral", MOODS["neutral"])
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    g = a.mean(axis=2, keepdims=True)
    a = g + (a - g) * sat
    a = a * np.array(tint, np.float32) * bright
    if mood == "tense":  # tăng tương phản
        a = (a - 0.45) * 1.25 + 0.45
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    a *= (1 - vig * np.clip(r - 0.35, 0, 1) ** 1.4)[..., None]
    if mood == "warm":  # quầng sáng đèn bàn
        a += (np.exp(-(((xx - w * 0.82) / (w * 0.22)) ** 2 + ((yy - h * 0.35) / (h * 0.3)) ** 2))
              [..., None] * np.array([0.35, 0.2, 0.05], np.float32))
    if mood == "hopeful":  # nắng chiếu chéo
        a += (np.exp(-(((xx - w * 0.1) / (w * 0.4)) ** 2 + ((yy + h * 0.1) / (h * 0.5)) ** 2))
              [..., None] * np.array([0.25, 0.2, 0.1], np.float32))
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def light_char(img: Image.Image, mood: str, pose: str = "", glow_at: tuple[float, float] | None = None) -> Image.Image:
    """Ánh sáng lên nhân vật theo mood. Mood "phone" hoặc tư thế cầm điện thoại: mặt sáng cam từ dưới lên."""
    _, _, _, _, ct = MOODS.get(mood or "neutral", MOODS["neutral"])
    a = np.asarray(img.convert("RGBA")).astype(np.float32) / 255
    rgb, al = a[..., :3], a[..., 3:]
    rgb = rgb * (0.45 + 0.55 * np.array(ct, np.float32))  # nhân vật nhuốm màu cảnh nhưng vẫn rõ mặt
    if mood == "phone" or (pose == "phone" and mood in ("night", "rain", "phone", "tense")):
        h, w = rgb.shape[:2]
        gx, gy = glow_at or (0.5, 0.5)
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.exp(-(((xx - w * gx) / (w * 0.42)) ** 2 + ((yy - h * gy) / (h * 0.3)) ** 2))
        rgb = rgb * (0.6 + 0.4 * d[..., None]) + d[..., None] * np.array([0.55, 0.32, 0.05], np.float32)
    if mood == "tense":  # viền đỏ
        edge = np.asarray(Image.fromarray((al[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.FIND_EDGES)
                          .filter(ImageFilter.GaussianBlur(4))).astype(np.float32)[..., None] / 255
        rgb = rgb + edge * np.array([0.8, 0.1, 0.05], np.float32)
    out = np.concatenate([np.clip(rgb, 0, 1), al], axis=2)
    return Image.fromarray((out * 255).astype(np.uint8), "RGBA")


def glow(img: Image.Image, color=ACCENT, radius: int = 18, strength: float = 1.6) -> Image.Image:
    """Viền phát sáng quanh hình (bóng đen nội tâm)."""
    pad = radius * 3
    big = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    big.alpha_composite(img, (pad, pad))
    al = big.split()[3].filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(radius))
    al = al.point(lambda v: min(255, int(v * strength)))
    halo = Image.new("RGBA", big.size, color + (0,))
    halo.putalpha(al)
    halo.alpha_composite(big)
    return halo


def shadow_figure(size: int, facing: str = "left", pose: str = "point", color=ACCENT) -> Image.Image:
    """Bóng đen cám dỗ: thân đen, mặt cười nham hiểm, viền phát sáng."""
    look = {"head": [16, 14, 18], "outline": list(color), "shirt": [16, 14, 18], "pants": [16, 14, 18],
            "shoes": [16, 14, 18], "accessory": "", "line": 9}
    m = mascot.draw_mascot("grin", pose, facing, look, size)
    g = glow(m, color)
    d = ImageDraw.Draw(g)  # vòng sáng dưới chân
    cx, by = g.width / 2, g.height - 18 * 3 - 4
    d.ellipse([cx - m.width * 0.28, by - 22, cx + m.width * 0.28, by + 22], outline=color + (200,), width=5)
    return g


def voice_text(text: str, max_w: int, size: int, color=ACCENT) -> Image.Image:
    """Chữ viết tay (giọng nói trong đầu / cám dỗ)."""
    f = hand_font(size)
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines = [text]
    for width in range(14, 60):
        lines = textwrap.wrap(text, width)
        if max(tmp.textlength(ln, font=f) for ln in lines) <= max_w:
            break
    lh = int(size * 1.15)
    tw = int(max(tmp.textlength(ln, font=f) for ln in lines))
    img = Image.new("RGBA", (tw + 40, lh * len(lines) + 30), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ds, d = ImageDraw.Draw(sh), ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        ds.text((22, 18 + i * lh), ln, font=f, fill=(0, 0, 0, 200))
        d.text((20, 15 + i * lh), ln, font=f, fill=color + (255,))
    sh = sh.filter(ImageFilter.GaussianBlur(5))
    sh.alpha_composite(img)
    return sh


# ----------------------------------------------------------------- màn hình chèn (insert)

def _phone(W: int, H: int, ph_h: float = 0.82) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Khung điện thoại (RGBA) + toạ độ màn hình."""
    h = int(H * ph_h)
    w = int(h * 0.49)
    img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, w + 20, h + 20], radius=int(w * 0.13), fill=(20, 20, 24), outline=(70, 70, 80),
                        width=6)
    sx0, sy0, sx1, sy1 = 20 + int(w * 0.045), 20 + int(w * 0.045), 20 + w - int(w * 0.045), 20 + h - int(w * 0.045)
    grad = Image.new("RGB", (1, 256))
    for y in range(256):
        k = y / 255
        grad.putpixel((0, y), (int(70 + 40 * k), int(50 + 20 * k), int(140 - 30 * k)))
    scr = grad.resize((sx1 - sx0, sy1 - sy0))
    mask = Image.new("L", scr.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, scr.width, scr.height], radius=int(w * 0.1), fill=255)
    img.paste(scr, (sx0, sy0), mask)
    d.rounded_rectangle([20 + w / 2 - w * 0.15, sy0 + 12, 20 + w / 2 + w * 0.15, sy0 + 12 + w * 0.07],
                        radius=int(w * 0.035), fill=(10, 10, 12))
    return img, (sx0, sy0, sx1, sy1)


def _hands_on_phone(canvas: Image.Image, box: tuple[int, int, int, int], look: dict):
    """Hai bàn tay tròn của nhân vật cầm điện thoại ở mép dưới."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(canvas)
    r = int((x1 - x0) * 0.17)
    ol = tuple(look["outline"])
    for cx in (x0 - r * 0.2, x1 + r * 0.2):
        for k in range(3):
            cy = y1 - r * 2.6 + k * r * 0.95
            d.ellipse([cx - r * 0.75, cy - r * 0.5, cx + r * 0.75, cy + r * 0.5], fill=tuple(look["head"]),
                      outline=ol, width=6)


def insert_plate(ins: dict, out: Path, W: int, H: int, bg: Path | None, look: dict, mood: str = "night",
                 lang: str = "vi") -> tuple[Path, list[dict]]:
    """Vẽ màn hình chèn. Trả về (plate 1.5x, các lớp động ở toạ độ khung W/1.5).
    ins: {"type": "phone"|"clock"|"chat"|"bank", "time": "11:48", "date": "...", "app": "...", "text": "...",
          "messages": [{"from": "me"|"them", "text": "..."}]}"""
    from .graphics import title_font

    typ = (ins.get("type") or "phone").lower()
    if bg and Path(bg).exists():
        with Image.open(bg) as im:
            base = ImageOps.fit(im.convert("RGB"), (W, H)).filter(ImageFilter.GaussianBlur(18))
        base = grade(base, "phone" if mood in ("", "neutral") else mood)
    else:
        base = Image.new("RGB", (W, H), (18, 18, 24))
    base = base.convert("RGBA")
    layers: list[dict] = []
    s1 = 1 / 1.5  # toạ độ lớp (khung xuất) = toạ độ plate / 1.5
    if typ == "clock":
        d = ImageDraw.Draw(base)
        bw, bh = int(W * 0.5), int(H * 0.36)
        x0, y0 = (W - bw) // 2, int(H * 0.36)
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=30, fill=(22, 18, 18), outline=(60, 50, 50), width=8)
        t = ins.get("time") or "3:00"
        f = title_font(int(bh * 0.72))
        tw = d.textlength(t, font=f)
        glow_l = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow_l).text(((W - tw) / 2, y0 + bh * 0.08), t, font=f, fill=(255, 40, 30, 255))
        base.alpha_composite(glow_l.filter(ImageFilter.GaussianBlur(16)))
        base.alpha_composite(glow_l)
        if ins.get("text"):
            ft = hand_font(int(H * 0.06))
            d.text((W * 0.5 - d.textlength(ins["text"], font=ft) / 2, y0 + bh + H * 0.05), ins["text"], font=ft,
                   fill=(230, 230, 230))
        base.convert("RGB").save(out, quality=92)
        return out, layers
    ph, (sx0, sy0, sx1, sy1) = _phone(W, H)
    px, py = (W - ph.width) // 2, int(H * 0.09)
    base.alpha_composite(ph, (px, py))
    sx0, sy0, sx1, sy1 = sx0 + px, sy0 + py, sx1 + px, sy1 + py
    sw = sx1 - sx0
    d = ImageDraw.Draw(base)
    white = (245, 245, 250)
    if typ == "phone":
        date = ins.get("date") or ""
        if date:
            f = title_font(int(sw * 0.065), False)
            d.text((sx0 + (sw - d.textlength(date, font=f)) / 2, sy0 + sw * 0.2), date, font=f, fill=white)
        t = ins.get("time") or "23:48"
        f = title_font(int(sw * 0.3))
        d.text((sx0 + (sw - d.textlength(t, font=f)) / 2, sy0 + sw * 0.28), t, font=f, fill=white)
        if ins.get("text"):  # thông báo bật xuống (lớp động)
            nw, nh = int(sw * 0.9), int(sw * 0.36)
            card = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle([0, 0, nw - 1, nh - 1], radius=int(nh * 0.22), fill=(235, 235, 245, 235))
            fa = title_font(int(nh * 0.2))
            cd.text((nh * 0.25, nh * 0.14), (ins.get("app") or "THÔNG BÁO").upper(), font=fa, fill=(90, 90, 110))
            ft = title_font(int(nh * 0.22))
            lines = []
            for wdt in range(30, 8, -1):
                lines = textwrap.wrap(ins["text"], wdt)
                if max(cd.textlength(ln, font=ft) for ln in lines) <= nw - nh * 0.45:
                    break
            lines = lines[:2]
            for k_, ln in enumerate(lines):
                cd.text((nh * 0.25, nh * 0.42 + k_ * ft.size * 1.15), ln, font=ft, fill=(20, 20, 30))
            cx, cy = sx0 + (sw - nw) / 2, sy0 + sw * 0.75
            card = card.resize((int(nw * s1), int(nh * s1)), Image.LANCZOS)
            layers.append({"kind": "notif", "img": card, "x": int(cx * s1), "y": int(cy * s1)})
    elif typ == "bank":
        f = title_font(int(sw * 0.075), False)
        lab = ins.get("app") or ("SỐ DƯ" if lang == "vi" else "BALANCE")
        d.text((sx0 + (sw - d.textlength(lab, font=f)) / 2, sy0 + sw * 0.45), lab, font=f, fill=(210, 210, 225))
        val = ins.get("text") or "0"
        f2 = title_font(int(sw * 0.2))
        neg = val.strip().startswith("-") or ins.get("alert")
        d.text((sx0 + (sw - d.textlength(val, font=f2)) / 2, sy0 + sw * 0.58), val, font=f2,
               fill=(255, 80, 70) if neg else white)
    elif typ == "chat":
        f = title_font(int(sw * 0.085), False)
        if ins.get("app"):  # tên người gửi trên đầu khung chat
            fa = title_font(int(sw * 0.08))
            d.text((sx0 + (sw - d.textlength(ins["app"], font=fa)) / 2, sy0 + sw * 0.18), ins["app"], font=fa,
                   fill=(245, 245, 250))
        y = sy0 + sw * 0.34
        for i, m in enumerate((ins.get("messages") or [{"from": "them", "text": ins.get("text", "")}])[:5]):
            me = m.get("from") == "me"
            lines = textwrap.wrap(m.get("text", ""), 17)
            bw = int(max(d.textlength(ln, font=f) for ln in lines) + sw * 0.08)
            bh = int(len(lines) * f.size * 1.25 + sw * 0.05)
            bx = sx1 - bw - sw * 0.05 if me else sx0 + sw * 0.05
            bub = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bub)
            bd.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=int(sw * 0.04),
                                 fill=(40, 130, 250) if me else (225, 225, 232))
            for k, ln in enumerate(lines):
                bd.text((sw * 0.04, sw * 0.025 + k * f.size * 1.25), ln, font=f,
                        fill=(255, 255, 255) if me else (20, 20, 25))
            layers.append({"kind": "msg", "img": bub.resize((int(bw * s1), int(bh * s1)), Image.LANCZOS),
                           "x": int(bx * s1), "y": int(y * s1), "order": i})
            y += bh + sw * 0.04
    _hands_on_phone(base, (sx0, sy0, sx1, sy1 + int(H * 0.06)), look)
    base.convert("RGB").save(out, quality=92)
    return out, layers


# ----------------------------------------------------------------- bộ đếm góc màn hình (HUD)

_NUM = re.compile(r"-?\d[\d.,]*")


def _parse(s: str) -> tuple[float, str, str, str] | None:
    m = _NUM.search(s or "")
    if not m:
        return None
    raw = m.group(0)
    sep = "." if re.search(r"\d\.\d{3}(\D|$)", raw) else ","
    try:
        v = float(raw.replace(sep, "").replace(",", "."))
    except ValueError:
        return None
    return v, s[: m.start()], s[m.end():], sep


def _fmt(v: float, sep: str) -> str:
    return f"{int(round(v)):,}".replace(",", sep)


def hud_png(text: str, W: int, H: int, color=(255, 255, 255)) -> Image.Image:
    from .graphics import title_font

    f = title_font(int(H * 0.034))
    img = Image.new("RGBA", (W, int(H * 0.1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((W * 0.028 + 3, H * 0.03 + 3), text, font=f, fill=(0, 0, 0, 160))
    d.text((W * 0.028, H * 0.03), text, font=f, fill=color + (255,))
    return img


def hud_frames(prev: str, cur: str, folder: Path, fps: int, W: int, H: int) -> tuple[str, int]:
    """PNG: chữ HUD. Nếu số thay đổi -> chạy số trong ~1 giây (đỏ khi giảm, xanh khi tăng)."""
    folder.mkdir(parents=True, exist_ok=True)
    a, b = _parse(prev), _parse(cur)
    if not a or not b or a[0] == b[0] or a[1].strip() != b[1].strip():
        p = folder / "f_0000.png"
        if not p.exists():
            hud_png(cur, W, H).save(p)
        return str(folder / "f_%04d.png"), 1
    n = int(fps * 1.0)
    col = (255, 90, 80) if b[0] < a[0] else (110, 230, 120)
    if not (folder / f"f_{n + int(fps * 0.6) - 1:04d}.png").exists():
        for i in range(n + int(fps * 0.6)):
            k = min(1.0, i / n)
            e = 1 - (1 - k) ** 3
            v = a[0] + (b[0] - a[0]) * e
            txt = f"{b[1]}{_fmt(v, b[3])}{b[2]}"
            c = col if i < n + int(fps * 0.3) else (255, 255, 255)
            hud_png(txt, W, H, c).save(folder / f"f_{i:04d}.png")
    return str(folder / "f_%04d.png"), n + int(fps * 0.6)


# ----------------------------------------------------------------- mưa

def rain_texture(path: Path, W: int, H: int, seed: int = 3) -> Path:
    if path.exists():
        return path
    rng = np.random.default_rng(seed)
    img = Image.new("RGBA", (W, H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(int(W * 0.35)):
        x, y = rng.uniform(0, W), rng.uniform(0, H * 2)
        ln = rng.uniform(H * 0.03, H * 0.08)
        a = int(rng.uniform(40, 110))
        d.line([(x, y), (x - ln * 0.12, y + ln)], fill=(200, 210, 230, a), width=int(rng.integers(1, 3)))
    img.save(path)
    return path


# ----------------------------------------------------------------- ghép cảnh nhân vật theo lớp

def compose_layers(bg: Path | None, outbase: Path, W: int, H: int, char: dict, look: dict, title_font_fn,
                   story_caps: bool = False) -> dict:
    """Tạo: nền đã chỉnh màu (1.5x, để camera trôi) + các lớp PNG (toạ độ khung W x H) + 1 ảnh gộp (cho CapCut).
    Trả về meta {"bg", "flat", "focus", "layers": [{"kind","file","x","y"}]}."""
    mood = char.get("mood") or "neutral"
    W2, H2 = int(W * 1.5), int(H * 1.5)
    if bg and Path(bg).exists():
        with Image.open(bg) as im:
            base = ImageOps.fit(im.convert("RGB"), (W2, H2), Image.LANCZOS)
    else:
        base = Image.new("RGB", (W2, H2), (60, 58, 70) if mood in ("night", "rain", "phone", "tense") else (238, 230, 212))
    base = grade(base, mood)
    bg_out = outbase.with_name(outbase.stem + "_bg.jpg")
    base.save(bg_out, quality=92)

    framing = char.get("framing") or "wide"
    pos = char.get("position", "left")
    has_shadow = bool(char.get("shadow"))
    px = {"left": 0.3, "center": 0.5, "right": 0.7}.get(pos, 0.3)
    if framing == "closeup":
        px = {"left": 0.36, "center": 0.5, "right": 0.64}.get(pos, 0.36) if has_shadow else 0.5
    facing = char.get("facing") or ("right" if px < 0.5 else "left")
    exp, pose = char.get("expression", "neutral"), char.get("pose", "stand")
    if framing == "closeup":
        size = int(H * 1.12)
    else:
        size = int(H * float(char.get("scale", 0.66)))
    glow_at = (0.5, 0.55) if pose == "phone" else (0.5, 0.42)
    m = light_char(mascot.draw_mascot(exp, pose, facing, look, size), mood, pose, glow_at)
    mb = light_char(mascot.draw_mascot(exp, pose, facing, look, size, blink=True), mood, pose, glow_at)
    # bóng tiếp đất (chỉ khi toàn thân)
    canvas_h = m.height + (int(H * 0.04) if framing != "closeup" else 0)

    def with_floor(im: Image.Image) -> Image.Image:
        c = Image.new("RGBA", (im.width, canvas_h), (0, 0, 0, 0))
        if framing != "closeup":
            sh = Image.new("RGBA", (int(im.width * 0.75), int(H * 0.05)), (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse([0, 0, sh.width, sh.height], fill=(0, 0, 0, 90))
            c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), ((im.width - sh.width) // 2,
                                                                         canvas_h - sh.height))
        c.alpha_composite(im, (0, 0))
        return c

    m, mb = with_floor(m), with_floor(mb)
    if framing == "closeup":
        cx, cy = int(W * px - m.width / 2), int(H * 0.56 - m.height * 0.27)
    else:
        cx, cy = int(W * px - m.width / 2), int(H * 0.985 - m.height)
    layers: list[dict] = []
    files = {}

    def save(kind: str, im: Image.Image, x: int, y: int, **kw):
        p = outbase.with_name(f"{outbase.stem}_{kind}.png")
        im.save(p)
        files[kind] = p
        layers.append({"kind": kind, "file": str(p), "x": int(x), "y": int(y), "w": im.width, "h": im.height, **kw})

    if has_shadow:  # bóng đen đứng phía sau, hơi lệch, nhìn về nhân vật
        sx_rel = (0.26 if framing != "closeup" else 0.34) * (1 if px <= 0.5 else -1)
        s_size = int(H * 0.62) if framing != "closeup" else int(H * 0.9)
        sf = shadow_figure(s_size, "left" if sx_rel > 0 else "right", "stand")
        sx = int(W * (px + sx_rel) - sf.width / 2)
        sy = int(H * 0.985 - sf.height + 18 * 3) if framing != "closeup" else int(H * 0.3)
        save("shadow", sf, sx, sy)
    save("char", m, cx, cy)
    save("blink", mb, cx, cy)
    top_min = int(H * (0.17 if story_caps else 0.03))
    face = (px, (cy + m.height * 0.27) / H)
    if char.get("thought"):
        b = mascot.thought_bubble(char["thought"], title_font_fn(int(H * 0.055)), int(W * 0.3),
                                  "speech" if char.get("bubble") == "speech" else "thought")
        if framing == "closeup":
            bx = int(W * (0.06 if px >= 0.5 else 0.62))
            by = max(top_min, int(H * 0.12))
        else:
            bx = int(W * px + (m.width * 0.22 if px <= 0.5 else -m.width * 0.22 - b.width))
            by = max(top_min, int(cy - b.height * 0.5))
        bx = max(20, min(W - b.width - 20, bx))
        save("bubble", b, bx, by)
    if (char.get("shadow") or "").strip():
        vt = voice_text(char["shadow"], int(W * 0.36), int(H * 0.06))
        sl = next(x for x in layers if x["kind"] == "shadow")
        vx = sl["x"] + sl["w"] // 2 - vt.width // 2
        vy = max(top_min, sl["y"] + 18 * 3 - vt.height) if framing != "closeup" else max(top_min, int(H * 0.14))
        save("voice", vt, max(20, min(W - vt.width - 20, vx)), vy)
    # ảnh gộp (CapCut / ảnh xem trước)
    flat = base.resize((W, H), Image.LANCZOS).convert("RGBA")
    for ly in layers:
        if ly["kind"] == "blink":
            continue
        with Image.open(ly["file"]) as im:
            _paste_clip(flat, im.convert("RGBA"), ly["x"], ly["y"])
    flat_p = outbase.with_name(outbase.stem + "_flat.jpg")
    flat.convert("RGB").resize((W2, H2), Image.LANCZOS).save(flat_p, quality=90)
    meta = {"bg": str(bg_out), "flat": str(flat_p), "focus": list(face), "layers": layers}
    outbase.with_name(outbase.stem + "_layers.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _paste_clip(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """alpha_composite không nhận toạ độ âm -> cắt phần ngoài khung."""
    l, t = max(0, -x), max(0, -y)
    if l >= src.width or t >= src.height:
        return
    part = src.crop((l, t, min(src.width, l + dst.width - max(0, x)), min(src.height, t + dst.height - max(0, y))))
    dst.alpha_composite(part, (max(0, x), max(0, y)))

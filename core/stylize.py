"""Biến ảnh gốc thành "plate" (khung hình 16:9 lớn gấp 1.5 lần) theo phong cách kể chuyện bằng ảnh.

Kiểu khung (frame style):
  full      ảnh phủ kín khung (ảnh ngang)
  blurfit   ảnh nằm giữa trên nền mờ của chính nó (ảnh dọc / vuông)
  print     ảnh in cũ có viền kem, hơi xoay, đổ bóng, đặt trên mặt bàn tối
  polaroid  ảnh polaroid viền trắng dày phía dưới
  clipping  mẩu báo / tài liệu: ngả vàng, mép giấy, đặt trên bàn
  detail    crop cận vào 1 vùng của ảnh (punch-in chi tiết)
Kèm theo: tìm "điểm nhấn" (focus) của ảnh để camera zoom/lia về đó.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


def focal_point(img: Image.Image) -> tuple[float, float]:
    """Điểm nhấn ~ trọng tâm vùng nhiều chi tiết (mặt người, chữ, vật thể). Trả về toạ độ chuẩn hoá 0..1."""
    small = ImageOps.grayscale(img).resize((96, 54))
    edges = small.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(3))
    px = list(edges.getdata())
    w, h = edges.size
    tot = sum(px) or 1
    cx = sum((i % w) * v for i, v in enumerate(px)) / tot / w
    cy = sum((i // w) * v for i, v in enumerate(px)) / tot / h
    # kéo nhẹ về giữa + hơi lên trên (bố cục 1/3 trên thường chứa mặt người)
    return (0.6 * cx + 0.4 * 0.5, 0.6 * cy + 0.4 * 0.42)


def detail_box(img: Image.Image, focus: tuple[float, float], scale: float = 0.5, seed: int = 0) -> tuple:
    """Hộp crop cận (tỉ lệ 16:9) quanh điểm nhấn, lệch ngẫu nhiên nhẹ để mỗi lần khác nhau."""
    rnd = random.Random(seed)
    W, H = img.size
    bw = min(W, max(H * 16 / 9 * scale, W * scale))
    bh = bw * 9 / 16
    if bh > H:
        bh, bw = H, H * 16 / 9
    cx = focus[0] * W + rnd.uniform(-0.12, 0.12) * W
    cy = focus[1] * H + rnd.uniform(-0.1, 0.1) * H
    x0 = min(max(0, cx - bw / 2), W - bw)
    y0 = min(max(0, cy - bh / 2), H - bh)
    return (x0 / W, y0 / H, (x0 + bw) / W, (y0 + bh) / H)


def _desk(W: int, H: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    base = Image.effect_noise((W // 6, H // 6), 28).resize((W, H), Image.BICUBIC)
    base = ImageOps.colorize(base, (14, 12, 10), (52, 44, 36))
    d = ImageDraw.Draw(base)
    for _ in range(60):  # vân gỗ
        y = rnd.randint(0, H)
        d.line([(0, y), (W, y + rnd.randint(-30, 30))], fill=(38 + rnd.randint(-6, 6), 32, 26), width=rnd.randint(1, 3))
    base = base.filter(ImageFilter.GaussianBlur(1.2))
    return _vignette(base, 0.6)


def _vignette(img: Image.Image, strength: float) -> Image.Image:
    w, h = img.size
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse([-w * 0.2, -h * 0.3, w * 1.2, h * 1.3], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(min(w, h) // 5))
    return Image.composite(img, ImageEnhance.Brightness(img).enhance(1 - strength), m)


def _age(img: Image.Image, amount: float = 0.5) -> Image.Image:
    """Ngả vàng + giảm tương phản kiểu giấy ảnh cũ."""
    g = ImageOps.grayscale(img)
    sep = ImageOps.colorize(g, (40, 30, 20), (238, 225, 196))
    out = Image.blend(img, sep, amount)
    return ImageEnhance.Contrast(out).enhance(0.92)


def _paste_card(canvas: Image.Image, card: Image.Image, angle: float, seed: int, center=(0.5, 0.5)) -> None:
    card = card.convert("RGBA").rotate(angle, resample=Image.BICUBIC, expand=True)
    shadow = Image.new("RGBA", (card.width + 80, card.height + 80), (0, 0, 0, 0))
    alpha = card.split()[3].point(lambda a: 170 if a > 0 else 0)
    shadow.paste((0, 0, 0, 255), (40, 40), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    W, H = canvas.size
    x = int(W * center[0] - card.width / 2)
    y = int(H * center[1] - card.height / 2)
    canvas.paste(shadow, (x - 22, y - 10), shadow)
    canvas.paste(card, (x, y), card)


def _rough_edges(card: Image.Image, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    w, h = card.size
    mask = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(mask)
    step = 6
    for x in range(0, w, step):  # mép trên/dưới răng cưa
        d.rectangle([x, 0, x + step, rnd.randint(0, 7)], fill=0)
        d.rectangle([x, h - rnd.randint(0, 7), x + step, h], fill=0)
    for y in range(0, h, step):
        d.rectangle([0, y, rnd.randint(0, 6), y + step], fill=0)
        d.rectangle([w - rnd.randint(0, 6), y, w, y + step], fill=0)
    card = card.convert("RGBA")
    card.putalpha(mask)
    return card


def make_plate(src: Path, out: Path, w: int, h: int, style: str = "auto", crop=None, seed: int = 0,
               aged: bool = False) -> tuple[Path, tuple[float, float], str]:
    """Tạo plate (1.5x khung). Trả về (đường dẫn, điểm nhấn trên plate, style đã dùng)."""
    W, H = int(w * 1.5), int(h * 1.5)
    rnd = random.Random(seed)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    if crop:
        x0, y0, x1, y1 = crop
        im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
        style = "full" if style in ("auto", "detail") else style
    ar = im.width / im.height
    if style == "auto":
        style = "full" if 1.45 <= ar <= 2.1 else "blurfit"
    if aged:
        im = _age(im, 0.35)

    if style == "full":
        plate = ImageOps.fit(im, (W, H), Image.LANCZOS, centering=focal_point(im))
        fx, fy = focal_point(plate)
    elif style == "blurfit":
        plate = ImageOps.fit(im, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(45))
        plate = ImageEnhance.Brightness(plate).enhance(0.4)
        fg = ImageOps.contain(im, (int(W * 0.9), int(H * 0.9)), Image.LANCZOS)
        _paste_card(plate, fg, 0, seed)
        f = focal_point(fg)
        fx = (W - fg.width) / 2 / W + f[0] * fg.width / W
        fy = (H - fg.height) / 2 / H + f[1] * fg.height / H
    else:  # print / polaroid / clipping trên mặt bàn
        plate = _desk(W, H, seed)
        maxw, maxh = int(W * 0.72), int(H * 0.8)
        if style == "clipping":
            maxw, maxh = int(W * 0.86), int(H * 0.96)
            card = _age(im, 0.75)
            card = ImageOps.contain(card, (maxw, maxh), Image.LANCZOS)
            card = _rough_edges(card, seed)
        else:
            body = ImageOps.contain(im, (maxw, maxh), Image.LANCZOS)
            if style == "polaroid":
                pad, bottom = int(body.width * 0.05), int(body.width * 0.18)
                card = Image.new("RGB", (body.width + 2 * pad, body.height + pad + bottom), (236, 232, 222))
            else:
                pad = bottom = int(body.width * 0.035)
                card = Image.new("RGB", (body.width + 2 * pad, body.height + 2 * pad), (226, 214, 190))
            card.paste(body, (pad, pad))
            card = _age(card, 0.15)
        angle = rnd.uniform(-4, 4)
        cx, cy = 0.5 + rnd.uniform(-0.04, 0.04), 0.5 + rnd.uniform(-0.03, 0.03)
        _paste_card(plate, card, angle, seed, (cx, cy))
        f = focal_point(card)
        fx = cx + (f[0] - 0.5) * card.width / W
        fy = cy + (f[1] - 0.5) * card.height / H
    plate.convert("RGB").save(out, quality=92)
    return out, (min(max(fx, 0.2), 0.8), min(max(fy, 0.2), 0.8)), style


def is_tall(path: str) -> bool:
    try:
        with Image.open(path) as im:
            return im.height > im.width * 1.15
    except Exception:  # noqa: BLE001
        return False


def image_size(path: str) -> tuple[int, int]:
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return (0, 0)



def red_circle(plate_path: Path, focus: tuple[float, float], seed: int = 0, radius: float = 0.13) -> Path:
    """Vẽ vòng tròn đỏ 'vẽ tay' quanh điểm nhấn (kiểu đánh dấu vật chứng) lên plate."""
    rnd = random.Random(seed)
    with Image.open(plate_path) as im:
        im = im.convert("RGB")
    W, H = im.size
    cx, cy = focus[0] * W, focus[1] * H
    rx, ry = radius * W * 0.75, radius * H * 1.1
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    import math

    for k in range(3):  # 3 nét chồng nhau lệch nhẹ -> giống bút dạ vẽ tay
        pts = []
        a0 = rnd.uniform(0, 2 * math.pi)
        for i in range(0, 380, 6):
            a = a0 + math.radians(i)
            wob = 1 + 0.04 * math.sin(a * 3 + k) + rnd.uniform(-0.01, 0.01)
            pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
        d.line(pts, fill=(205, 25, 30, 230 - k * 50), width=max(4, int(W * 0.0045)), joint="curve")
    im = im.convert("RGBA")
    im.alpha_composite(layer)
    im.convert("RGB").save(plate_path, quality=92)
    return plate_path

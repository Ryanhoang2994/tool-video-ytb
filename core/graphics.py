"""Đồ hoạ bằng PIL: thẻ tiêu đề, thẻ chương, nhãn chữ (lower-third), thumbnail, chuẩn hoá khung ảnh."""
from __future__ import annotations

import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .util import find_font, find_mono_font


def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except OSError:
        return ImageFont.load_default()


def _paper_bg(w: int, h: int, seed: int = 0) -> Image.Image:
    """Nền tối có vân, kiểu bàn làm việc của thám tử."""
    rnd = random.Random(seed)
    base = Image.new("RGB", (w, h), (18, 17, 16))
    noise = Image.effect_noise((w // 4, h // 4), 40).resize((w, h), Image.BILINEAR)
    noise = ImageOps.colorize(noise, (10, 10, 10), (48, 44, 38))
    img = Image.blend(base, noise, 0.6)
    d = ImageDraw.Draw(img)
    for _ in range(40):  # vết xước mờ
        x = rnd.randint(0, w)
        d.line([(x, 0), (x + rnd.randint(-40, 40), h)], fill=(30, 28, 26), width=1)
    return _vignette(img)


def _vignette(img: Image.Image, strength: float = 0.75) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([-w * 0.15, -h * 0.25, w * 1.15, h * 1.25], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) // 5))
    dark = ImageEnhance.Brightness(img).enhance(1 - strength)
    return Image.composite(img, dark, mask)


def _center_text(d: ImageDraw.ImageDraw, w: int, y: int, text: str, font, fill, spacing=12) -> int:
    box = d.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align="center")
    tw, th = box[2] - box[0], box[3] - box[1]
    d.multiline_text(((w - tw) / 2, y), text, font=font, fill=fill, spacing=spacing, align="center")
    return y + th


def title_card(title: str, channel: str, out: Path, w=1920, h=1080, font="") -> Path:
    img = _paper_bg(w, h, 1)
    d = ImageDraw.Draw(img)
    f_big = _font(find_font(font), 92)
    f_small = _font(find_mono_font(), 34)
    lines = "\n".join(textwrap.wrap(title.upper(), 26))
    _center_text(d, w, int(h * 0.12), channel.upper(), f_small, (170, 40, 35))
    box = d.multiline_textbbox((0, 0), lines, font=f_big, spacing=18, align="center")
    y = (h - (box[3] - box[1])) // 2
    end = _center_text(d, w, y, lines, f_big, (232, 226, 214), spacing=18)
    d.line([(w * 0.35, end + 40), (w * 0.65, end + 40)], fill=(170, 40, 35), width=4)
    img.save(out, quality=95)
    return out


def chapter_card(num: int, title: str, out: Path, w=1920, h=1080, font="", lang="vi") -> Path:
    img = _paper_bg(w, h, num + 7)
    d = ImageDraw.Draw(img)
    if num > 0:
        label = f"{'CHƯƠNG' if lang == 'vi' else 'CHAPTER'} {num}"
        _center_text(d, w, int(h * 0.36), label, _font(find_mono_font(), 40), (170, 40, 35))
    lines = "\n".join(textwrap.wrap(title, 30))
    _center_text(d, w, int(h * 0.45), lines, _font(find_font(font), 78), (232, 226, 214), spacing=16)
    img.save(out, quality=95)
    return out


def label_png(text: str, out: Path, w=1920, h=1080, box_text: str = "") -> Path:
    """Nhãn kiểu máy đánh chữ ở góc dưới trái, nền trong suốt (overlay). box_text: chữ đầy đủ để cố định khung."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = _font(find_mono_font(), 44)
    box = d.textbbox((0, 0), (box_text or text) + " ", font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    x, y = 110, h - 190
    d.rectangle([x - 26, y - 20, x + tw + 26, y + th + 30], fill=(10, 10, 10, 185))
    d.rectangle([x - 26, y - 20, x - 18, y + th + 30], fill=(170, 40, 35, 255))
    d.text((x, y), text, font=f, fill=(236, 230, 218, 255))
    img.save(out)
    return out


def frame_image(src: Path, out: Path, w: int, h: int) -> Path:
    """Đưa ảnh bất kỳ về khung 16:9 (gấp 1.5 lần độ phân giải để zoom Ken Burns không vỡ).
    Ảnh dọc / tài liệu: đặt giữa trên nền mờ của chính nó."""
    W, H = int(w * 1.5), int(h * 1.5)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        ar = im.width / im.height
        target = W / H
        if 0.85 * target <= ar <= 1.25 * target:
            img = ImageOps.fit(im, (W, H), Image.LANCZOS)
        else:
            bg = ImageOps.fit(im, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
            bg = ImageEnhance.Brightness(bg).enhance(0.45)
            fg = ImageOps.contain(im, (int(W * 0.92), int(H * 0.92)), Image.LANCZOS)
            shadow = Image.new("RGBA", (fg.width + 60, fg.height + 60), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rectangle([30, 30, fg.width + 30, fg.height + 30], fill=(0, 0, 0, 200))
            shadow = shadow.filter(ImageFilter.GaussianBlur(18))
            px, py = (W - fg.width) // 2, (H - fg.height) // 2
            bg.paste(shadow, (px - 30, py - 20), shadow)
            bg.paste(fg, (px, py))
            img = bg
        img.save(out, quality=93)
    return out


def thumbnail(bg_image: Path | None, text: str, channel: str, out: Path, font="") -> Path:
    w, h = 1280, 720
    if bg_image and Path(bg_image).exists():
        with Image.open(bg_image) as im:
            img = ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)
        img = ImageEnhance.Color(img).enhance(0.5)
        img = ImageEnhance.Contrast(img).enhance(1.25)
        img = _vignette(img, 0.6)
    else:
        img = _paper_bg(w, h, 3)
    d = ImageDraw.Draw(img)
    f = _font(find_font(font), 110)
    lines = textwrap.wrap(text.upper(), 14)[:3]
    y = h - 70 - len(lines) * 120
    for i, ln in enumerate(lines):
        color = (255, 214, 0) if i == len(lines) - 1 else (255, 255, 255)
        d.text((60, y), ln, font=f, fill=color, stroke_width=8, stroke_fill=(0, 0, 0))
        y += 120
    d.rectangle([0, 0, 18, h], fill=(190, 25, 25))
    d.text((60, 40), channel.upper(), font=_font(find_font(font), 36), fill=(230, 230, 230),
           stroke_width=3, stroke_fill=(0, 0, 0))
    img.save(out, quality=95)
    return out


# =====================================================================
#  PHONG CÁCH "CRIME DOC" TỐI (tiêu đề chữ đứng xám/đỏ, bảng điều tra, poster, thẻ tên)
# =====================================================================
RED = (196, 38, 52)
GRAY = (178, 178, 178)


def title_font(size: int, bold: bool = True):
    from .util import ROOT

    p = ROOT / "assets" / "fonts" / ("title.ttf" if bold else "title_regular.ttf")
    if p.exists():
        return ImageFont.truetype(str(p), size)
    return _font(find_font(), size)


def dark_wall(w: int, h: int, seed: int = 0) -> Image.Image:
    """Nền tường tối có vân + khói mờ."""
    rnd = random.Random(seed)
    n1 = Image.effect_noise((w // 8, h // 8), 60).resize((w, h), Image.BICUBIC)
    n2 = Image.effect_noise((w // 2, h // 2), 25).resize((w, h), Image.BILINEAR)
    base = ImageOps.colorize(Image.blend(n1, n2, 0.35), (6, 7, 9), (40, 42, 46))
    smoke = Image.effect_noise((w // 24, h // 24), 90).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(30))
    base = Image.composite(ImageOps.colorize(smoke, (0, 0, 0), (70, 72, 78)), base, smoke.point(lambda v: v // 3))
    d = ImageDraw.Draw(base)
    for _ in range(25):
        x = rnd.randint(0, w)
        d.line([(x, 0), (x + rnd.randint(-60, 60), h)], fill=(20, 21, 24), width=1)
    return _vignette(base, 0.7)


def _print_photo(img: Image.Image, maxw: int, maxh: int, border=(222, 218, 208), aged=0.25) -> Image.Image:
    img = ImageOps.grayscale(img).convert("RGB") if aged > 0.5 else img
    body = ImageOps.contain(img, (maxw, maxh), Image.LANCZOS)
    pad = max(6, int(min(body.size) * 0.04))
    card = Image.new("RGB", (body.width + 2 * pad, body.height + 2 * pad), border)
    card.paste(body, (pad, pad))
    return card


def _pin(d: ImageDraw.ImageDraw, x: float, y: float, r: int = 11):
    d.ellipse([x - r + 3, y - r + 5, x + r + 3, y + r + 5], fill=(0, 0, 0))
    d.ellipse([x - r, y - r, x + r, y + r], fill=(170, 25, 30))
    d.ellipse([x - r / 3 - 2, y - r / 3 - 2, x - r / 3 + 3, y - r / 3 + 3], fill=(240, 150, 150))


def evidence_board(images: list, out: Path, w: int = 2880, h: int = 1620, seed: int = 0,
                   region=(0.0, 0.0, 1.0, 1.0)) -> tuple[Path, list]:
    """Bảng điều tra: ảnh ghim trên tường tối nối bằng dây đỏ. Trả về (file, danh sách toạ độ ghim 0..1)."""
    rnd = random.Random(seed)
    board = dark_wall(w, h, seed)
    imgs = []
    for p in images[:8]:
        try:
            with Image.open(p) as im:
                imgs.append(ImageOps.exif_transpose(im).convert("RGB"))
        except Exception:  # noqa: BLE001
            pass
    n = max(1, len(imgs))
    import math

    cols = max(1, min(4, math.ceil(math.sqrt(n * 1.6))))
    rows = (n + cols - 1) // cols
    x0, y0, x1, y1 = [v * s for v, s in zip(region, (w, h, w, h))]
    cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
    pins = []
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        cx = x0 + cw * (c + 0.5) + rnd.uniform(-cw * 0.1, cw * 0.1)
        cy = y0 + ch * (r + 0.5) + rnd.uniform(-ch * 0.08, ch * 0.08)
        card = _print_photo(im, int(cw * 0.9), int(ch * 0.86), aged=0.6 if rnd.random() < 0.5 else 0.2)
        card = card.convert("RGBA").rotate(rnd.uniform(-6, 6), resample=Image.BICUBIC, expand=True)
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
        sh.putalpha(card.split()[3].point(lambda a: 160 if a else 0))
        sh = sh.filter(ImageFilter.GaussianBlur(14))
        px, py = int(cx - card.width / 2), int(cy - card.height / 2)
        layer.alpha_composite(sh, (px + 14, py + 18))
        layer.alpha_composite(card, (px, py))
        pins.append((cx, py + 14))
    board = board.convert("RGBA")
    board.alpha_composite(layer)
    d = ImageDraw.Draw(board)
    order = list(range(len(pins)))
    rnd.shuffle(order)
    for a, b in zip(order, order[1:] + order[:1] if len(order) > 2 else order[1:]):
        (xa, ya), (xb, yb) = pins[a], pins[b]
        sag = abs(xb - xa) * 0.06
        pts = [(xa + (xb - xa) * t, ya + (yb - ya) * t + sag * 4 * t * (1 - t)) for t in [i / 20 for i in range(21)]]
        d.line(pts, fill=(150, 18, 24), width=4)
    for x, y in pins:
        _pin(d, x, y)
    out_img = _vignette(board.convert("RGB"), 0.55)
    out_img.save(out, quality=92)
    return out, [(x / w, y / h) for x, y in pins]


def pinned_photo(src: Path, out: Path, w: int = 2880, h: int = 1620, seed: int = 0, poster: bool = False) -> Path:
    """1 ảnh ghim trên tường tối (hoặc poster giấy rách) - dùng khi giới thiệu nhân vật / vật chứng."""
    rnd = random.Random(seed)
    board = dark_wall(w, h, seed).convert("RGBA")
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    if poster:
        card = _print_photo(ImageOps.grayscale(im).convert("RGB"), int(w * 0.5), int(h * 0.9), border=(214, 208, 192))
    else:
        card = _print_photo(im, int(w * 0.46), int(h * 0.74), aged=0.6)
    card = card.convert("RGBA")
    if poster:  # mép rách
        m = Image.new("L", card.size, 255)
        dm = ImageDraw.Draw(m)
        for x in range(0, card.width, 8):
            dm.rectangle([x, 0, x + 8, rnd.randint(0, 14)], fill=0)
            dm.rectangle([x, card.height - rnd.randint(0, 14), x + 8, card.height], fill=0)
        card.putalpha(m)
    card = card.rotate(rnd.uniform(-3, 3), resample=Image.BICUBIC, expand=True)
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    sh.putalpha(card.split()[3].point(lambda a: 170 if a else 0))
    sh = sh.filter(ImageFilter.GaussianBlur(20))
    px, py = int(w * (0.5 + rnd.uniform(-0.03, 0.03)) - card.width / 2), int(h * 0.5 - card.height / 2)
    board.alpha_composite(sh, (px + 18, py + 22))
    board.alpha_composite(card, (px, py))
    _pin(ImageDraw.Draw(board), px + card.width / 2, py + 22, 13)
    _vignette(board.convert("RGB"), 0.5).save(out, quality=92)
    return out


def silhouette(out: Path, w: int = 1000, h: int = 1250) -> Path:
    """Ảnh 'không có tư liệu': bóng đen người với dấu hỏi."""
    img = Image.new("RGB", (w, h), (58, 60, 64))
    d = ImageDraw.Draw(img)
    d.ellipse([w * 0.32, h * 0.14, w * 0.68, h * 0.48], fill=(18, 18, 20))
    d.rounded_rectangle([w * 0.16, h * 0.5, w * 0.84, h * 1.1], radius=int(w * 0.25), fill=(18, 18, 20))
    f = title_font(int(h * 0.2))
    d.text((w / 2, h * 0.31), "?", font=f, fill=(90, 92, 98), anchor="mm")
    img.save(out, quality=92)
    return out


def crime_title_card(line1: str, line2: str, out: Path, right_img: Path | None, w=1920, h=1080, seed=1,
                     small: str = "") -> Path:
    """Thẻ tiêu đề kiểu phim tài liệu tội phạm: chữ đứng xám + đỏ bên trái, ảnh/bảng điều tra bên phải chìm vào tối."""
    W, H = int(w * 1.5), int(h * 1.5)
    base = dark_wall(W, H, seed)
    if right_img and Path(right_img).exists():
        with Image.open(right_img) as im:
            r = ImageOps.fit(im.convert("RGB"), (int(W * 0.62), H), Image.LANCZOS)
        r = ImageEnhance.Brightness(ImageEnhance.Color(r).enhance(0.35)).enhance(0.8)
        mask = Image.new("L", (r.width, 1))  # trái trong suốt -> phải rõ
        mask.putdata([int(255 * min(1.0, (x / r.width) ** 1.3 * 1.9)) for x in range(r.width)])
        mask = mask.resize(r.size)
        base.paste(r, (W - r.width, 0), mask)
    base = _vignette(base, 0.55)
    d = ImageDraw.Draw(base)
    x = int(W * 0.08)
    f1 = title_font(int(H * 0.085))
    size2 = int(H * 0.16)
    f2 = title_font(size2)
    while d.textlength(line2, font=f2) > W * 0.52 and size2 > 40:
        size2 -= 6
        f2 = title_font(size2)
    y2 = int(H * 0.55)
    d.text((x + 4, y2 - int(H * 0.1)), line1.upper(), font=f1, fill=GRAY)
    d.text((x, y2), line2.upper(), font=f2, fill=RED)
    if small:
        d.text((x + 6, y2 + size2 + int(H * 0.03)), small.upper(), font=title_font(int(H * 0.035), False), fill=(140, 140, 140))
    base.save(out, quality=93)
    return out


def name_card_png(name: str, role: str, out: Path, w=1920, h=1080) -> Path:
    """Thẻ tên nhân vật (overlay trong suốt) góc dưới trái."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fn, fr = title_font(84), title_font(40, False)
    x, y = 110, h - 260
    tw = max(d.textlength(name.upper(), font=fn), d.textlength(role.upper(), font=fr))
    grad = Image.new("RGBA", (int(tw + 160), 190), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(grad.width):
        gd.line([(i, 0), (i, 190)], fill=(0, 0, 0, int(190 * (1 - i / grad.width))))
    img.alpha_composite(grad, (x - 40, y - 20))
    d.rectangle([x - 26, y, x - 16, y + 150], fill=RED + (255,))
    d.text((x, y - 4), name.upper(), font=fn, fill=(240, 240, 240, 255))
    d.text((x + 2, y + 100), role.upper(), font=fr, fill=RED + (255,))
    img.save(out)
    return out


def fog_texture(out: Path, w=3840, h=1080, seed=5) -> Path:
    """Lớp khói/sương trong suốt để trôi ngang trên hình."""
    if out.exists():
        return out
    # khói dạng dải ngang mảnh (kéo giãn theo chiều ngang), dày hơn ở nửa dưới khung hình
    n = Image.effect_noise((w // 160, h // 30), 100).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(25))
    n2 = Image.effect_noise((w // 60, h // 14), 70).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(10))
    a = Image.blend(n, n2, 0.35).point(lambda v: max(0, int((v - 112) * 1.6)))
    grad = Image.new("L", (1, h))
    grad.putdata([int(90 + 165 * (y / h) ** 1.2) for y in range(h)])
    a = Image.composite(a, Image.new("L", (w, h), 0), grad.resize((w, h)))
    # nối liền mép trái-phải để lặp vô hạn
    left = a.crop((0, 0, 200, h))
    mask = Image.linear_gradient("L").rotate(90, expand=True).resize((200, h))
    a.paste(left, (w - 200, 0), ImageOps.invert(mask))
    fog = Image.new("RGBA", (w, h), (200, 205, 215, 0))
    fog.putalpha(a)
    fog.save(out)
    return out


def crime_thumbnail(bg: Path | None, face: Path | None, text: str, stamp: str, out: Path) -> Path:
    w, h = 1280, 720
    base = dark_wall(w, h, 9)
    if bg and Path(bg).exists():
        with Image.open(bg) as im:
            b = ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)
        b = ImageEnhance.Brightness(ImageEnhance.Color(b).enhance(0.4)).enhance(0.55)
        base = Image.blend(base, b, 0.55)
    if face and Path(face).exists():
        with Image.open(face) as im:
            f = ImageOps.contain(ImageOps.grayscale(im).convert("RGB"), (int(w * 0.42), int(h * 0.92)))
        f = ImageEnhance.Contrast(f).enhance(1.3)
        base.paste(f, (w - f.width - 40, h - f.height - 20))
    base = _vignette(base, 0.45)
    d = ImageDraw.Draw(base)
    lines = textwrap.wrap(text.upper(), 13)[:3]
    y = h - 60 - len(lines) * 112
    for i, ln in enumerate(lines):
        d.text((50, y), ln, font=title_font(108), fill=(255, 214, 0) if i == len(lines) - 1 else (255, 255, 255),
               stroke_width=7, stroke_fill=(0, 0, 0))
        y += 112
    if stamp:
        sf = title_font(74)
        tw = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(stamp.upper(), font=sf))
        st = Image.new("RGBA", (tw + 70, 150), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        sd.rounded_rectangle([6, 6, st.width - 6, 144], radius=14, outline=(220, 30, 40, 255), width=9)
        sd.text((st.width // 2, 78), stamp.upper(), font=sf, fill=(220, 30, 40, 255), anchor="mm")
        st = st.rotate(-10, expand=True, resample=Image.BICUBIC)
        base.paste(st, (40, 40), st)
    base.save(out, quality=95)
    return out


def quote_frames(text: str, who: str, folder: Path, fps: int, w: int = 1920, h: int = 1080, cps: float = 22) -> tuple[str, int]:
    """Thẻ trích dẫn: câu nói hiện dần từng chữ giữa màn hình tối, tên người nói phía dưới. Trả về pattern PNG."""
    folder.mkdir(parents=True, exist_ok=True)
    f = title_font(84, False)
    fw = title_font(44)
    lines = textwrap.wrap("“" + text.strip().strip('"“”') + "”", 34)
    full = "\n".join(lines)
    frames = int(len(full) / cps * fps) + int(fps * 0.5)
    if (folder / f"q_{frames - 1:04d}.png").exists():
        return str(folder / "q_%04d.png"), frames
    tmp = Image.new("RGBA", (w, h))
    dd = ImageDraw.Draw(tmp)
    box = dd.multiline_textbbox((0, 0), full, font=f, spacing=18)
    x0, y0 = (w - (box[2] - box[0])) / 2, (h - (box[3] - box[1])) / 2 - 40
    for i in range(frames):
        k = min(len(full), int(i * cps / fps) + 1)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.multiline_text((x0, y0), full[:k], font=f, fill=(236, 232, 224, 255), spacing=18)
        if k >= len(full) and who:
            d.text((w / 2, y0 + (box[3] - box[1]) + 70), "— " + who.upper(), font=fw, fill=RED + (255,), anchor="mt")
        img.save(folder / f"q_{i:04d}.png")
    return str(folder / "q_%04d.png"), frames


# =====================================================================
#  PHONG CÁCH "BOLD" (kênh giải thích 2D / kể chuyện bí ẩn): chữ đậm trong hộp vàng, nền minh hoạ
# =====================================================================
YELLOW = (255, 221, 0)


def _wrap_fit(d, text: str, font_fn, max_w: int, size: int, min_size: int = 40, max_lines: int = 3):
    import textwrap as _tw

    while size >= min_size:
        f = font_fn(size)
        for width in range(10, 40):
            lines = _tw.wrap(text, width)
            if len(lines) <= max_lines and all(d.textlength(ln, font=f) <= max_w for ln in lines):
                return f, lines, size
        size -= 6
    f = font_fn(min_size)
    return f, _tw.wrap(text, 18)[:max_lines], min_size


def bold_card(line1: str, line2: str, out: Path, bg: Path | None, w: int = 1920, h: int = 1080,
              dark: bool = False, seed: int = 0) -> Path:
    """Thẻ tiêu đề/chương: nền là minh hoạ (làm mờ nhẹ) + hộp chữ đậm.
    light: hộp vàng chữ đen (kiểu 'Psychology of GEN X') | dark: chữ trắng + đỏ trên nền đen (kiểu 'DON'T LOOK UP')."""
    W, H = int(w * 1.5), int(h * 1.5)
    if bg and Path(bg).exists():
        with Image.open(bg) as im:
            base = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        base = base.filter(ImageFilter.GaussianBlur(6))
        base = ImageEnhance.Brightness(base).enhance(0.35 if dark else 0.85)
    else:
        base = Image.new("RGB", (W, H), (8, 8, 8) if dark else (245, 240, 228))
    d = ImageDraw.Draw(base)
    f2, lines, size2 = _wrap_fit(d, line2.upper(), title_font, int(W * 0.7), int(H * 0.15))
    lh = int(size2 * 1.12)
    block_h = lh * len(lines)
    f1 = title_font(int(H * 0.055))
    y = (H - block_h) // 2 + int(H * 0.04)
    if dark:
        if line1:
            _center_text(d, W, y - int(H * 0.1), line1.upper(), f1, (235, 235, 235))
        for i, ln in enumerate(lines):
            col = (255, 255, 255) if i < len(lines) - 1 else (225, 30, 40)
            tw = d.textlength(ln, font=f2)
            d.text(((W - tw) / 2, y + i * lh), ln, font=f2, fill=col, stroke_width=4, stroke_fill=(0, 0, 0))
    else:
        tw = max(d.textlength(ln, font=f2) for ln in lines)
        pad = int(H * 0.04)
        x0, y0 = (W - tw) / 2 - pad, y - pad
        box = Image.new("RGBA", (int(tw + 2 * pad), int(block_h + 2 * pad)), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle([0, 0, box.width - 1, box.height - 1], radius=int(pad * 0.9),
                                              fill=YELLOW + (255,))
        rot = box.rotate(random.Random(seed).uniform(-2.5, 2.5), resample=Image.BICUBIC, expand=True)
        sh = Image.new("RGBA", rot.size, (0, 0, 0, 0))
        sh.putalpha(rot.split()[3].point(lambda a: 120 if a else 0))
        base = base.convert("RGBA")
        base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)), (int(x0) + 12, int(y0) + 16))
        base.alpha_composite(rot, (int(x0 - (rot.width - box.width) / 2), int(y0 - (rot.height - box.height) / 2)))
        d = ImageDraw.Draw(base)
        for i, ln in enumerate(lines):
            lw = d.textlength(ln, font=f2)
            d.text(((W - lw) / 2, y + i * lh), ln, font=f2, fill=(15, 15, 15))
        if line1:
            pill_f = title_font(int(H * 0.045))
            pw = d.textlength(line1.upper(), font=pill_f) + int(H * 0.06)
            px, py = (W - pw) / 2, y0 - int(H * 0.11)
            d.rounded_rectangle([px, py, px + pw, py + int(H * 0.075)], radius=int(H * 0.035), fill=(20, 20, 20))
            _center_text(d, W, int(py + H * 0.012), line1.upper(), pill_f, (255, 255, 255))
        base = base.convert("RGB")
    base.save(out, quality=93)
    return out


def bold_thumbnail(bg: Path | None, text: str, out: Path, dark: bool = False) -> Path:
    """Thumbnail kiểu kênh giải thích: minh hoạ full khung + chữ đậm trong hộp vàng (hoặc trắng/đỏ trên nền tối)."""
    w, h = 1280, 720
    if bg and Path(bg).exists():
        with Image.open(bg) as im:
            base = ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)
        base = ImageEnhance.Color(base).enhance(1.15)
        if dark:
            base = ImageEnhance.Brightness(base).enhance(0.7)
    else:
        base = Image.new("RGB", (w, h), (10, 10, 10) if dark else (245, 240, 228))
    d = ImageDraw.Draw(base)
    f, lines, size = _wrap_fit(d, text.upper(), title_font, int(w * 0.48), 120, 50, 3)
    lh = int(size * 1.1)
    x, y = 50, int(h * 0.5 - lh * len(lines) / 2)
    if dark:
        for i, ln in enumerate(lines):
            d.text((x, y + i * lh), ln, font=f, fill=(255, 255, 255) if i < len(lines) - 1 else (230, 30, 40),
                   stroke_width=6, stroke_fill=(0, 0, 0))
    else:
        tw = max(d.textlength(ln, font=f) for ln in lines)
        d.rounded_rectangle([x - 24, y - 20, x + tw + 24, y + lh * len(lines) + 10], radius=26, fill=YELLOW,
                            outline=(20, 20, 20), width=5)
        for i, ln in enumerate(lines):
            d.text((x, y + i * lh), ln, font=f, fill=(15, 15, 15))
    base.save(out, quality=95)
    return out


# =====================================================================
#  SƠ ĐỒ / BIỂU ĐỒ dựng từ số liệu trong storyboard (sửa số trong script.json -> sơ đồ đổi theo)
# =====================================================================

def fmt_num(v: float, unit: str = "", lang: str = "vi") -> str:
    if abs(v) >= 1000:
        s = f"{v:,.0f}"
        s = s.replace(",", ".") if lang == "vi" else s
    else:
        s = f"{v:g}".replace(".", ",") if lang == "vi" else f"{v:g}"
    u = unit.strip()
    if u.upper() in ("USD", "$"):
        return f"${s}" if lang != "vi" else f"{s} USD"
    return f"{s} {u}".strip()


def _diagram_base(W: int, H: int, dark: bool, title: str):
    base = Image.new("RGB", (W, H), (12, 16, 24) if dark else (247, 243, 233))
    d = ImageDraw.Draw(base)
    if title:
        f = title_font(int(H * 0.065))
        d.text((int(W * 0.06), int(H * 0.06)), title.upper(), font=f, fill=(240, 240, 240) if dark else (20, 20, 20))
        d.rectangle([int(W * 0.06), int(H * 0.06) + int(H * 0.085), int(W * 0.06) + int(W * 0.12),
                     int(H * 0.06) + int(H * 0.095)], fill=YELLOW)
    return base, d


def size_compare(subject: str, size_m: float, out: Path, W: int = 2880, H: int = 1620, dark: bool = True,
                 look: dict | None = None, ref_h: float = 1.8, ref_label: str = "Thợ lặn 1,8 m") -> Path:
    """So sánh kích thước sinh vật với thợ lặn (đúng tỉ lệ)."""
    from .mascot import draw_mascot

    base = Image.new("RGB", (W, H), (0, 0, 0))
    top, bot = (16, 70, 120), (3, 12, 30)  # nền nước sâu
    grad = Image.linear_gradient("L").resize((W, H))
    base = Image.composite(Image.new("RGB", (W, H), bot), Image.new("RGB", (W, H), top), grad)
    d = ImageDraw.Draw(base)
    f = title_font(int(H * 0.05))
    size_m = max(0.05, float(size_m or 1))
    span = max(size_m, ref_h) * 1.25
    px_per_m = (W * 0.8) / span
    ground = int(H * 0.8)
    x0 = int(W * 0.08)
    for m in range(0, int(span) + 1):  # thước đo
        x = x0 + m * px_per_m
        if x > W * 0.92:
            break
        d.line([x, ground + 10, x, ground + (40 if m % 5 == 0 else 22)], fill=(200, 220, 240), width=4)
        if m % (1 if span < 12 else 5) == 0:
            d.text((x - 10, ground + 48), f"{m} m", font=title_font(int(H * 0.028), False), fill=(200, 220, 240))
    d.line([x0, ground + 10, W * 0.92, ground + 10], fill=(200, 220, 240), width=4)
    # sinh vật: thân thuôn + vây đuôi, dài đúng tỉ lệ
    L = size_m * px_per_m
    bh = max(30, L * 0.22)
    cx0 = x0
    cy = ground - bh * 0.9
    body = [cx0 + L * 0.08, cy - bh / 2, cx0 + L * 0.85, cy + bh / 2]
    d.ellipse(body, fill=(70, 95, 120), outline=(210, 230, 245), width=5)
    d.polygon([(cx0 + L * 0.8, cy), (cx0 + L, cy - bh * 0.7), (cx0 + L * 0.93, cy), (cx0 + L, cy + bh * 0.5)],
              fill=(70, 95, 120), outline=(210, 230, 245))
    d.polygon([(cx0 + L * 0.4, cy - bh / 2), (cx0 + L * 0.5, cy - bh * 1.1), (cx0 + L * 0.58, cy - bh / 2)],
              fill=(70, 95, 120), outline=(210, 230, 245))
    d.ellipse([cx0 + L * 0.15, cy - bh * 0.12, cx0 + L * 0.15 + bh * 0.12, cy], fill=(240, 240, 240))
    d.text((cx0 + L * 0.1, cy - bh / 2 - H * 0.09), f"{subject} ~ {fmt_num(size_m, 'm')}", font=f, fill=(255, 255, 255))
    # thợ lặn (nhân vật brand) cao ref_h
    dh = int(ref_h * px_per_m)
    diver = draw_mascot("surprised", "stand", "left", look, max(60, int(dh * 1.25)))
    dx = int(min(W * 0.9 - diver.width, cx0 + L + W * 0.03))
    base.paste(diver, (dx, ground - diver.height + 10), diver)
    d.text((dx - 10, ground - diver.height - H * 0.06), ref_label, font=title_font(int(H * 0.035)), fill=YELLOW)
    base.save(out, quality=92)
    return out


def depth_chart(subject: str, depth_m: float, out: Path, W: int = 2880, H: int = 1620) -> Path:
    """Bản đồ độ sâu đại dương với các tầng nước và vị trí sinh vật."""
    zones = [(0, 200, "Vùng nắng"), (200, 1000, "Vùng chạng vạng"), (1000, 4000, "Vùng nửa đêm"),
             (4000, 6000, "Vùng biển thẳm"), (6000, 11000, "Vùng rãnh sâu")]
    base = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(base)
    top, bot = int(H * 0.06), int(H * 0.96)

    def y_of(m):  # thang căn bậc hai để vùng nông không bị bẹp
        return top + (bot - top) * (max(0, m) / 11000) ** 0.5

    for y in range(top, bot):
        t = (y - top) / (bot - top)
        col = (int(40 * (1 - t) ** 2), int(140 * (1 - t) ** 1.6 + 5), int(200 * (1 - t) + 15))
        d.line([0, y, W, y], fill=col)
    d.rectangle([0, 0, W, top], fill=(170, 210, 235))
    f = title_font(int(H * 0.034), False)
    for a, b, name in zones:
        ya = y_of(a)
        d.line([W * 0.05, ya, W * 0.95, ya], fill=(255, 255, 255), width=2)
        d.text((W * 0.06, ya + 8), f"{name}  {fmt_num(a, 'm')} – {fmt_num(b, 'm')}", font=f, fill=(230, 240, 250))
    for m, lab in ((40, "Giới hạn lặn giải trí ~40 m"), (332, "Kỷ lục lặn bình khí ~332 m")):
        y = y_of(m)
        d.line([W * 0.55, y, W * 0.95, y], fill=(255, 255, 255), width=2)
        d.text((W * 0.56, y + 4), lab, font=title_font(int(H * 0.026), False), fill=(255, 255, 255))
    if depth_m:
        y = y_of(depth_m)
        d.ellipse([W * 0.42 - 26, y - 26, W * 0.42 + 26, y + 26], fill=(220, 30, 40), outline=(255, 255, 255), width=5)
        d.line([W * 0.42 + 26, y, W * 0.5, y], fill=(220, 30, 40), width=6)
        d.text((W * 0.5 + 10, y - H * 0.03), f"{subject}: ~{fmt_num(depth_m, 'm')}", font=title_font(int(H * 0.045)),
               fill=YELLOW)
    base.save(out, quality=92)
    return out


def figures_chart(figures: list[dict], out: Path, title: str = "", W: int = 2880, H: int = 1620,
                  dark: bool = False, kind: str = "cost_breakdown", lang: str = "vi") -> Path:
    """Biểu đồ thanh ngang từ figures (label, value, unit). Số chưa xác minh có dấu ⚠."""
    base, d = _diagram_base(W, H, dark, title)
    figs = [f for f in figures if isinstance(f.get("value"), (int, float))]
    if not figs:
        d.text((W * 0.1, H * 0.5), "(chưa có số liệu)", font=title_font(int(H * 0.05)), fill=(150, 150, 150))
        base.save(out, quality=92)
        return out
    vmax = max(abs(f["value"]) for f in figs) or 1
    n = len(figs)
    top, bottom = H * 0.24, H * 0.80  # chừa dải dưới cho phụ đề
    row = (bottom - top) / n
    fl = title_font(int(min(row * 0.38, H * 0.045)), False)
    fv = title_font(int(min(row * 0.42, H * 0.05)))
    palette = [(255, 196, 0), (90, 170, 230), (120, 200, 120), (240, 130, 90), (180, 140, 220), (100, 200, 200)]
    txt = (235, 235, 235) if dark else (25, 25, 25)
    for i, f in enumerate(figs):
        y = top + i * row
        label = f["label"] + ("" if f.get("verified", True) else " *")
        d.text((W * 0.06, y + row * 0.05), label, font=fl, fill=txt)
        bw = (W * 0.62) * abs(f["value"]) / vmax
        d.rounded_rectangle([W * 0.06, y + row * 0.45, W * 0.06 + max(bw, 12), y + row * 0.85], radius=int(row * 0.15),
                            fill=palette[i % len(palette)], outline=(20, 20, 20), width=3)
        d.text((W * 0.06 + max(bw, 12) + 24, y + row * 0.42), fmt_num(f["value"], f.get("unit", ""), lang), font=fv,
               fill=txt)
    _unverified_note(d, figs, W, H, txt)
    base.save(out, quality=92)
    return out


def _unverified_note(d, figs, W, H, color):
    if any(not f.get("verified", True) for f in figs):
        d.text((W * 0.06, H * 0.175), "* Số giả định / chưa xác minh - xem nguồn & giả định trong mô tả video",
               font=title_font(int(H * 0.026), False), fill=color)


def rent_vs_buy(figures: list[dict], out: Path, title: str = "", W: int = 2880, H: int = 1620,
                lang: str = "vi") -> Path:
    """Chia đôi màn hình: các khoản 'Thuê: ...' bên trái, 'Mua: ...' bên phải (theo tiền tố label)."""
    base, d = _diagram_base(W, H, False, title)
    sides = {"THUÊ": [], "MUA": []}
    for f in figures:
        lab = f.get("label", "")
        key = "THUÊ" if lab.lower().startswith(("thuê", "rent")) else "MUA" if lab.lower().startswith(("mua", "buy")) else None
        if key:
            sides[key].append(f)
    d.line([W / 2, H * 0.22, W / 2, H * 0.84], fill=(30, 30, 30), width=6)
    for i, (name, items) in enumerate(sides.items()):
        x = W * (0.07 if i == 0 else 0.55)
        pill_w = d.textlength(name, font=title_font(int(H * 0.06))) + 60
        d.rounded_rectangle([x, H * 0.22, x + pill_w, H * 0.31], radius=30, fill=YELLOW if i else (90, 170, 230),
                            outline=(20, 20, 20), width=4)
        d.text((x + 30, H * 0.225), name, font=title_font(int(H * 0.06)), fill=(15, 15, 15))
        y = H * 0.36
        total = 0.0
        for f in items:
            lab = f["label"].split(":", 1)[-1].strip() + ("" if f.get("verified", True) else " *")
            d.text((x, y), lab, font=title_font(int(H * 0.038), False), fill=(30, 30, 30))
            val = fmt_num(f["value"], f.get("unit", ""), lang)
            d.text((x + W * 0.36 - d.textlength(val, font=title_font(int(H * 0.04))), y), val,
                   font=title_font(int(H * 0.04)), fill=(15, 15, 15))
            total += f["value"] if "tổng" not in f["label"].lower() else 0
            y += H * 0.075
        if items:
            unit = items[0].get("unit", "")
            d.line([x, y + 6, x + W * 0.36, y + 6], fill=(30, 30, 30), width=4)
            tv = fmt_num(total, unit, lang)
            ft = title_font(int(H * 0.05))
            d.text((x, y + 20), "TỔNG", font=ft, fill=(15, 15, 15))
            d.text((x + W * 0.36 - d.textlength(tv, font=ft), y + 20), tv, font=ft, fill=(200, 30, 40))
    _unverified_note(d, [f for v in sides.values() for f in v], W, H, (30, 30, 30))
    base.save(out, quality=92)
    return out

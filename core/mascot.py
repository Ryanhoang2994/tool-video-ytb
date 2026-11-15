"""Nhân vật linh vật 2D vẽ bằng code -> giống hệt nhau ở mọi cảnh (AI không làm được điều này).

Kiểu: đầu tròn trắng viền đen, mắt chấm, lông mày đơn giản (giống phong cách kênh giải thích 2D).
Thiết kế lưu trong brand kit (brand/<tên>.yaml): màu áo, màu quần, màu da/đầu, độ dày nét...
  expression: neutral | happy | smile | worried | sad | surprised | thinking | smug | angry | nervous | scared
  pose:       stand | wave | think | point | shrug | hold | cheer | sit
  facing:     left | right
Kèm: bong bóng suy nghĩ / lời nói, nhãn từ khoá (chữ đậm hộp vàng), và màn "bên ngoài vs bên trong".
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .util import ROOT

DEFAULT_LOOK = {
    "head": [252, 252, 250],
    "outline": [20, 20, 20],
    "shirt": [138, 181, 90],      # áo len xanh lá
    "pants": [120, 92, 66],
    "shoes": [40, 40, 40],
    "accessory": "",              # "" | "glasses" | "cap" | "scarf"
    "accessory_color": [200, 40, 40],
    "line": 10,
}

EXPRESSIONS = ["neutral", "happy", "smile", "worried", "sad", "surprised", "thinking", "smug", "angry",
               "nervous", "scared", "tired", "crying", "anxious", "panic", "empty", "determined", "relieved", "smirk",
               "grin"]
POSES = ["stand", "wave", "think", "point", "shrug", "hold", "cheer", "sit", "phone", "hug", "cover", "slump"]
INTENSE = {"crying", "panic", "anxious", "tired", "empty", "scared", "smirk", "determined", "relieved", "angry"}
TEAR = (120, 190, 240)
BAG = (150, 120, 165)


def load_look(brand: dict | None) -> dict:
    look = dict(DEFAULT_LOOK)
    look.update((brand or {}).get("mascot", {}) or {})
    return look


def _c(v):
    return tuple(v) if isinstance(v, (list, tuple)) else v


def _limb(d: ImageDraw.ImageDraw, p0, angle_deg: float, length: float, w: int, fill, outline, line: int):
    a = math.radians(angle_deg)
    p1 = (p0[0] + length * math.cos(a), p0[1] + length * math.sin(a))
    d.line([p0, p1], fill=outline, width=w + 2 * line, joint="curve")
    d.line([p0, p1], fill=fill, width=w, joint="curve")
    return p1


def _hand(d, p, r, look):
    line = look["line"]
    d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=_c(look["head"]), outline=_c(look["outline"]),
              width=line)


def draw_mascot(expression: str = "neutral", pose: str = "stand", facing: str = "right",
                look: dict | None = None, size: int = 1200, blink: bool = False) -> Image.Image:
    """Trả về ảnh RGBA (rộng = 0.8*size, cao = size) của nhân vật."""
    look = look or DEFAULT_LOOK
    S = 1000  # vẽ trên khung chuẩn 800x1000 rồi phóng
    W, H = 800, 1000
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    line = look["line"]
    ol = _c(look["outline"])
    headc = _c(look["head"])
    cx = W / 2
    sit = pose == "sit"
    # --- chân ---
    hip_y = 760 if not sit else 700
    leg_len = 190 if not sit else 110
    for dx in (-55, 55):
        top = (cx + dx, hip_y)
        bot = (cx + dx * (1.6 if sit else 1.0), hip_y + leg_len)
        d.line([top, bot], fill=ol, width=78 + 2 * line)
        d.line([top, bot], fill=_c(look["pants"]), width=78)
        d.rounded_rectangle([bot[0] - 52, bot[1] - 18, bot[0] + 62, bot[1] + 30], radius=22, fill=_c(look["shoes"]),
                            outline=ol, width=line)
    # --- thân (áo len) ---
    body = [cx - 165, 470, cx + 165, hip_y + 40]
    d.rounded_rectangle(body, radius=110, fill=_c(look["shirt"]), outline=ol, width=line)
    d.arc([cx - 80, 455, cx + 80, 530], 0, 180, fill=ol, width=line)  # cổ áo
    # --- tay theo tư thế ---
    shL, shR = (cx - 140, 540), (cx + 140, 540)
    arms = {  # (góc tay trái, góc tay phải) theo độ; 90 = thẳng xuống
        "stand": (105, 75), "wave": (110, -60), "think": (110, -150), "point": (110, -10),
        "shrug": (200, -20), "hold": (60, 120), "cheer": (-120, -60), "sit": (80, 100), "slump": (95, 85),
    }
    aL, aR = arms.get(pose, arms["stand"])
    shirt = _c(look["shirt"])
    hy = 270 + (45 if pose == "slump" else 0)  # gục đầu
    hand_l = hand_r = None
    late_hands = []
    if pose in ("phone", "hug", "cover"):
        tgt = {"phone": [(cx - 70, 640), (cx + 70, 640)],
               "hug": [(cx + 95, 620), (cx - 95, 585)],
               "cover": [(cx - 95, hy + 20), (cx + 95, hy + 20)]}[pose]
        for sh_, t_ in ((shL, tgt[0]), (shR, tgt[1])):
            if pose == "cover":  # khuỷu tay ra ngoài, bàn tay che mặt
                el = (sh_[0] + (-90 if sh_[0] < cx else 90), sh_[1] + 150)
                _limb(d, sh_, math.degrees(math.atan2(el[1] - sh_[1], el[0] - sh_[0])), math.dist(sh_, el), 62, shirt, ol, line)
                _limb(d, el, math.degrees(math.atan2(t_[1] - el[1], t_[0] - el[0])), math.dist(el, t_), 62, shirt, ol, line)
            else:
                _limb(d, sh_, math.degrees(math.atan2(t_[1] - sh_[1], t_[0] - sh_[0])), math.dist(sh_, t_), 62, shirt, ol, line)
            late_hands.append(t_)
        if pose == "phone":  # điện thoại cầm trước ngực (mặt lưng hướng ra người xem)
            d.rounded_rectangle([cx - 62, 520, cx + 62, 700], radius=22, fill=(45, 45, 55), outline=ol, width=line)
            d.ellipse([cx + 18, 540, cx + 40, 562], fill=(90, 90, 100))
    elif pose == "think":  # tay phải gập, bàn tay đặt dưới cằm
        e = _limb(d, shR, 60, 150, 62, shirt, ol, line)
        chin = (cx + 55, 470)
        ang = math.degrees(math.atan2(chin[1] - e[1], chin[0] - e[0]))
        ln = math.hypot(chin[0] - e[0], chin[1] - e[1])
        hand_r = _limb(d, e, ang, ln, 62, shirt, ol, line)
    else:
        hand_r = _limb(d, shR, aR, 230, 62, shirt, ol, line)
    if hand_r is not None or pose not in ("phone", "hug", "cover"):
        hand_l = _limb(d, shL, aL, 230, 62, shirt, ol, line)
        _hand(d, hand_l, 40, look)
    if pose in ("phone", "hug"):
        for hp in late_hands:
            _hand(d, hp, 40, look)
    # --- đầu ---
    hr = 255
    d.ellipse([cx - hr, hy - hr, cx + hr, hy + hr], fill=headc, outline=ol, width=line + 2)
    _face(d, cx, hy, hr, expression, look, blink)
    acc = look.get("accessory", "")
    if acc == "glasses":
        for dx in (-85, 85):
            d.ellipse([cx + dx - 58, hy - 40, cx + dx + 58, hy + 50], outline=ol, width=line)
        d.line([cx - 27, hy, cx + 27, hy], fill=ol, width=line)
    elif acc == "cap":
        d.chord([cx - hr + 15, hy - hr - 10, cx + hr - 15, hy + 60], 180, 360, fill=_c(look["accessory_color"]),
                outline=ol, width=line)
        d.rounded_rectangle([cx - 20, hy - 70, cx + hr + 120, hy - 30], radius=18,
                            fill=_c(look["accessory_color"]), outline=ol, width=line)
    elif acc == "scarf":
        d.rounded_rectangle([cx - 150, 455, cx + 150, 525], radius=30, fill=_c(look["accessory_color"]), outline=ol,
                            width=line)
    if hand_r is not None:
        _hand(d, hand_r, 40, look)  # tay phải vẽ sau cùng (đè lên mặt khi chống cằm)
    if pose == "cover":
        for i_, hp in enumerate(late_hands):  # lòng bàn tay + 4 ngón che mặt
            sx = -1 if i_ == 0 else 1
            x0, y0 = hp[0] + sx * 15, hp[1] + 25
            for f_ in range(4):
                fx = x0 - 45 + f_ * 30
                d.rounded_rectangle([fx - 15, y0 - 115 + abs(f_ - 1.5) * 12, fx + 15, y0], radius=15, fill=headc,
                                    outline=ol, width=line - 2)
            d.rounded_rectangle([x0 - 62, y0 - 50, x0 + 62, y0 + 55], radius=40, fill=headc, outline=ol, width=line)
    if facing == "left":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    scale = size / S
    return img.resize((int(W * scale), int(H * scale)), Image.LANCZOS)


def _face(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, exp: str, look: dict, blink: bool = False):
    ol = _c(look["outline"])
    line = look["line"]
    ex, ey = 85, cy - 5  # vị trí mắt
    lx = 18  # mặt hơi nhìn sang phải (hướng facing)
    head = _c(look["head"])
    closed_happy = exp in ("happy", "cheer", "relieved", "grin")
    # ----- mắt -----
    for side, dx in ((-1, -ex), (1, ex)):
        x0 = cx + dx + lx
        if blink and not closed_happy:
            d.line([x0 - 30, ey + 4, x0 + 30, ey + 4], fill=ol, width=line + 2)
        elif exp in ("happy", "cheer", "grin"):
            d.arc([x0 - 30, ey - 22, x0 + 30, ey + 28], 200, 340, fill=ol, width=line + 2)
        elif exp == "relieved":  # mắt nhắm cong xuống, thư thái
            d.arc([x0 - 30, ey - 30, x0 + 30, ey + 12], 20, 160, fill=ol, width=line + 2)
        elif exp == "crying":  # mắt nhắm chặt + nước mắt
            d.arc([x0 - 30, ey - 10, x0 + 30, ey + 30], 200, 340, fill=ol, width=line + 2)
        elif exp in ("smug", "smirk", "tired", "empty"):  # mí mắt sụp nửa chừng
            d.ellipse([x0 - 20, ey - 14, x0 + 20, ey + 22], fill=ol)
            lid = ey + (4 if exp != "empty" else 8)
            d.rectangle([x0 - 32, ey - 40, x0 + 32, lid], fill=head)
            d.line([x0 - 30, lid, x0 + 30, lid], fill=ol, width=line + 1)
        elif exp in ("anxious", "panic", "surprised", "scared"):  # mắt tròn to, con ngươi nhỏ
            er = 40 if exp == "panic" else 33
            d.ellipse([x0 - er, ey - er, x0 + er, ey + er], fill=(255, 255, 255), outline=ol, width=line)
            pr = 9 if exp in ("panic", "anxious") else 15
            d.ellipse([x0 - pr + 4, ey - pr + 2, x0 + pr + 4, ey + pr + 2], fill=ol)
        else:
            er = 15
            d.ellipse([x0 - er, ey - er, x0 + er, ey + er], fill=ol)
        if exp in ("tired", "empty", "panic", "crying"):  # quầng thâm
            d.arc([x0 - 34, ey + 14, x0 + 34, ey + 48], 20, 160, fill=BAG, width=line)
    # ----- lông mày -----
    by = ey - 62
    brows = {
        "neutral": (0, 0), "happy": (-6, 6), "smile": (-4, 4), "worried": (18, -18), "sad": (16, -16),
        "surprised": (-10, 10), "thinking": (12, 6), "smug": (-14, 0), "angry": (-22, 22), "nervous": (16, -16),
        "scared": (20, -20), "tired": (6, -6), "crying": (22, -22), "anxious": (20, -20), "panic": (26, -26),
        "empty": (0, 0), "determined": (-16, 16), "relieved": (10, -10), "smirk": (-18, -4), "grin": (-20, 20),
    }
    tl, tr = brows.get(exp, (0, 0))
    lift = {"panic": 22, "surprised": 14, "smirk": 0}.get(exp, 0)
    for dx, tilt in ((-ex, tl), (ex, tr)):
        x0, x1 = cx + dx - 34 + lx, cx + dx + 34 + lx
        inner_up = tilt if dx < 0 else -tilt
        extra = 26 if (exp == "smirk" and dx > 0) else 0  # nhướng 1 bên mày
        yb = by - lift - extra
        d.line([x0, yb - (0 if dx < 0 else inner_up), x1, yb - (inner_up if dx < 0 else 0)], fill=ol, width=line + 2)
    # ----- miệng -----
    my = cy + 95
    mx = cx + lx
    if exp in ("happy", "cheer"):
        d.chord([mx - 70, my - 45, mx + 70, my + 55], 0, 180, fill=(70, 20, 20), outline=ol, width=line)
    elif exp == "grin":  # nụ cười nham hiểm rộng
        d.chord([mx - 110, my - 70, mx + 110, my + 60], 10, 170, fill=(30, 10, 10), outline=ol, width=line + 2)
    elif exp in ("smile", "smug", "relieved"):
        d.arc([mx - 55, my - 40, mx + 55, my + 25], 20, 160, fill=ol, width=line + 2)
    elif exp == "smirk":  # cười nhếch 1 bên
        d.line([mx - 45, my + 14, mx + 20, my + 14], fill=ol, width=line + 2)
        d.arc([mx - 10, my - 30, mx + 60, my + 18], 0, 90, fill=ol, width=line + 2)
    elif exp in ("sad", "worried", "scared", "tired"):
        d.arc([mx - 50, my + 5, mx + 50, my + 60], 200, 340, fill=ol, width=line + 2)
    elif exp == "crying":
        d.chord([mx - 50, my, mx + 50, my + 60], 180, 360, fill=(70, 20, 20), outline=ol, width=line)
    elif exp in ("surprised", "panic"):
        rr = 34 if exp == "panic" else 24
        d.ellipse([mx - rr, my - 10, mx + rr, my + 45 + (15 if exp == "panic" else 0)], fill=(70, 20, 20), outline=ol,
                  width=line)
    elif exp == "angry":
        d.line([mx - 45, my + 20, mx + 45, my + 20], fill=ol, width=line + 4)
    elif exp == "determined":
        d.line([mx - 45, my + 18, mx + 45, my + 12], fill=ol, width=line + 3)
    elif exp in ("nervous", "anxious"):  # cười gượng / miệng run
        pts = [(mx - 60 + i * 20, my + (10 if i % 2 else 22)) for i in range(7)]
        d.line(pts, fill=ol, width=line + 1)
    elif exp == "thinking":
        d.line([mx - 30, my + 15, mx + 40, my + 5], fill=ol, width=line + 2)
    elif exp == "empty":
        d.line([mx - 25, my + 15, mx + 25, my + 15], fill=ol, width=line)
    else:
        d.line([mx - 35, my + 12, mx + 35, my + 12], fill=ol, width=line + 2)
    # ----- chi tiết cảm xúc -----
    if exp in ("happy", "smile", "cheer"):  # má hồng
        for dx in (-ex - 30, ex + 30):
            d.ellipse([cx + dx - 30 + lx, ey + 40, cx + dx + 30 + lx, ey + 70], fill=(250, 190, 190))
    if exp in ("nervous", "anxious", "panic"):  # giọt mồ hôi
        drops = [(0.72, -0.45, 1.0)] + ([(-0.75, -0.3, 0.8)] if exp != "nervous" else []) + \
                ([(0.55, -0.7, 0.7)] if exp == "panic" else [])
        for fx, fy, k in drops:
            px, py = cx + r * fx, cy + r * fy
            d.polygon([(px, py - 34 * k), (px - 17 * k, py + 4 * k), (px + 17 * k, py + 4 * k)], fill=TEAR)
            d.ellipse([px - 17 * k, py - 12 * k, px + 17 * k, py + 20 * k], fill=TEAR, outline=ol, width=4)
    if exp == "crying":  # dòng nước mắt
        for dx in (-ex, ex):
            x0 = cx + dx + lx
            d.line([x0, ey + 22, x0 - 6, ey + 150], fill=TEAR, width=18)
            d.ellipse([x0 - 20, ey + 140, x0 + 8, ey + 172], fill=TEAR)


# --------------------- bong bóng & nhãn ---------------------

def thought_bubble(text: str, font, max_w: int, kind: str = "thought") -> Image.Image:
    """Bong bóng suy nghĩ (mây) hoặc lời nói (bo góc + đuôi)."""
    import textwrap

    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines = []
    for width in range(12, 40):
        lines = textwrap.wrap(text, width)
        if max(tmp.textlength(ln, font=font) for ln in lines) <= max_w:
            break
    tw = int(max(tmp.textlength(ln, font=font) for ln in lines))
    lh = int(font.size * 1.25)
    bw, bh = tw + 120, lh * len(lines) + 90
    img = Image.new("RGBA", (bw + 80, bh + 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "thought":
        for i in range(10):  # mép mây
            a = 2 * math.pi * i / 10
            px, py = 40 + bw / 2 + (bw / 2 - 30) * math.cos(a), bh / 2 + (bh / 2 - 22) * math.sin(a)
            d.ellipse([px - 55, py - 45, px + 55, py + 45], fill=(255, 255, 255), outline=(20, 20, 20), width=6)
        d.ellipse([40 + 25, 20, 40 + bw - 25, bh - 20], fill=(255, 255, 255))
        for k, (ox, rr) in enumerate([(70, 22), (40, 14)]):
            d.ellipse([ox - rr, bh + 25 + k * 40 - rr, ox + rr, bh + 25 + k * 40 + rr], fill=(255, 255, 255),
                      outline=(20, 20, 20), width=5)
    else:
        d.rounded_rectangle([40, 0, 40 + bw, bh], radius=40, fill=(255, 255, 255), outline=(20, 20, 20), width=6)
        d.polygon([(110, bh - 6), (70, bh + 70), (170, bh - 6)], fill=(255, 255, 255))
        d.line([(110, bh - 3), (70, bh + 70), (170, bh - 3)], fill=(20, 20, 20), width=6)
    y = (bh - lh * len(lines)) / 2
    for ln in lines:
        lw = d.textlength(ln, font=font)
        d.text((40 + (bw - lw) / 2, y), ln, font=font, fill=(20, 20, 20))
        y += lh
    return img


def keyword_pill(text: str, font, color=(255, 221, 0)) -> Image.Image:
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    tw = int(tmp.textlength(text.upper(), font=font))
    h = int(font.size * 1.6)
    img = Image.new("RGBA", (tw + 70, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 10, tw + 64, h + 10], radius=h // 2, fill=(0, 0, 0, 120))
    d.rounded_rectangle([0, 0, tw + 60, h], radius=h // 2, fill=color + (255,), outline=(20, 20, 20, 255), width=5)
    d.text((30, (h - font.size) / 2 - 4), text.upper(), font=font, fill=(15, 15, 15))
    return img


# --------------------- ghép cảnh ---------------------

def compose_scene(bg: Path | None, out: Path, W: int, H: int, char: dict, look: dict,
                  title_font_fn, seed: int = 0) -> tuple[Path, tuple[float, float]]:
    """Ghép: nền (ảnh AI không có người hoặc màu trơn) + nhân vật + bong bóng (+ chia đôi bên ngoài/bên trong).
    Trả về (file, điểm nhấn = vị trí mặt nhân vật để camera zoom vào)."""
    from PIL import ImageEnhance, ImageOps

    if bg and Path(bg).exists():
        with Image.open(bg) as im:
            base = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
    else:
        base = Image.new("RGB", (W, H), (240, 232, 214))
    base = base.convert("RGBA")
    contrast = char.get("contrast")  # {"outside": "smile", "inside": "worried", "labels": ["BÊN NGOÀI","BÊN TRONG"]}
    if contrast:
        dim = ImageEnhance.Brightness(base.convert("RGB")).enhance(0.55).convert("RGBA")
        base = dim
        labels = contrast.get("labels") or ["BÊN NGOÀI", "BÊN TRONG"]
        d = ImageDraw.Draw(base)
        d.line([(W / 2, H * 0.08), (W / 2, H * 0.92)], fill=(255, 255, 255), width=8)
        f = title_font_fn(int(H * 0.06))
        for i, (exp, lab) in enumerate(((contrast.get("outside", "smile"), labels[0]),
                                        (contrast.get("inside", "worried"), labels[1]))):
            m = draw_mascot(exp, char.get("pose", "stand"), "right" if i == 0 else "left", look, int(H * 0.62))
            x = int(W * (0.25 if i == 0 else 0.75) - m.width / 2)
            base.alpha_composite(m, (x, int(H * 0.95 - m.height)))
            pill = keyword_pill(lab, f)
            base.alpha_composite(pill, (int(W * (0.25 if i == 0 else 0.75) - pill.width / 2), int(H * 0.07)))
        base.convert("RGB").save(out, quality=92)
        return out, (0.5, 0.45)
    pos = char.get("position", "left")
    px = {"left": 0.27, "center": 0.5, "right": 0.73}.get(pos, 0.27)
    facing = char.get("facing") or ("right" if px < 0.5 else "left")
    scale = float(char.get("scale", 0.68))
    m = draw_mascot(char.get("expression", "neutral"), char.get("pose", "stand"), facing, look, int(H * scale))
    shadow = Image.new("RGBA", (int(m.width * 0.7), int(m.height * 0.06)), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([0, 0, shadow.width, shadow.height], fill=(0, 0, 0, 55))
    x = int(W * px - m.width / 2)
    y = int(H * 0.97 - m.height)
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)),
                         (int(W * px - shadow.width / 2), int(H * 0.97 - shadow.height / 1.5)))
    base.alpha_composite(m, (x, y))
    face = (px, (y + m.height * 0.27) / H)
    if char.get("thought"):
        b = thought_bubble(char["thought"], title_font_fn(int(H * 0.07)), int(W * 0.32),
                           "speech" if char.get("bubble") == "speech" else "thought")
        bx = int(W * px + (m.width * 0.25 if px <= 0.5 else -m.width * 0.25 - b.width))
        bx = max(20, min(W - b.width - 20, bx))
        by = max(20, int(y - b.height * 0.55))
        if px > 0.5:
            b = b.transpose(Image.FLIP_LEFT_RIGHT)
            # chữ bị lật -> vẽ lại bong bóng không lật nhưng đuôi giữ bên trái là chấp nhận được
            b = thought_bubble(char["thought"], title_font_fn(int(H * 0.07)), int(W * 0.32),
                               "speech" if char.get("bubble") == "speech" else "thought")
        base.alpha_composite(b, (bx, by))
    base.convert("RGB").save(out, quality=92)
    return out, face


def brand_kit(name: str | None) -> dict:
    """brand/<tên>.yaml: thiết kế nhân vật, bảng màu, font, giọng... dùng chung mọi video của kênh."""
    import yaml

    if not name:
        return {}
    p = ROOT / "brand" / f"{name}.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

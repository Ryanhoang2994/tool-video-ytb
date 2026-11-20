"""Nhấn nhá cảm xúc theo cảnh (hình + tiếng + nhạc).

scene["fx"]:
  shudder  cảnh man rợ / ghê rợn: rung khung, lệch màu RGB, chớp đỏ, nhiễu, tối nhịp tim + tiếng "sting" + nhạc kinh dị
  action   cảnh hành động: camera giật + chớp trắng ở mỗi nhịp, màu gắt hơn + tiếng va đập + nhạc trống dồn dập
  impact   khoảnh khắc chấn động: giật camera + chớp trắng + "boom"
  reveal   tiết lộ: im lặng ngắn trước, rồi "boom" + chớp
  glitch   nhiễu tín hiệu (bí ẩn, công nghệ, ký ức chập chờn)
  jumpscare cú hù doạ: tối + lặng nửa giây, rồi chớp trắng/âm bản, camera lao vào + rung mạnh, tiếng rít chói
  dread    dồn căng thẳng suốt cảnh: tối dần, mất màu, viền đen khép lại, nhịp tim nhanh dần + tiếng trầm rền
  flicker  đèn chập chờn: hình tối/sáng thất thường + tiếng điện rè
  auto     tool tự đoán theo lời đọc (máu, xác, giết... -> shudder; truy đuổi, nổ súng... -> action;
           preset kinh dị (edit.fx_style: horror) còn tự nhận jumpscare / dread / flicker)
  none     không hiệu ứng
scene["emphasis"]: ["cụm từ quan trọng", ...] -> đúng lúc đọc tới: camera giật vào, "boom", chữ đập ra màn hình.
"""
from __future__ import annotations

import re
import unicodedata

SHUDDER = re.compile(
    r"máu|xác chết|thi thể|thi hài|giết|sát hại|sát nhân|chặt|phân xác|đâm (chết|nhiều nhát)|cắt cổ|thảm sát|man rợ|"
    r"ghê rợn|rùng rợn|kinh hoàng|tra tấn|hành hạ|bóp cổ|siết cổ|treo cổ|xé xác|chôn sống|ăn thịt|"
    r"blood|corpse|murder|killed|stabbed|massacre|dismember|tortur|strangl|gruesome", re.I)
ACTION = re.compile(
    r"truy đuổi|đuổi theo|rượt đuổi|nổ súng|bắn (trả|chết|vào|liên tiếp)|đấu súng|lao (ra|vào|tới|xuống)|"
    r"nhảy (xuống|khỏi|ra)|tháo chạy|bỏ chạy|chạy trốn|đột kích|ập vào|xông vào|va chạm|đâm sầm|phát nổ|vụ nổ|"
    r"vật lộn|giằng co|chase|shoot|gunfire|explosion|raid|crash|escape|jumped", re.I)
GLITCH = re.compile(r"mất tích không dấu vết|biến mất|không thể giải thích|tín hiệu|chập chờn|ký ức", re.I)

# --- kinh dị / chuyện ma (chỉ tự nhận khi edit.fx_style = horror) ---
JUMP = re.compile(
    r"đột nhiên|bỗng nhiên|bỗng dưng|bất thình lình|thình lình|bất chợt|ngay sau lưng|ngay phía sau|ngay bên tai|"
    r"vụt (qua|hiện|tắt)|hiện ra ngay|chộp lấy|túm lấy|hét lên|thét lên|gào lên|rú lên|mở bừng mắt|"
    r"suddenly|all at once|out of nowhere|right behind (me|him|her|them)|lunged|grabbed|screamed|shrieked|"
    r"slammed (shut|open)|burst open|snapped open", re.I)
DREAD = re.compile(
    r"tiếng (bước chân|gõ|cào|thở|khóc|cười|thì thầm|rên|kéo lê|cọt kẹt)|thì thầm|thì thào|lạnh (sống lưng|gáy|toát)|"
    r"nổi da gà|sởn gai ốc|rợn người|bóng (đen|người|trắng)|ai đó đang|có (thứ|cái) gì đó|nhìn chằm chằm|"
    r"im lặng đến|tối om|tối đen|cánh cửa (từ từ|hé|khẽ)|không dám (thở|quay|nhìn)|nín thở|"
    r"footsteps|whisper|knocking|scratching|shadow|staring|breathing|something was|someone was|in the dark|"
    r"held (my|his|her) breath|goosebumps|chill ran", re.I)
FLICKER = re.compile(
    r"đèn (chập chờn|nhấp nháy|phụt tắt|vụt tắt|tắt phụt|chớp tắt)|mất điện|cúp điện|bóng đèn (nổ|chớp)|"
    r"lights? (began to |started to )?flicker|lights? went out|power went out|bulb (burst|popped)", re.I)

# --- mọi thể loại: hồi hộp / chấn động / tiết lộ ---
TENSION = re.compile(
    r"không ai (biết|ngờ|hay)|chưa ai (biết|ngờ)|chỉ còn (vài|\d+|một|hai|ba|mấy) (phút|giây|giờ)|từng (giây|phút)|"
    r"đếm ngược|nín thở|im lặng (bao trùm|đáng sợ|chết chóc)|mỗi lúc một (gần|lớn|nhanh)|không còn đường|"
    r"no one (knew|noticed|realized)|nobody (knew|noticed)|had no idea|little did|minutes (before|away|left)|"
    r"seconds (before|away|left)|the clock|running out|closer and closer|dead silence|held (its|their) breath|"
    r"what (he|she|they) (didn't|did not) know|too late", re.I)
IMPACT = re.compile(
    r"sụp đổ|đổ sập|phát nổ|nổ tung|đâm (vào|sầm)|lao xuống|rơi xuống|vỡ tung|chìm (xuống|hẳn)|bốc cháy|trúng (đạn|ngư lôi)|"
    r"explod|collaps|crashed|slammed into|struck|detonat|erupted|capsized|torpedo(ed)? hit|burst into flames|"
    r"gave way|snapped|shattered", re.I)
REVEAL = re.compile(
    r"sự thật là|hoá ra|hóa ra|thì ra|thực chất|không phải (là )?tai nạn|"
    r"the truth was|it turned out|turned out to be|in reality|was no accident|had been lying|was never", re.I)

FX_MUSIC = {"shudder": "horror", "action": "action", "jumpscare": "horror", "dread": "tense", "flicker": "horror"}


NEG = re.compile(r"(không|chưa|chẳng|chả|no|not|without)\W+(\w+\W+){0,2}$", re.I)


def _hits(rx: re.Pattern, text: str) -> list[re.Match]:
    """Từ khoá thật sự (bỏ trường hợp phủ định: "không thi thể", "chưa ai bị giết")."""
    return [m for m in rx.finditer(text) if not NEG.search(text[max(0, m.start() - 16):m.start()])]


def detect(scene: dict, cfg: dict | None = None) -> str:
    fx = (scene.get("fx") or "auto").lower()
    if fx != "auto":
        return fx
    if (cfg or {}).get("edit", {}).get("auto_fx", True) is False:
        return "none"
    t = scene.get("narration", "")
    if (cfg or {}).get("edit", {}).get("fx_style") == "horror":
        if _hits(JUMP, t):
            return "jumpscare"
        if _hits(FLICKER, t):
            return "flicker"
        if _hits(SHUDDER, t):
            return "shudder"
        if _hits(DREAD, t):
            return "dread"
    if _hits(SHUDDER, t):
        return "shudder"
    if _hits(ACTION, t):
        return "action"
    if (cfg or {}).get("edit", {}).get("auto_fx_level", 2) >= 2:  # 1 = chỉ shudder/action như bản cũ
        if _hits(IMPACT, t):
            return "impact"
        if _hits(REVEAL, t):
            return "reveal"
        if _hits(TENSION, t):
            return "dread"
    return "none"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower()


def anchors(text: str, wav, dur: float) -> list[list[float]]:
    """Căn chữ <-> thời gian: các dấu câu được ghim vào khoảng lặng thật trong file giọng đọc
    (ffmpeg silencedetect). Trả về [[vị trí ký tự, giây], ...] để nội suy tuyến tính."""
    import subprocess
    from pathlib import Path

    text = _norm(text)
    n = max(1, len(text))
    pts = [[0, 0.0], [n, dur]]
    if not wav or not Path(wav).exists():
        return pts
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", "silencedetect=noise=-38dB:d=0.16",
                        "-f", "null", "-"], capture_output=True, text=True, errors="ignore").stderr
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r)]
    sil = list(zip(st, en))
    speech0 = en[0] if sil and st[0] < 0.05 else 0.0
    speech1 = st[-1] if sil and (len(en) < len(st) or en[-1] >= dur - 0.05) else dur
    inner_sil = [(a, b) for a, b in sil if a > speech0 + 0.1 and b < speech1 - 0.05]
    inner = [((a + b) / 2) for a, b in inner_sil]
    pts = [[0, speech0]]
    used: set[int] = set()
    for m in re.finditer(r"[.,!?;:…]+\s", text + " "):
        b = m.end() - 1
        if b >= n - 1:
            continue
        est = speech0 + (speech1 - speech0) * b / n
        cand = [(abs(t - est), i) for i, t in enumerate(inner) if i not in used and t > pts[-1][1]]
        if cand:
            d_, i = min(cand)
            if d_ < max(0.9, (speech1 - speech0) * 0.15):
                used.add(i)
                pts.append([b, inner_sil[i][0]])       # chữ trước dấu câu kết thúc khi bắt đầu lặng
                pts.append([b + 0.5, inner_sil[i][1]])  # chữ sau bắt đầu khi hết lặng
    pts.append([n, speech1])
    return pts


def at_time(pts: list[list[float]], pos: float) -> float:
    for (p0, t0), (p1, t1) in zip(pts, pts[1:]):
        if p0 <= pos <= p1:
            return t0 + (t1 - t0) * (pos - p0) / max(1e-6, p1 - p0)
    return pts[-1][1]


def accents(scene: dict, fx: str, audio_dur: float, pts: list | None = None) -> list[float]:
    """Thời điểm nhấn (giây, tính từ đầu cảnh) = lúc giọng đọc tới cụm từ (căn theo khoảng lặng thật)."""
    text = _norm(scene.get("narration", ""))
    n = max(1, len(text))
    pts = pts or [[0, 0.0], [n, audio_dur]]
    pos: list[int] = []
    for ph in scene.get("emphasis") or []:
        i = text.find(_norm(ph))
        if i >= 0:
            pos.append(i)
    if fx == "jumpscare":  # đúng 1 cú: ở cụm emphasis đầu tiên, không có thì ở từ "đột nhiên..." hoặc cuối cảnh
        if not pos:
            hit = _hits(JUMP, text)
            # "Đột nhiên, cửa bật mở": từ báo hiệu ở đầu câu -> cú hù rơi vào cuối câu, nơi sự việc xảy ra
            pos = [hit[0].start()] if hit and hit[0].start() > n * 0.35 else [int(n * 0.8)]
        t0 = min(max(round(at_time(pts, pos[0]) + 0.05, 2), 0.7), max(0.7, audio_dur - 0.3))
        return [t0]
    if fx in ("shudder", "action", "glitch"):
        rx = {"shudder": SHUDDER, "action": ACTION, "glitch": GLITCH}[fx]
        pos += [m.start() for m in _hits(rx, text)]
    if fx in ("impact", "reveal") and not pos:
        hit = _hits(IMPACT if fx == "impact" else REVEAL, text)
        pos.append(hit[0].start() if hit and (fx == "impact" or hit[0].start() > n * 0.35) else int(n * 0.6))
    times = sorted({round(at_time(pts, p) + 0.05, 2) for p in pos})
    out: list[float] = []
    for t in times:  # cách nhau tối thiểu 0.9s
        if not out or t - out[-1] >= 0.9:
            out.append(t)
    return out[:6]


def phrases(scene: dict, pts: list) -> list[list]:
    """Các cụm nhấn mạnh (chữ đập ra màn hình) kèm giây xuất hiện."""
    text = _norm(scene.get("narration", ""))
    out = []
    for ph in scene.get("emphasis") or []:
        i = text.find(_norm(ph))
        if i >= 0:
            out.append([ph, round(at_time(pts, i) + 0.05, 2)])
    return out


def post_filters(fx: str, acc: list[float], span: float) -> list[str]:
    """Bộ lọc ffmpeg cho cả đoạn (t = giây trong đoạn)."""
    f: list[str] = []

    def win(a: float, d: float) -> str:
        return f"enable='between(t,{a:.2f},{a + d:.2f})'"

    if fx == "shudder":
        f.append("eq=saturation=0.55:contrast=1.12:brightness='-0.03-0.035*pow(sin(PI*t/0.95),8)':eval=frame")
        for a in acc:
            f.append(f"rgbashift=rh=-14:bh=14:gv=4:{win(a, 0.3)}")
            f.append(f"colorchannelmixer=rr=1.5:gg=0.45:bb=0.45:{win(a, 0.09)}")
            f.append(f"noise=alls=38:allf=t:{win(a, 0.35)}")
            f.append(f"eq=contrast=1.6:saturation=0:{win(a + 0.09, 0.25)}")
    elif fx == "action":
        f.append("eq=contrast=1.08:saturation=1.15")
        for a in acc:
            f.append(f"eq=brightness=0.32:{win(a, 0.06)}")
            f.append(f"rgbashift=rh=-6:bh=6:{win(a, 0.15)}")
    elif fx in ("impact", "reveal"):
        for a in acc:
            f.append(f"eq=brightness=0.4:saturation=0.6:{win(a, 0.07)}")
    elif fx == "jumpscare":
        f.append("eq=saturation=0.7:contrast=1.08")
        for a in acc:
            f.append(f"eq=brightness=-0.16:saturation=0.4:{win(max(0, a - 0.55), 0.55)}")  # tối + lặng trước cú hù
            f.append(f"eq=brightness=0.6:contrast=1.5:{win(a, 0.07)}")                      # chớp trắng
            f.append(f"negate={win(a + 0.07, 0.08)}")                                       # âm bản 2 khung hình
            f.append(f"rgbashift=rh=-26:bh=26:gv=8:{win(a, 0.45)}")
            f.append(f"noise=alls=55:allf=t:{win(a, 0.5)}")
            f.append(f"colorchannelmixer=rr=1.45:gg=0.5:bb=0.5:{win(a + 0.15, 0.12)}")
            f.append(f"eq=contrast=1.45:saturation=0.15:brightness=-0.04:{win(a + 0.27, 0.9)}")
    elif fx == "dread":
        s_ = max(span, 0.5)
        f.append(f"eq=brightness='-0.05*min(1,t/{s_:.2f})-0.03*pow(sin(PI*t/0.9),8)':"
                 f"saturation='1-0.6*min(1,t/{s_:.2f})':contrast=1.1:eval=frame")
        f.append(f"vignette=angle='PI/9+(PI/8)*min(1,t/{s_:.2f})':eval=frame")
        f.append(f"noise=alls=14:allf=t:enable='gt(t,{s_ * 0.5:.2f})'")
    elif fx == "flicker":
        f.append("eq=brightness='-0.34*lt(mod(t*6.7,1),0.13)-0.22*lt(mod(t*2.9+0.37,1),0.09)"
                 "-0.5*lt(mod(t*0.83+0.6,1),0.05)+0.05*lt(mod(t*4.3+0.2,1),0.04)':saturation=0.8:eval=frame")
    elif fx == "glitch":
        f.append("rgbashift=rh=-10:bh=10:enable='lt(mod(t*3.1,1),0.06)'")
        f.append("noise=alls=25:allf=t:enable='lt(mod(t*2.3,1),0.05)'")
    if fx in ("none", "") and acc:  # chỉ có cụm nhấn mạnh: chớp rất nhẹ
        for a in acc:
            f.append(f"eq=brightness=0.12:{win(a, 0.05)}")
    return f


def shake_amount(fx: str) -> float:
    return {"shudder": 0.012, "action": 0.009, "impact": 0.006, "reveal": 0.0, "jumpscare": 0.03}.get(fx, 0.003)


def punch_amount(fx: str) -> float:
    """Camera giật vào bao nhiêu ở mỗi nhịp nhấn (jumpscare: lao thẳng vào mặt)."""
    return {"jumpscare": 0.34, "shudder": 0.09}.get(fx, 0.075)


def emphasis_png(text: str, out, W: int, H: int, style: str = "dark"):
    """Chữ nhấn mạnh đập ra màn hình (nền trong suốt, kích thước khung W x H)."""
    from PIL import Image, ImageDraw, ImageFilter

    from .graphics import title_font

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = int(H * 0.11)
    f = title_font(size)
    t = text.upper()
    while d.textlength(t, font=f) > W * 0.8 and size > 40:
        size -= 6
        f = title_font(size)
    tw = d.textlength(t, font=f)
    x, y = (W - tw) / 2, H * 0.62
    if style == "bold":
        d.rectangle([x - 30, y - 12, x + tw + 30, y + size * 1.15], fill=(255, 221, 0, 255))
        d.text((x, y - size * 0.06), t, font=f, fill=(15, 15, 15))
    elif style == "collage":
        d.rectangle([x - 30, y - 12, x + tw + 30, y + size * 1.15], fill=(200, 36, 36, 255))
        d.text((x, y - size * 0.06), t, font=f, fill=(20, 16, 16))
    else:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((x + 5, y + 6), t, font=f, fill=(0, 0, 0, 220))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        d.text((x, y), t, font=f, fill=(245, 245, 245))
        d.rectangle([x, y + size * 1.12, x + tw, y + size * 1.12 + max(6, size // 12)], fill=(200, 30, 30))
    img.save(out)
    return out


def title_overlay_png(small: str, big: str, out, W: int, H: int, style: str = "dark", kind: str = "chapter"):
    """Tên chương / tiêu đề hiện đè lên cảnh (nền trong suốt) - lời kể vẫn chạy, không ngắt nhịp."""
    from PIL import Image, ImageDraw, ImageFilter

    from .graphics import _wrap_fit, title_font

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    big_size = int(H * (0.12 if kind == "title" else 0.095))
    if style == "collage":
        from . import collage

        f, lines, _ = _wrap_fit(d, big.upper(), title_font, int(W * 0.5), big_size, int(H * 0.06), 3)
        lh = int(f.size * 1.08)
        bw = int(max(d.textlength(ln, font=f) for ln in lines) + W * 0.05)
        red = Image.new("RGBA", (bw, lh * len(lines) + int(H * 0.05)), collage.RED + (255,))
        rd = ImageDraw.Draw(red)
        for i, ln in enumerate(lines):
            rd.text((W * 0.025, H * 0.02 + i * lh), ln, font=f, fill=(20, 16, 16))
        red = collage._torn(red, 3, depth=14)
        x0, y0 = int(W * 0.06), int(H * 0.5 - red.height / 2)
        sh = Image.new("RGBA", red.size, (0, 0, 0, 0))
        sh.putalpha(red.split()[3].point(lambda v: int(v * 0.4)))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (x0 + 12, y0 + 14))
        img.alpha_composite(red, (x0, y0))
        if small:
            ls = collage.label_strip(small.upper(), int(H * 0.04))
            img.alpha_composite(ls, (x0, max(10, y0 - ls.height - 8)))
        img.save(out)
        return out
    # dải tối mờ ngang khung + chữ lớn
    band = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(band)
    bd.rectangle([0, H * 0.3, W, H * 0.72], fill=175)
    band = band.filter(ImageFilter.GaussianBlur(int(H * 0.06)))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dark.putalpha(band)
    img.alpha_composite(dark)
    d = ImageDraw.Draw(img)
    f, lines, size = _wrap_fit(d, big.upper(), title_font, int(W * 0.8), big_size, int(H * 0.06), 2)
    lh = int(size * 1.1)
    y = H * 0.5 - lh * len(lines) / 2 + H * 0.03
    if style == "bold":
        for ln in lines:
            tw = d.textlength(ln, font=f)
            d.rectangle([(W - tw) / 2 - 24, y - 6, (W + tw) / 2 + 24, y + size * 1.1], fill=(255, 221, 0, 255))
            d.text(((W - tw) / 2, y - size * 0.05), ln, font=f, fill=(15, 15, 15))
            y += lh + 12
    else:
        for ln in lines:
            tw = d.textlength(ln, font=f)
            d.text(((W - tw) / 2, y), ln, font=f, fill=(245, 245, 245))
            y += lh
        d.rectangle([W / 2 - W * 0.06, y + 8, W / 2 + W * 0.06, y + 14], fill=(200, 30, 30))
    if small:
        fs = title_font(int(H * 0.035))
        t = small.upper()
        tw = d.textlength(t, font=fs)
        ys = H * 0.5 - lh * len(lines) / 2 - H * 0.05
        d.text(((W - tw) / 2, ys), t, font=fs, fill=(230, 60, 60) if style != "bold" else (255, 255, 255))
    img.save(out)
    return out

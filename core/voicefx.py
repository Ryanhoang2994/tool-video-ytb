"""Diễn xuất giọng đọc theo cảnh + hiệu ứng giọng nhân vật.

delivery (cách đọc của người dẫn chuyện, mọi engine):
  normal  : bình thường
  hushed  : hạ giọng, nói gần mic, chậm lại (trước cú hù, chi tiết rợn người, bí mật)
  tense   : chậm, nén, căng (dồn hồi hộp)
  urgent  : nhanh, dồn dập (truy đuổi, đếm ngược, hỗn loạn)
  grave   : trầm, chậm, nặng (số người chết, kết cục, phán quyết)
  warm    : ấm, chậm nhẹ (hi vọng, kết thúc có hậu, mẹ và bé)
  Engine hỗ trợ sẵn (edge, google) đổi tốc độ/cao độ ngay khi đọc -> tự nhiên hơn; engine khác chỉnh sau khi đọc.
  ElevenLabs eleven_v3 còn nhận "thẻ cảm xúc" ([whispers]...) -> đọc thì thầm thật.

voice_fx (chỉ cho LỜI NHÂN VẬT - câu trích dẫn, không áp lên người dẫn chuyện):
  radio : bộ đàm / buồng lái / đài kiểm soát      phone: điện thoại / cuộc gọi 911 / nghe lén
  tape  : băng ghi âm cũ                            echo : vọng lại (ký ức, hang động, giọng trong đầu)
  ghost : giọng ma (chỉ truyện hư cấu/kinh dị)      none : giữ nguyên
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import run

DELIVERY_ENUM = ["auto", "normal", "hushed", "tense", "urgent", "grave", "warm"]
VOICE_FX_ENUM = ["auto", "none", "radio", "phone", "tape", "echo", "ghost"]

# rate: % tốc độ, pitch: Hz (edge) , gain: dB sau chuẩn hoá, eq: lọc thêm
DELIVERY = {
    "normal": {"rate": 0, "pitch": 0, "gain": 0.0, "eq": ""},
    "hushed": {"rate": -9, "pitch": -3, "gain": -4.0,
               "eq": "equalizer=f=220:t=q:w=1:g=2.5,equalizer=f=4500:t=q:w=1.5:g=-2,lowpass=f=8000"},
    "tense": {"rate": -6, "pitch": -2, "gain": -1.5, "eq": "equalizer=f=180:t=q:w=1:g=1.5"},
    "urgent": {"rate": 8, "pitch": 2, "gain": 1.0, "eq": "equalizer=f=2500:t=q:w=1.2:g=1.5"},
    "grave": {"rate": -10, "pitch": -5, "gain": 0.0, "eq": "equalizer=f=120:t=q:w=1:g=2.5"},
    "warm": {"rate": -3, "pitch": 0, "gain": 0.0,
             "eq": "equalizer=f=200:t=q:w=1:g=1.5,equalizer=f=6500:t=q:w=2:g=-1.5"},
}
ELEVEN_TAGS = {"hushed": "[whispers]", "tense": "[tense]", "urgent": "[urgently]", "grave": "[seriously]",
               "warm": "[warmly]"}

FX_FILTER = {
    "radio": "highpass=f=380,lowpass=f=2700,acompressor=threshold=-26dB:ratio=9:attack=2:release=60:makeup=4,"
             "asoftclip=type=tanh,equalizer=f=1500:t=q:w=1:g=3",
    "phone": "highpass=f=420,lowpass=f=3300,acompressor=threshold=-24dB:ratio=6:attack=3:release=80:makeup=3,"
             "equalizer=f=1800:t=q:w=1:g=2",
    "tape": "highpass=f=110,lowpass=f=4800,vibrato=f=0.7:d=0.12,equalizer=f=300:t=q:w=1:g=2",
    "echo": "aecho=0.85:0.75:170|340:0.38|0.2",
    # giọng ma: hạ giọng + vọng ngược (tiếng "hút vào" trước mỗi chữ) + vọng sau
    "ghost": "asetrate=44100*0.9,aresample=44100,atempo=1.08,areverse,aecho=0.8:0.9:220|410:0.45|0.3,areverse,"
             "aecho=0.8:0.85:120|260:0.35|0.2,lowpass=f=6000",
}

_RADIO = re.compile(r"\b(radio(ed|s)?|transmi(t|tted|ssion)|cockpit|control tower|air traffic|atc|mayday|"
                    r"dispatch(er)?|walkie|co-?pilot|captain said|pilot said|flight engineer|black box|"
                    r"voice recorder)\b|bộ đàm|vô tuyến|buồng lái|đài kiểm soát|điện đàm|hộp đen", re.I)
_PHONE = re.compile(r"\b(911|nine[- ]one[- ]one|phone|telephone|called (the )?police|hotline|operator|voicemail|wiretap(ped)?|"
                    r"intercepted call|on the line)\b|điện thoại|cuộc gọi|tổng đài|gọi cảnh sát", re.I)
_TAPE = re.compile(r"\b(tape|tapes|recording|recorded|dictaphone|cassette|reel-to-reel|confession tape)\b|"
                   r"băng ghi âm|đoạn ghi âm|băng cát", re.I)
_GHOST = re.compile(r"\b(ghost|spirit|apparition|phantom|demon|the voice|whisper(ed|s)?|entity)\b|"
                    r"\bma\b|hồn|vong|oan hồn|giọng nói lạ|thì thầm", re.I)


def auto_delivery(scene: dict, fx: str, cfg: dict) -> str:
    d = (scene.get("delivery") or "auto").strip()
    if d in DELIVERY:
        return d
    if not cfg.get("voice", {}).get("delivery", True):
        return "normal"
    if fx in ("jumpscare", "flicker"):
        return "hushed"
    if fx == "dread":
        return "tense"
    if fx == "action":
        return "urgent"
    if fx in ("shudder", "impact"):
        return "grave"
    mood = scene.get("mood") or ""
    if mood == "sad":
        return "grave"
    if mood in ("hopeful", "dawn", "warm"):
        return "warm"
    return "normal"


def auto_voice_fx(scene: dict, fx: str, cfg: dict, lead: str = "") -> str:
    """lead = lời dẫn ngay trước câu trích (nơi thường nói "anh ta gọi bộ đàm:", "trong băng ghi âm...")."""
    v = (scene.get("voice_fx") or "auto").strip()
    if v in FX_FILTER or v == "none":
        return v
    if not cfg.get("voice", {}).get("voice_fx", True):
        return "none"
    ent = scene.get("entity") or {}
    ctx = " ".join([(lead or scene.get("narration", ""))[-160:], ent.get("role", "")])
    horror = cfg.get("edit", {}).get("fx_style") == "horror"
    if horror and (fx in ("jumpscare", "flicker", "dread") or _GHOST.search(ent.get("role", "") + " " + ent.get("name", ""))):
        if _GHOST.search(ctx):
            return "ghost"
    if _PHONE.search(ctx):
        return "phone"
    if _RADIO.search(ctx):
        return "radio"
    if _TAPE.search(ctx):
        return "tape"
    return "none"


def params(delivery: str, vc: dict) -> dict:
    k = float(vc.get("delivery_strength", 1.0))
    d = DELIVERY.get(delivery, DELIVERY["normal"])
    return {"name": delivery, "rate": round(d["rate"] * k), "pitch": round(d["pitch"] * k),
            "gain": d["gain"] * k, "eq": d["eq"] if k > 0 else "",
            "tag": (vc.get("elevenlabs_tags") or ELEVEN_TAGS).get(delivery, "")}


def edge_rate(base: str, delta: int) -> str:
    m = re.match(r"([+-]?\d+)%", str(base or "+0%"))
    v = (int(m.group(1)) if m else 0) + delta
    return f"{v:+d}%"


def edge_pitch(base: str, delta: int) -> str:
    m = re.match(r"([+-]?\d+)Hz", str(base or "+0Hz"))
    v = (int(m.group(1)) if m else 0) + delta
    return f"{v:+d}Hz"


def post_delivery(path: Path, p: dict, tempo: bool) -> None:
    """Chỉnh giọng sau khi đọc: tốc độ (nếu engine không tự làm), màu giọng, âm lượng tương đối."""
    chain = []
    if tempo and p["rate"]:
        chain.append(f"atempo={1 + p['rate'] / 100:.3f}")
    if tempo and p["pitch"] < 0:  # hạ giọng nhẹ cho engine không có pitch (giữ tốc độ)
        f = 1 + p["pitch"] / 100  # -5 -> 0.95
        chain.append(f"asetrate=44100*{f:.3f},aresample=44100,atempo={1 / f:.3f}")
    if p["eq"]:
        chain.append(p["eq"])
    if chain or p["gain"]:
        # EQ làm to/nhỏ giọng -> chuẩn lại âm lượng rồi mới đặt độ to tương đối của cách đọc (thì thầm nhỏ hơn...)
        chain.append("loudnorm=I=-16:TP=-2")
        if p["gain"]:
            chain.append(f"volume={p['gain']:+.1f}dB")
        _filter(path, ",".join(chain) + ",alimiter=limit=0.89:level=disabled")


def apply_fx(path: Path, kind: str) -> None:
    if kind in FX_FILTER:
        _filter(path, FX_FILTER[kind] + ",loudnorm=I=-17:TP=-1.5")


def _filter(path: Path, af: str) -> None:
    tmp = path.with_name(path.stem + "_vfx.wav")
    run(["ffmpeg", "-y", "-i", str(path), "-af", af, "-ar", "44100", "-ac", "1", str(tmp)])
    tmp.replace(path)


def split_quote(narration: str, quote: str) -> tuple[str, str, str] | None:
    """Tách lời dẫn thành [trước, câu trích, sau] khi câu trích nằm sẵn trong lời dẫn."""
    q = quote.strip().strip('"“”\'‘’ ').rstrip(".!?,")
    if len(q) < 4:
        return None
    m = re.search(re.escape(q), narration, re.I)
    if not m:
        return None
    a, b = m.start(), m.end()
    while b < len(narration) and narration[b] in '.!?,"”’\'':
        b += 1
    while a > 0 and narration[a - 1] in '"“‘\'':
        a -= 1
    before, mid, after = narration[:a].strip(), narration[a:b].strip(), narration[b:].strip()
    mid = mid.strip('"“”\'‘’ ')
    return before, mid, after

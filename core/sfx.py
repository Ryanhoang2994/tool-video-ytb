"""Hiệu ứng âm thanh (SFX) + nhạc nền tự tạo khi bạn chưa có file nhạc.

SFX được gắn tự động theo timeline:
  hit      tiếng "boom" trầm khi hiện thẻ tiêu đề / thẻ chương
  whoosh   tiếng gió lướt khi thẻ tên nhân vật trượt vào
  flash    tiếng màn trập máy ảnh khi chớp trắng (vật chứng, tờ báo)
  type     tiếng gõ máy chữ khi hiện chữ địa danh / thời gian
Muốn dùng âm thanh "xịn" của bạn: đặt file assets/sfx/hit.wav, whoosh.wav, flash.wav, type.wav (tool ưu tiên dùng).
Nhạc nền: bỏ .mp3 vào assets/music/. Nếu trống, tool tự tạo 1 đoạn nhạc nền trầm u tối (drone) để không bị trống.
"""
from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from .util import ROOT, log

SR = 44100
SFX_DIR = ROOT / "assets" / "sfx"
GEN_DIR = ROOT / "assets" / "sfx" / "_gen"


def _write(path: Path, x: np.ndarray, sr: int = SR, ch: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return path


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError(f"{path}: cần WAV 16-bit")
    x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:  # đổi tần số mẫu đơn giản
        idx = np.linspace(0, len(x) - 1, int(len(x) * SR / sr))
        x = np.interp(idx, np.arange(len(x)), x)
    return x


def _lowpass(x: np.ndarray, a: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # 1-pole lowpass (đủ nhanh cho clip ngắn)
        acc += a * (v - acc)
        y[i] = acc
    return y


def _gen_hit() -> np.ndarray:
    t = np.arange(int(SR * 2.2)) / SR
    f = 55 * np.exp(-t * 1.6) + 28  # sụt tần số -> "boom"
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    rng = np.random.default_rng(1)
    noise = _lowpass(rng.standard_normal(len(t)).astype(np.float32), 0.02) * np.exp(-t * 6) * 3
    return (body * 0.9 + noise * 0.4) * 0.9


def _gen_whoosh() -> np.ndarray:
    n = int(SR * 0.9)
    t = np.arange(n) / SR
    rng = np.random.default_rng(2)
    noise = rng.standard_normal(n).astype(np.float32)
    env = np.sin(np.pi * np.clip(t / 0.9, 0, 1)) ** 2
    lo = _lowpass(noise, 0.05)
    hi = noise - _lowpass(noise, 0.25)
    mix = lo * (1 - t / 0.9) * 2 + hi * (t / 0.9) * 0.6
    return mix * env * 0.5


def _gen_flash() -> np.ndarray:
    n = int(SR * 0.35)
    rng = np.random.default_rng(3)
    x = np.zeros(n, np.float32)
    for start, dur, amp in [(0, 0.012, 0.9), (0.06, 0.02, 0.6)]:  # 2 tiếng "tách" của màn trập
        a, b = int(start * SR), int((start + dur) * SR)
        x[a:b] += rng.standard_normal(b - a).astype(np.float32) * amp * np.exp(-np.linspace(0, 6, b - a))
    t = np.arange(n) / SR
    x += (rng.standard_normal(n).astype(np.float32) - _lowpass(rng.standard_normal(n).astype(np.float32), 0.3)) \
        * np.exp(-t * 14) * 0.25  # tiếng "xì" đèn flash
    return x * 0.8


def _gen_riser() -> np.ndarray:
    n = int(SR * 2.4)
    t = np.arange(n) / SR
    rng = np.random.default_rng(4)
    noise = rng.standard_normal(n).astype(np.float32)
    env = (t / t[-1]) ** 2.2
    a = 0.01 + 0.25 * (t / t[-1]) ** 2  # mở dần bộ lọc -> tiếng "vút" tăng dần
    y = np.empty_like(noise)
    acc = 0.0
    for i, v in enumerate(noise):
        acc += a[i] * (v - acc)
        y[i] = acc
    tone = np.sin(2 * np.pi * np.cumsum(80 + 220 * (t / t[-1]) ** 2) / SR) * 0.25
    out = (y * 2.5 + tone) * env
    out[-int(SR * 0.03):] *= np.linspace(1, 0, int(SR * 0.03))
    return out


def _gen_rain(seconds: float = 20.0) -> np.ndarray:
    n = int(SR * seconds)
    rng = np.random.default_rng(5)
    noise = rng.standard_normal(n).astype(np.float32)
    cs = np.cumsum(np.concatenate([[0.0], noise]))
    lo = (cs[8:] - cs[:-8]) / 8  # mưa rào nền
    lo = np.pad(lo, (0, n - len(lo)))
    hiss = noise - lo
    drops = np.zeros(n, np.float32)
    for pos in rng.integers(0, n - 400, int(seconds * 60)):
        drops[pos:pos + 400] += rng.uniform(0.2, 0.8) * np.exp(-np.arange(400) / 40) * rng.standard_normal(400)
    x = lo * 0.6 + hiss * 0.12 + drops * 0.3
    fade = int(SR * 0.5)  # nối vòng lặp mượt
    x[:fade] = x[:fade] * np.linspace(0, 1, fade) + x[-fade:] * np.linspace(1, 0, fade)
    return x[:-fade]


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    cs = np.cumsum(np.concatenate([[0.0], x]))
    y = (cs[k:] - cs[:-k]) / k
    return np.pad(y, (0, len(x) - len(y)))


def _loopable(x: np.ndarray, fade_s: float = 0.6) -> np.ndarray:
    f = int(SR * fade_s)
    x[:f] = x[:f] * np.linspace(0, 1, f) + x[-f:] * np.linspace(1, 0, f)
    return x[:-f]


def _gen_ambience(kind: str, seconds: float = 16.0) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    rng = np.random.default_rng(abs(hash(kind)) % 1000)
    noise = rng.standard_normal(n).astype(np.float32)
    if kind == "underwater":  # rì rầm trầm + bọt khí
        x = _smooth(_smooth(noise, 120), 60) * 6 * (0.7 + 0.3 * np.sin(2 * np.pi * 0.1 * t))
        for pos in rng.integers(0, n - 4000, int(seconds * 3)):
            L = rng.integers(800, 3000)
            tt = np.arange(L) / SR
            f0 = rng.uniform(300, 900)
            x[pos:pos + L] += np.sin(2 * np.pi * (f0 + 2500 * tt) * tt) * np.exp(-tt * 25) * 0.25
    elif kind == "wind":
        x = _smooth(noise, 30) * 3 * (0.4 + 0.6 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.13 * t)) ** 2)
    elif kind == "night":  # gió nhẹ + dế
        x = _smooth(noise, 40) * 1.2
        chirp = (np.sin(2 * np.pi * 4300 * t) * (np.sin(2 * np.pi * 28 * t) > 0.3)) * 0.08
        x += chirp * (np.sin(2 * np.pi * 0.7 * t) > 0)
    elif kind in ("office", "cafe", "city"):
        x = _smooth(noise, 200) * 4 + _smooth(noise, 12) * (0.3 if kind == "cafe" else 0.15)
        if kind == "cafe":  # tiếng ly tách
            for pos in rng.integers(0, n - 6000, int(seconds * 0.6)):
                tt = np.arange(6000) / SR
                x[pos:pos + 6000] += np.sin(2 * np.pi * rng.uniform(2500, 3800) * tt) * np.exp(-tt * 18) * 0.12
        if kind == "office":  # gõ phím lác đác
            for pos in rng.integers(0, n - 3000, int(seconds * 4)):
                k = _gen_type_key(int(pos) % 5) * 0.25
                x[pos:pos + len(k)] += k[: n - pos]
        if kind == "city":  # xe chạy qua
            for pos in rng.integers(0, max(1, n - SR * 3), int(seconds * 0.25)):
                L = SR * 3
                env = np.sin(np.pi * np.arange(L) / L) ** 2
                x[pos:pos + L] += _smooth(rng.standard_normal(L).astype(np.float32), 20)[:L] * env * 2
    else:
        x = _smooth(noise, 60)
    return _loopable(x.astype(np.float32))


def _gen_heartbeat(seconds: float = 8.0) -> np.ndarray:
    n = int(SR * seconds)
    x = np.zeros(n, np.float32)
    hb = np.sin(2 * np.pi * 50 * np.arange(int(SR * 0.18)) / SR) * np.exp(-np.arange(int(SR * 0.18)) / SR * 20)
    for i in range(0, n - int(SR * 0.6), int(SR * 0.85)):
        x[i:i + len(hb)] += hb
        j = i + int(SR * 0.25)
        x[j:j + len(hb)] += hb * 0.6
    return x


def _gen_footsteps(steps: int = 6) -> np.ndarray:
    rng = np.random.default_rng(9)
    gap = int(SR * 0.55)
    x = np.zeros(gap * steps + SR, np.float32)
    for k in range(steps):
        L = int(SR * 0.12)
        tt = np.arange(L) / SR
        thud = _smooth(rng.standard_normal(L).astype(np.float32), 25) * np.exp(-tt * 40) * 6
        click = rng.standard_normal(L).astype(np.float32) * np.exp(-tt * 300) * 0.3
        x[k * gap:k * gap + L] += (thud + click) * rng.uniform(0.7, 1)
    return x


def _gen_door() -> np.ndarray:
    L = int(SR * 1.6)
    tt = np.arange(L) / SR
    f = 180 + 120 * np.sin(2 * np.pi * 0.9 * tt) + 40 * np.sin(2 * np.pi * 7 * tt)
    saw = 2 * ((np.cumsum(f) / SR) % 1) - 1  # tiếng bản lề kẽo kẹt
    creak = _smooth(saw.astype(np.float32), 6) * (np.sin(np.pi * tt / tt[-1]) ** 0.5) * 0.5
    thud_len = int(SR * 0.4)
    th = np.arange(thud_len) / SR
    thud = np.sin(2 * np.pi * 70 * th) * np.exp(-th * 14)
    out = np.zeros(L + thud_len, np.float32)
    out[:L] += creak
    out[L - int(SR * 0.05):L - int(SR * 0.05) + thud_len] += thud
    return out


def _gen_type_key(seed: int) -> np.ndarray:
    n = int(SR * 0.06)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 180)
    thunk = np.sin(2 * np.pi * (180 + seed % 5 * 20) * t) * np.exp(-t * 60) * 0.5
    return (click * 0.7 + thunk) * 0.5


def _gen_notify() -> np.ndarray:
    """Tiếng 'ting ting' thông báo điện thoại."""
    out = np.zeros(int(SR * 0.6), np.float32)
    for k, f in enumerate((1318.5, 1760.0)):
        n = int(SR * 0.35)
        t = np.arange(n) / SR
        tone = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 9)
        a = int(SR * 0.13 * k)
        out[a:a + n] += tone.astype(np.float32) * 0.6
    return out


def _gen_tick(seconds: float = 6.0) -> np.ndarray:
    """Đồng hồ tích tắc."""
    out = np.zeros(int(SR * seconds), np.float32)
    rng = np.random.default_rng(5)
    for i in range(int(seconds)):
        for h, f in ((0.0, 2600), (0.5, 2100)):
            n = int(SR * 0.025)
            t = np.arange(n) / SR
            c = (rng.standard_normal(n) * 0.4 + np.sin(2 * np.pi * f * t)) * np.exp(-t * 300)
            a = int(SR * (i + h))
            out[a:a + n] += c.astype(np.float32) * 0.5
    return out


def _gen_sting() -> np.ndarray:
    """Tiếng 'rùng mình': hút ngược lên + cú đánh trầm + tiếng rít chói không hoà âm."""
    rng = np.random.default_rng(13)
    n_sw, n_hit = int(SR * 0.6), int(SR * 1.8)
    t = np.arange(n_sw) / SR
    swell = rng.standard_normal(n_sw).astype(np.float32)
    swell = np.convolve(swell, np.ones(30) / 30, mode="same") * (t / t[-1]) ** 3 * 0.8
    th = np.arange(n_hit) / SR
    boom = np.sin(2 * np.pi * (70 * np.exp(-th * 3) + 35) * th) * np.exp(-th * 2.5)
    screech = sum(np.sin(2 * np.pi * f * th + np.sin(2 * np.pi * 6 * th) * 3) for f in (1480, 1568, 2217)) / 3
    screech *= np.exp(-th * 1.6) * 0.35
    cluster = sum(np.sin(2 * np.pi * f * th) for f in (110, 116.5, 155.6)) / 3 * np.exp(-th * 1.2) * 0.5
    return np.concatenate([swell, (boom * 0.9 + screech + cluster)]).astype(np.float32)


def _gen_glitch() -> np.ndarray:
    rng = np.random.default_rng(21)
    out = np.zeros(int(SR * 0.45), np.float32)
    for k in range(5):
        a = int(SR * rng.uniform(0, 0.38))
        n = int(SR * rng.uniform(0.02, 0.06))
        burst = np.sign(rng.standard_normal(n)) * (rng.random(n) < 0.5)
        out[a:a + n] += burst[: len(out) - a].astype(np.float32) * 0.6
    return out


def load(name: str) -> np.ndarray:
    """Âm thanh SFX: ưu tiên file của bạn ở assets/sfx/<name>.wav, không có thì tự tạo."""
    user = SFX_DIR / f"{name}.wav"
    if user.exists():
        try:
            return _read(user)
        except Exception as e:  # noqa: BLE001
            log(f"  ! không đọc được {user}: {e}")
    gen = GEN_DIR / f"{name}.wav"
    if not gen.exists():
        gens = {"hit": _gen_hit, "whoosh": _gen_whoosh, "flash": _gen_flash, "riser": _gen_riser,
                "rain": _gen_rain, "heartbeat": _gen_heartbeat, "footsteps": _gen_footsteps, "door": _gen_door,
                "notify": _gen_notify, "tick": _gen_tick, "sting": _gen_sting, "glitch": _gen_glitch}
        for amb in ("underwater", "wind", "night", "office", "cafe", "city"):
            gens[amb] = (lambda k=amb: _gen_ambience(k))
        x = gens.get(name, lambda: _gen_type_key(0))()
        _write(gen, x / (np.abs(x).max() + 1e-6) * 0.9)
    return _read(gen)


def typing(n_chars: int, cps: float = 16) -> np.ndarray:
    keys = [_gen_type_key(i) for i in range(5)]
    user = SFX_DIR / "type.wav"
    if user.exists():
        keys = [_read(user)]
    step = int(SR / cps)
    out = np.zeros(step * n_chars + len(keys[0]) + 10, np.float32)
    rng = np.random.default_rng(n_chars)
    for i in range(n_chars):
        k = keys[i % len(keys)]
        pos = i * step + int(rng.integers(-step // 5, step // 5 + 1)) if i else 0
        pos = max(0, pos)
        out[pos:pos + len(k)] += k[: len(out) - pos] * rng.uniform(0.7, 1.0)
    return out


def build_sfx_track(tl: dict, cfg: dict, out: Path) -> Path | None:
    """Tạo 1 file WAV chứa toàn bộ SFX đúng thời điểm theo timeline."""
    sc = cfg.get("sfx", {})
    if not sc.get("enabled", True):
        return None
    fps = tl["fps"]
    total = int((tl["duration"] + 2) * SR)
    track = np.zeros(total, np.float32)
    vol = {"hit": sc.get("hit", 0.55), "whoosh": sc.get("whoosh", 0.35), "flash": sc.get("flash", 0.45),
           "type": sc.get("type", 0.25), "riser": sc.get("riser", 0.3), "rain": sc.get("rain", 0.18),
           "ambience": sc.get("ambience", 0.16), "footsteps": sc.get("footsteps", 0.45), "door": sc.get("door", 0.45),
           "heartbeat": sc.get("heartbeat", 0.35), "notify": sc.get("notify", 0.4), "tick": sc.get("tick", 0.3),
           "sting": sc.get("sting", 0.6), "glitch": sc.get("glitch", 0.3)}
    AMB = ("underwater", "wind", "night", "office", "cafe", "city", "rain", "heartbeat")
    import re as _re

    rain_words = _re.compile(sc.get("rain_words", r"mưa|rain|storm|bão|giông"), _re.I)
    cache: dict[str, np.ndarray] = {}

    def put(name: str, t: float, clip: np.ndarray | None = None):
        if clip is None:
            clip = cache.setdefault(name, load(name))
        a = int(max(0, t) * SR)
        b = min(total, a + len(clip))
        if b > a:
            track[a:b] += clip[: b - a] * vol[name]

    n_events = 0
    for it in tl["items"]:
        if it["type"] in ("title", "chapter"):
            if it["start"] > 3:
                put("riser", it["start"] - 2.35)
            put("hit", it["start"] + 0.05)
            n_events += 1
            continue
        snd = it.get("sound") or ""
        if snd in ("", "none", "auto"):
            snd = sc.get("default_ambience", "") or ""
        if snd in AMB and snd != "rain":  # âm nền suốt cảnh (theo storyboard)
            amb = cache.setdefault(snd, load(snd))
            reps = int(np.ceil(it["duration"] / (len(amb) / SR)))
            clip = np.tile(amb, reps)[: int(it["duration"] * SR)]
            f = min(len(clip) // 4, int(SR * 0.8))
            clip[:f] *= np.linspace(0, 1, f)
            clip[-f:] *= np.linspace(1, 0, f)
            key = "heartbeat" if snd == "heartbeat" else "ambience"
            a = int(it["start"] * SR)
            b = min(total, a + len(clip))
            track[a:b] += clip[: b - a] * vol[key]
            n_events += 1
        elif snd in ("footsteps", "door"):
            put(snd, it["start"] + 0.2)
            n_events += 1
        elif snd == "riser":
            put("riser", it["start"] + it["duration"] - 2.4)
            n_events += 1
        elif snd == "whoosh":
            put("whoosh", it["start"])
            n_events += 1
        if snd == "rain" or rain_words.search(it.get("text", "")):  # tiếng mưa nền suốt cảnh có nhắc tới mưa
            rain = cache.setdefault("rain", load("rain"))
            reps = int(np.ceil(it["duration"] / (len(rain) / SR)))
            clip = np.tile(rain, reps)[: int(it["duration"] * SR)]
            f = min(len(clip) // 4, int(SR * 0.8))
            clip[:f] *= np.linspace(0, 1, f)
            clip[-f:] *= np.linspace(1, 0, f)
            put("rain", it["start"], clip)
            n_events += 1
        shots = it["shots"]
        label_at = it["start"] + 0.4
        for k, sh in enumerate(shots):
            if sh.get("namecard"):
                put("whoosh", sh["start"] + 0.1)
                n_events += 1
                F0 = round((sh["start"] + sh["duration"]) * fps) - round(sh["start"] * fps)
                label_at = it["start"] + min(F0 / fps, 4.5) + 0.3
            if sh.get("motion") == "slam":
                put("hit", sh["start"] + 0.02, cache.setdefault("hit", load("hit")) * 0.6)
                n_events += 1
            if k > 0 and sh.get("transition") == "flash":
                put("flash", sh["start"] - 0.12)
                n_events += 1
        fxk, acc = it.get("fx") or "none", it.get("accents") or []
        for i_, a_ in enumerate(acc):  # nhấn nhá đúng nhịp lời đọc
            at = it["start"] + a_
            if fxk == "shudder":
                put("sting", at - 0.6, cache.setdefault("sting", load("sting")) * (1.0 if i_ == 0 else 0.6))
            elif fxk == "action":
                put("hit", at, cache.setdefault("hit", load("hit")) * 0.8)
                put("whoosh", at - 0.35, cache.setdefault("whoosh", load("whoosh")) * 0.6)
            elif fxk in ("impact", "reveal"):
                if fxk == "reveal" and at > 2.5:
                    put("riser", at - 2.35)
                put("hit", at)
            elif fxk == "glitch":
                put("glitch", at)
            else:
                put("hit", at, cache.setdefault("hit", load("hit")) * 0.45)
            n_events += 1
        if fxk == "shudder" and (it.get("sound") or "") in ("", "none", "auto"):  # nhịp tim suốt cảnh
            hb = cache.setdefault("heartbeat", load("heartbeat"))
            clip = np.tile(hb, int(np.ceil(it["duration"] / (len(hb) / SR))))[: int(it["duration"] * SR)].copy()
            f_ = min(len(clip) // 4, int(SR * 0.6))
            clip[:f_] *= np.linspace(0, 1, f_)
            clip[-f_:] *= np.linspace(1, 0, f_)
            put("heartbeat", it["start"], clip)
        if fxk == "action":
            for sh in shots[1:]:
                put("whoosh", sh["start"] - 0.2, cache.setdefault("whoosh", load("whoosh")) * 0.5)
        if fxk == "glitch":
            for k_ in range(int(it["duration"] / 1.3)):
                if k_ % 3 == 1:
                    put("glitch", it["start"] + k_ * 1.3, cache.setdefault("glitch", load("glitch")) * 0.5)
        if it.get("overlay"):  # tên video / chương hiện đè: riser dẫn vào + boom
            if it["start"] > 3:
                put("riser", it["start"] - 2.3, cache.setdefault("riser", load("riser")) * 0.7)
            put("hit", it["start"] + 0.12)
            put("whoosh", it["start"] + 0.05, cache.setdefault("whoosh", load("whoosh")) * 0.6)
            n_events += 1
        for sh in shots:
            if sh.get("frame") == "insert":
                typ = (sh.get("insert") or {}).get("type")
                if typ in ("phone", "chat", "bank"):
                    put("notify", sh["start"] + 0.6)
                elif typ == "clock":
                    tk = cache.setdefault("tick", load("tick"))
                    put("tick", sh["start"], tk[: int(sh["duration"] * SR)])
                n_events += 1
            if (sh.get("char") or {}).get("shadow", "").strip() and sh.get("frame") == "character":
                put("whoosh", sh["start"] + 0.05, cache.setdefault("whoosh", load("whoosh")) * 0.45)
                n_events += 1
        if it.get("label"):
            put("type", label_at, typing(len(it["label"])))
            n_events += 1
    peak = np.abs(track).max()
    if peak > 0.95:
        track *= 0.95 / peak
    _write(out, track)
    log(f"  SFX: {n_events} hiệu ứng âm thanh")
    return out


def auto_music_light(out: Path, minutes: float = 2.0) -> Path:
    """Nhạc nền nhẹ nhàng, tươi sáng (hợp kênh giải thích 2D): hợp âm C-G-Am-F + rải nốt."""
    if out.exists():
        return out
    bpm = 92
    beat = 60 / bpm
    chords = [[261.6, 329.6, 392.0], [196.0, 246.9, 293.7], [220.0, 261.6, 329.6], [174.6, 220.0, 261.6]]
    bar = beat * 4
    n_bars = int(minutes * 60 / bar)
    n = int(n_bars * bar * SR)
    x = np.zeros(n, np.float32)
    for b in range(n_bars):
        ch = chords[b % 4]
        a = int(b * bar * SR)
        L = int(bar * SR)
        tt = np.arange(L) / SR
        pad = sum(np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt) for f in ch) / 3
        x[a:a + L] += (pad * (0.5 + 0.5 * np.sin(np.pi * tt / bar)) * 0.12).astype(np.float32)
        for k in range(8):  # rải nốt (pluck)
            f = ch[k % 3] * (2 if k % 4 == 3 else 1)
            s0 = a + int(k * beat / 2 * SR)
            pl = int(SR * 0.45)
            pt = np.arange(pl) / SR
            note = np.sin(2 * np.pi * f * pt) * np.exp(-pt * 7) * 0.18
            x[s0:s0 + pl] += note[: max(0, min(pl, n - s0))]
        bass = np.sin(2 * np.pi * ch[0] / 2 * tt) * np.exp(-(tt % beat) * 3) * 0.15
        x[a:a + L] += bass.astype(np.float32)
    x = x / np.abs(x).max() * 0.55
    stereo = np.stack([x, np.roll(x, 220)], axis=1).reshape(-1)
    _write(out, stereo, ch=2)
    log(f"  (chưa có nhạc trong assets/music -> tự tạo nhạc nền nhẹ nhàng: {out.name})")
    return out


def auto_music(out: Path, minutes: float = 3.0, seed: int = 7, style: str = "dark") -> Path:
    """Nhạc nền tự tạo khi assets/music/ trống. style: dark (drone u tối) | light (nhẹ nhàng, tươi sáng)."""
    if style == "light":
        return auto_music_light(out.with_name("_auto_music_light.wav"))
    if out.exists():
        return out
    n = int(SR * 60 * minutes)
    t = np.arange(n, dtype=np.float32) / SR
    rng = np.random.default_rng(seed)
    loop = 60 * minutes
    lfo = lambda f, ph=0.0: 0.5 + 0.5 * np.sin(2 * np.pi * f * t + ph)  # noqa: E731
    # các tần số chia hết cho độ dài vòng lặp để nối liền không bị "giật"
    def tone(f):
        f = round(f * loop) / loop
        return np.sin(2 * np.pi * f * t)
    drone = (tone(55) * 0.5 + tone(82.4) * 0.28 + tone(110.2) * 0.12) * (0.6 + 0.4 * lfo(1 / loop * 4))
    pad = (tone(220.5) * lfo(1 / loop * 6, 1.0) + tone(261.6) * lfo(1 / loop * 3, 2.0)) * 0.05
    noise = rng.standard_normal(n).astype(np.float32)
    cs = np.cumsum(np.concatenate([[0.0], noise]))
    wind = ((cs[400:] - cs[:-400]) / 400)
    wind = np.pad(wind, (0, n - len(wind))) * 4 * lfo(1 / loop * 5, 0.5)
    pulse = np.zeros(n, np.float32)
    beat = int(SR * 2.0)  # nhịp tim chậm mỗi 2 giây
    hb = np.sin(2 * np.pi * 45 * np.arange(int(SR * 0.25)) / SR) * np.exp(-np.arange(int(SR * 0.25)) / SR * 18)
    for i in range(0, n - len(hb), beat):
        pulse[i:i + len(hb)] += hb * 0.35
        j = i + int(SR * 0.28)
        if j + len(hb) < n:
            pulse[j:j + len(hb)] += hb * 0.2
    x = drone + pad + wind * 0.3 + pulse
    x = x / np.abs(x).max() * 0.6
    stereo = np.stack([x, np.roll(x, 300)], axis=1).reshape(-1)
    _write(out, stereo, ch=2)
    log(f"  (chưa có nhạc trong assets/music -> tự tạo nhạc nền u tối: {out.name})")
    return out


# ======================================================================= nhạc theo cảm xúc
# Mỗi cảnh có thể đặt "music": calm | sad | tense | hopeful | dark | light | silence.
# Nhạc của bạn: assets/music/<cảm xúc>/*.mp3 (vd assets/music/sad/piano.mp3) -> tool ưu tiên dùng.
# Không có -> tự tạo nhạc đơn giản đúng cảm xúc (để có nhịp cảm xúc ngay, nên thay bằng nhạc thật có bản quyền).

MUSIC_MOODS = ("calm", "sad", "tense", "hopeful", "dark", "light", "horror", "action")
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _hz(name: str) -> float:
    """'A3' -> Hz; hỗ trợ '#'/'b'."""
    n, acc = NOTE[name[0]], 0
    rest = name[1:]
    if rest and rest[0] in "#b":
        acc = 1 if rest[0] == "#" else -1
        rest = rest[1:]
    midi = 12 * (int(rest) + 1) + n + acc
    return 440.0 * 2 ** ((midi - 69) / 12)


def _piano(f: float, dur: float, vel: float = 0.5) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = sum((1 / h ** 1.6) * np.sin(2 * np.pi * h * f * t + h) * np.exp(-t * (1.6 + 1.1 * h)) for h in range(1, 6))
    att = np.minimum(1, t / 0.006)
    return (x * att * vel).astype(np.float32)


def _pad(fs: list[float], dur: float, vol: float = 0.08) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2.003 * t) for f in fs) / len(fs)
    env = np.minimum(1, t / 1.2) * np.minimum(1, (dur - t) / 1.2)
    return (x * env * vol).astype(np.float32)


def _reverb(x: np.ndarray, mix: float = 0.35) -> np.ndarray:
    y = x.copy()
    for d, g in ((0.113, 0.5), (0.167, 0.42), (0.251, 0.33), (0.373, 0.25), (0.53, 0.17)):
        k = int(SR * d)
        y[k:] += x[:-k] * g
        y[2 * k:] += x[:-2 * k] * g * 0.5
    return x * (1 - mix) + y * mix


def _mood_gen(mood: str, seconds: float = 64.0, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    x = np.zeros(n + SR * 4, np.float32)

    def put(clip, t):
        a = int(t * SR)
        b = min(len(x), a + len(clip))
        x[a:b] += clip[: b - a]

    if mood in ("sad", "calm", "hopeful"):
        prog = {"sad": [["A2", "E3", "A3", "C4", "E4"], ["F2", "C3", "F3", "A3", "C4"], ["C3", "G3", "C4", "E4", "G4"],
                        ["G2", "D3", "G3", "B3", "D4"]],
                "calm": [["C3", "G3", "B3", "E4"], ["A2", "E3", "G3", "C4"], ["F2", "C3", "E3", "A3"],
                         ["G2", "D3", "F3", "B3"]],
                "hopeful": [["C3", "G3", "C4", "E4", "G4"], ["G2", "D3", "G3", "B3", "D4"],
                            ["A2", "E3", "A3", "C4", "E4"], ["F2", "C3", "F3", "A3", "C4"]]}[mood]
        bpm = {"sad": 62, "calm": 58, "hopeful": 76}[mood]
        beat = 60 / bpm
        bar = beat * 4
        t = 0.0
        i = 0
        while t < seconds:
            ch = [_hz(c) for c in prog[i % 4]]
            put(_pad(ch[:3], bar + 1.0, 0.05 if mood != "calm" else 0.08), t)
            put(_piano(ch[0], 3.5, 0.35), t)
            if mood != "calm":  # rải nốt piano nhẹ, có lúc nghỉ
                pattern = [1, 2, 3, 2, 4, 3, 2, 1] if mood == "hopeful" else [2, 3, 4, 3]
                step = bar / len(pattern)
                for k, idx in enumerate(pattern):
                    if mood == "sad" and rng.random() < 0.18:
                        continue
                    put(_piano(ch[min(idx, len(ch) - 1)] * (2 if mood == "hopeful" and k % 4 == 3 else 1), 2.2,
                               0.22 + 0.06 * rng.random()), t + k * step)
            else:
                put(_piano(ch[-1] * 2, 3.0, 0.12), t + beat * 2)
            t += bar
            i += 1
        x = _reverb(x, 0.45 if mood == "sad" else 0.35)
    elif mood == "tense":
        bpm = 96
        e = 60 / bpm / 2
        tt = np.arange(len(x)) / SR
        drone = (np.sin(2 * np.pi * _hz("D2") * tt) * 0.5 + np.sin(2 * np.pi * _hz("D#2") * tt) * 0.18)
        x += (drone * (0.6 + 0.4 * np.sin(2 * np.pi * tt / 7.5)) * 0.18).astype(np.float32)
        trem = np.sin(2 * np.pi * _hz("A#4") * tt) * (0.5 + 0.5 * np.sin(2 * np.pi * 11 * tt))
        x += (trem * 0.025 * np.minimum(1, tt / 8)).astype(np.float32)
        k = 0
        t = 0.0
        while t < seconds:  # ostinato trầm dồn dập
            f = _hz("D2") if (k // 8) % 2 == 0 else _hz("F2")
            put(_piano(f, 0.35, 0.45 if k % 2 == 0 else 0.3), t)
            if k % 8 == 0:
                put(_gen_hit() * 0.18, t)
            t += e
            k += 1
        x = _reverb(x, 0.25)
    elif mood == "action":
        bpm = 138
        beat = 60 / bpm
        tt = np.arange(int(SR * 0.5)) / SR
        kick = (np.sin(2 * np.pi * (150 * np.exp(-tt * 30) + 48) * tt) * np.exp(-tt * 9)).astype(np.float32)
        snare = ((rng.standard_normal(len(tt)) * 0.7 + np.sin(2 * np.pi * 190 * tt)) * np.exp(-tt * 18)).astype(np.float32)
        hat = (np.diff(rng.standard_normal(int(SR * 0.05)), prepend=0) * np.exp(-np.arange(int(SR * 0.05)) / SR * 90))
        hat = hat.astype(np.float32) * 0.25
        roots = [_hz("D2"), _hz("D2"), _hz("A#1"), _hz("C2")]
        t = 0.0
        k = 0
        while t < seconds:
            bar_i = int(t / (beat * 4))
            if k % 4 in (0, 2) or (k % 8 == 7):
                put(kick * 0.9, t)
            if k % 4 in (1, 3):
                put(snare * 0.55, t)
            put(hat, t)
            put(hat * 0.6, t + beat / 2)
            r = roots[bar_i % 4]
            for q in range(4):  # bass móc 16 dồn dập
                nn = int(SR * beat / 4 * 0.9)
                tq = np.arange(nn) / SR
                saw = (2 * ((r * tq) % 1) - 1) * np.exp(-tq * 6) * 0.28
                put(saw.astype(np.float32), t + q * beat / 4)
            if k % 8 == 0:  # hợp âm "stab" kèn đồng
                nn = int(SR * 0.45)
                ts = np.arange(nn) / SR
                stab = sum(2 * (((r * 2 * m_) * ts) % 1) - 1 for m_ in (1, 1.2, 1.5)) / 3 * np.exp(-ts * 5) * 0.22
                put(stab.astype(np.float32), t)
            t += beat
            k += 1
        x = _reverb(x, 0.15)
    elif mood == "horror":
        tt = np.arange(len(x)) / SR
        drone = sum(np.sin(2 * np.pi * f * tt + np.sin(2 * np.pi * 0.07 * tt) * 2) for f in (55, 58.3, 82.4)) / 3
        x += (drone * 0.22 * (0.7 + 0.3 * np.sin(2 * np.pi * tt / 9))).astype(np.float32)
        hi = sum(np.sin(2 * np.pi * f * tt) for f in (1244, 1318.5)) / 2 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.13 * tt))
        x += (hi * 0.03).astype(np.float32)
        t = 3.0
        while t < seconds:  # tiếng gõ trầm thưa, bất chợt
            put(_gen_hit() * 0.25, t)
            t += float(rng.uniform(4, 9))
        x = _reverb(x, 0.5)
    else:
        return np.zeros(n, np.float32)
    x = x[:n]
    f = int(SR * 1.5)
    x[:f] *= np.linspace(0, 1, f)
    x[-f:] *= np.linspace(1, 0, f)
    return x / (np.abs(x).max() + 1e-6) * 0.6


def _decode(path: Path) -> np.ndarray:
    """Đọc mp3/m4a/ogg/wav bất kỳ -> mono float32 44.1k (dùng ffmpeg)."""
    import subprocess

    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def mood_music(mood: str) -> np.ndarray:
    """Nhạc cho 1 cảm xúc: file của bạn (assets/music/<mood>/) -> nếu không có thì tự tạo."""
    import random as _r

    d = ROOT / "assets" / "music" / mood
    files = sorted(p for p in d.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")) if d.exists() else []
    if files:
        return _decode(_r.Random(mood).choice(files))
    gen = GEN_DIR / f"music_{mood}.wav"
    if mood in ("dark", "light"):
        p = auto_music(ROOT / "assets" / "_auto_music.wav", style=mood)
        return _read(p)
    if not gen.exists():
        _write(gen, _mood_gen(mood))
        log(f"  (chưa có nhạc assets/music/{mood}/ -> tự tạo nhạc '{mood}')")
    return _read(gen)


def build_music_track(tl: dict, cfg: dict, out: Path) -> Path | None:
    """Ghép nhạc nền theo cảm xúc từng đoạn, chuyển nhạc mềm (crossfade), 'silence' = tắt nhạc.
    Không cảnh nào đặt music -> trả None (dùng nhạc chung như cũ)."""
    rc = cfg["render"]
    if not any(it.get("music") for it in tl["items"]):
        return None
    default = rc.get("auto_music_style", "dark")
    segs: list[list] = []
    cur = default
    for it in tl["items"]:
        m = it.get("music") or cur
        cur = m
        if segs and segs[-1][2] == m:
            segs[-1][1] = it["start"] + it["duration"]
        else:
            segs.append([it["start"], it["start"] + it["duration"], m])
    total = int((tl["duration"] + 1) * SR)
    track = np.zeros(total, np.float32)
    xf = 1.6
    cache: dict[str, np.ndarray] = {}
    for a, b, m in segs:
        if m == "silence" or m not in MUSIC_MOODS:
            continue
        src = cache.setdefault(m, mood_music(m))
        if not len(src):
            continue
        s0 = int(max(0, a - xf / 2) * SR)
        s1 = min(total, int((b + xf / 2) * SR))
        L = s1 - s0
        clip = np.tile(src, int(np.ceil(L / len(src))) + 1)[:L].copy()
        f = min(int(xf * SR), L // 3)
        if f > 0:
            clip[:f] *= np.linspace(0, 1, f)
            clip[-f:] *= np.linspace(1, 0, f)
        track[s0:s1] += clip
    peak = np.abs(track).max()
    if peak > 0:
        track *= 0.8 / peak
    stereo = np.stack([track, np.roll(track, 240)], axis=1).reshape(-1)
    _write(out, stereo, ch=2)
    log(f"  Nhạc theo cảm xúc: {' -> '.join(dict.fromkeys(s[2] for s in segs))}")
    return out

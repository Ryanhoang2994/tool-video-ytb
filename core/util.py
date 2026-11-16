"""Tiện ích chung: config, HTTP, ffmpeg, đường dẫn project."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
UA = "ColdCaseStudio/1.1 (personal documentary research tool; https://www.mediawiki.org/wiki/API:Etiquette)"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def list_presets() -> dict[str, str]:
    out = {}
    for p in sorted((ROOT / "presets").glob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out[p.stem] = d.get("description", "")
    return out


def load_config(path: str | Path | None = None, preset: str | None = None) -> dict:
    """config.yaml + (tuỳ chọn) preset theo ngách trong presets/<tên>.yaml ghi đè lên."""
    p = Path(path) if path else ROOT / "config.yaml"
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if preset:
        pp = ROOT / "presets" / f"{preset}.yaml"
        if not pp.exists():
            raise SystemExit(f"Không có preset '{preset}'. Có: {', '.join(list_presets())}")
        over = yaml.safe_load(pp.read_text(encoding="utf-8")) or {}
        over.pop("description", None)
        _merge(cfg, over)
        cfg["_preset"] = preset
    return cfg


def slugify(text: str, maxlen: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:maxlen] or "case"


class Project:
    """Mỗi vụ án là một thư mục trong projects/<slug>/"""

    def __init__(self, slug: str):
        self.slug = slug
        self.dir = ROOT / "projects" / slug
        for sub in ("media", "media/raw", "media/shots", "audio", "cards", "output"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def read_json(self, name: str, default=None):
        p = self.path(name)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def write_json(self, name: str, data) -> Path:
        p = self.path(name)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p


_session = requests.Session()
_session.headers["User-Agent"] = UA


_host_lock = __import__("threading").Lock()
_host_last: dict[str, float] = {}
SLOW_HOSTS = {"upload.wikimedia.org": 0.6, "commons.wikimedia.org": 0.4, "en.wikipedia.org": 0.3,
              "vi.wikipedia.org": 0.3, "www.loc.gov": 0.5, "tile.loc.gov": 0.4, "archive.org": 0.5,
              "image.pollinations.ai": 6.0}  # Pollinations bản free: ~1 ảnh / vài giây, dồn dập sẽ bị 402


def _throttle(url: str) -> None:
    """Giãn nhịp gửi request tới các host hay giới hạn tốc độ (tránh lỗi 429)."""
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    gap = SLOW_HOSTS.get(host, 0)
    if not gap:
        return
    with _host_lock:
        wait = _host_last.get(host, 0) + gap - time.time()
        _host_last[host] = max(time.time(), _host_last.get(host, 0) + gap)
    if wait > 0:
        time.sleep(wait)


_host_429: dict[str, list[float]] = {}


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).hostname or ""


_host_timeout: dict[str, list[float]] = {}
_host_dead: set[str] = set()  # host bị chặn (proxy/SSL) -> không thử lại trong lượt chạy này


def host_ok(url: str) -> bool:
    return _host(url) not in _host_dead


def http_get(url: str, *, params=None, headers=None, timeout=30, retries=4, stream=False):
    last = None
    host = _host(url)
    hits = _host_429.get(host, [])
    if len([t for t in hits if time.time() - t < 120]) >= 6:  # host đang chặn tốc độ -> tạm bỏ qua 2 phút
        raise requests.HTTPError(f"429 (tạm bỏ qua {host})")
    allto = _host_timeout.get(host, [])
    if host in _host_dead:
        raise requests.exceptions.ProxyError(f"{host} bị chặn (bỏ qua)")
    tos = [t for t in allto if time.time() - t < 600]
    if len(tos) >= 2 or len(allto) >= 5:  # không trả lời 2 lần/10 phút -> nghỉ 10 phút; lặp lại nhiều lần -> bỏ hẳn
        raise requests.exceptions.ConnectTimeout(f"{host} không phản hồi (tạm bỏ qua)")
    for i in range(retries):
        try:
            _throttle(url)
            r = _session.get(url, params=params, headers=headers, timeout=timeout, stream=stream)
            if r.status_code in (429, 503) or (r.status_code == 402 and "pollinations" in host):
                _host_429.setdefault(host, []).append(time.time())
                ra = r.headers.get("retry-after", "")
                time.sleep(min(20.0, float(ra)) if ra.isdigit() else min(20, 2 ** (i + 1)))
                last = requests.HTTPError(f"{r.status_code} {url[:80]}")
                continue
            if 400 <= r.status_code < 500:  # 403/404...: thử lại vô ích -> báo lỗi ngay
                r.raise_for_status()
            r.raise_for_status()
            return r
        except (requests.exceptions.ProxyError, requests.exceptions.SSLError) as e:
            _host_dead.add(host)
            raise e  # host bị chặn / lỗi chứng chỉ: không thử lại
        except requests.HTTPError as e:
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise
            last = e
            time.sleep(1.5 * (i + 1))
        except requests.exceptions.Timeout as e:  # hết giờ: thử lại tối đa 1 lần, ghi nhận để lần sau bỏ qua host
            _host_timeout.setdefault(host, []).append(time.time())
            last = e
            if i >= 1:
                break
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last if last else RuntimeError(f"GET failed: {url}")


def http_json(url: str, **kw):
    return http_get(url, **kw).json()


def download(url: str, dest: Path, *, headers=None, max_mb: float = 200) -> Path | None:
    try:
        r = http_get(url, headers=headers, stream=True, timeout=60)
        size = int(r.headers.get("content-length") or 0)
        if size and size > max_mb * 1e6:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
        tmp.replace(dest)
        return dest
    except Exception as e:  # noqa: BLE001
        log(f"  ! tải lỗi {url[:80]}: {e}")
        return None


# ---------------- ffmpeg ----------------

def need_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("Chưa cài ffmpeg. Windows: winget install ffmpeg  |  Ubuntu: sudo apt install ffmpeg")


def run(cmd: list[str], quiet: bool = True) -> None:
    res = subprocess.run(cmd, capture_output=quiet, text=True, encoding="utf-8", errors="ignore")
    if res.returncode != 0:
        err = (res.stderr or "")[-1500:]
        raise RuntimeError(f"Lệnh lỗi: {' '.join(cmd[:6])} ...\n{err}")


def ffprobe_duration(path: str | Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def video_size(path: str | Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    try:
        w, h = out.split(",")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0


def find_font(preferred: str = "") -> str:
    """Tìm font có hỗ trợ tiếng Việt."""
    cands = [preferred] if preferred else []
    cands += [
        str(ROOT / "assets/fonts/font.ttf"),
        "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ]
    for c in cands:
        if c and Path(c).exists():
            return c
    return ""


def find_mono_font() -> str:
    for c in [str(ROOT / "assets/fonts/mono.ttf"), "C:/Windows/Fonts/cour.ttf", "C:/Windows/Fonts/consola.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"]:
        if Path(c).exists():
            return c
    return find_font()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[\.\!\?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]

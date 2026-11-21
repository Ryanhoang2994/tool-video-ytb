"""Viết kịch bản hàng loạt trên máy của bạn (Windows / Mac / Linux).

  python batch.py                 chạy mọi kênh trong batch/queue.yaml (bỏ qua tập đã viết xong)
  python batch.py --channel vu_an chỉ chạy 1 kênh
  python batch.py --status        xem tiến độ (cũng ghi vào batch/TIEN_DO.txt)
  python batch.py --dry           chỉ liệt kê việc sẽ làm

Mỗi chủ đề: tìm tư liệu (new) -> viết kịch bản (script) -> dịch (translate, nếu kênh có translate_to).
- Chạy song song `parallel` chủ đề (mặc định 2).
- Hết lượt Claude ("resets 3:40pm (...)") -> tự chờ tới giờ reset rồi chạy tiếp; tắt máy giữa chừng thì
  chạy lại lệnh, bước nào xong rồi sẽ được bỏ qua.
- Wikipedia không trả kết quả -> chưa viết tập đó (không viết khi thiếu nguồn), lượt sau thử lại.
- Trong lúc chạy, máy không tự ngủ (Windows).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core.util import slugify  # noqa: E402

BATCH = ROOT / "batch"
LOGS = BATCH / "logs"
PROJ = ROOT / "projects"
_lock = threading.Lock()
_stop = threading.Event()
_children: set = set()   # tiến trình đang chạy -> dừng hết khi bấm Ctrl+C


def say(msg: str) -> None:
    line = f"[{dt.datetime.now():%d/%m %H:%M}] {msg}"
    with _lock:
        print(line, flush=True)
        with open(BATCH / "nhat_ky.txt", "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---------------------------------------------------------------- danh sách chủ đề

def read_topics(path: Path) -> list[tuple[str, str]]:
    """Mỗi dòng: `Chủ đề | năm` (năm có thể bỏ trống). Dòng bắt đầu bằng # là ghi chú. Nhận cả file TSV cũ."""
    out = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"\s*\|\s*|\t", line)]
        out.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return out


def load_queue(path: Path) -> dict:
    q = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    q.setdefault("parallel", 2)
    q.setdefault("channels", [])
    return q


# ---------------------------------------------------------------- trạng thái 1 chủ đề

def has_script(slug: str) -> bool:
    p = PROJ / slug / "script.json"
    return p.exists() and '"narration"' in p.read_text(encoding="utf-8", errors="ignore")


def state(ch: dict, topic: str) -> str:
    slug = slugify(topic)
    if not has_script(slug):
        return "research" if not (PROJ / slug / "research.json").exists() else "script"
    if ch.get("translate_to") and not has_script(f"{slug}-{ch['translate_to']}"):
        return "translate"
    return "done"


# ---------------------------------------------------------------- hết lượt Claude

_RESET = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)]+)\))?", re.I)


def reset_wait_seconds(text: str, now: dt.datetime | None = None) -> int | None:
    """Đọc giờ reset trong thông báo hết lượt của Claude -> số giây cần chờ (thêm 2 phút). None nếu không phải hết lượt."""
    low = text.lower()
    if not re.search(r"hit your .*limit|usage limit|limit reached|resets \d", low):
        return None
    m = _RESET.search(text)
    if not m:
        return 30 * 60
    h, mi, ap, tzname = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower(), m.group(4)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    tz = None
    if tzname:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo("UTC" if tzname.upper() == "UTC" else tzname)
        except Exception:  # noqa: BLE001  - Windows thiếu dữ liệu múi giờ -> coi như giờ máy
            tz = None
    now = now or (dt.datetime.now(tz) if tz else dt.datetime.now())
    if tz and now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    wait = int((target - now).total_seconds()) + 120
    return wait if wait <= 8 * 3600 else 30 * 60


def sleep_until(seconds: int) -> None:
    end = time.time() + seconds
    while time.time() < end and not _stop.is_set():
        time.sleep(min(30, end - time.time()))


# ---------------------------------------------------------------- chạy 1 bước

def run_step(args: list[str], log: Path) -> tuple[bool, str]:
    cmd = [sys.executable, str(ROOT / "studio.py"), *args]
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n$ {' '.join(args)}\n")
        f.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                                env={**_env(), "PYTHONUNBUFFERED": "1"})
        with _lock:
            _children.add(proc)
        try:
            proc.wait()
        finally:
            with _lock:
                _children.discard(proc)
    tail = log.read_text(encoding="utf-8", errors="ignore")[-4000:]
    return proc.returncode == 0, tail


def _env() -> dict:
    import os

    e = dict(os.environ)
    e.setdefault("PYTHONIOENCODING", "utf-8")
    return e


def do_topic(ch: dict, topic: str, years: str) -> str:
    slug = slugify(topic)
    log = LOGS / f"{slug}.log"
    preset, lang = ch["preset"], ch.get("language", "en")
    fails = 0
    while fails < 4:  # chờ hết lượt Claude không tính là lỗi
        if _stop.is_set():
            return "stopped"
        st = state(ch, topic)
        if st == "done":
            return "ok"
        if st == "research":
            a = ["--preset", preset, "new", topic, "--language", lang, "--minutes", str(ch.get("minutes", 20))]
            if years and years != "2026":
                a += ["--years", years]
            if ch.get("story_type"):
                a += ["--story-type", ch["story_type"]]
            if ch.get("notes"):
                a += ["--notes", str(ROOT / ch["notes"])]
            if ch.get("aspect"):
                a += ["--aspect", ch["aspect"]]
            say(f"  {slug}: tìm tư liệu")
        elif st == "script":
            a = ["--preset", preset, "script", slug]
            say(f"  {slug}: viết kịch bản")
        else:
            a = ["--preset", preset, "translate", slug, "--to", ch["translate_to"]]
            say(f"  {slug}: dịch sang {ch['translate_to']}")
        ok, tail = run_step(a, log)
        if ok:
            continue
        if _stop.is_set():
            return "stopped"
        wait = reset_wait_seconds(tail)
        if wait is not None:
            say(f"  HẾT LƯỢT Claude - {slug} chờ {wait // 60} phút rồi chạy tiếp")
            sleep_until(wait)
            continue
        if "Wikipedia không trả kết quả" in tail:
            say(f"  {slug}: Wikipedia chưa trả kết quả - để lượt sau")
            return "no_source"
        fails += 1
        say(f"  {slug}: LỖI ở bước {st} (xem batch/logs/{slug}.log) - thử lại sau 2 phút")
        sleep_until(120)
    return "fail"


# ---------------------------------------------------------------- tiến độ

def status(q: dict, only: str | None = None) -> str:
    lines = [f"Tiến độ viết kịch bản - {dt.datetime.now():%d/%m/%Y %H:%M}", ""]
    for ch in q["channels"]:
        if only and ch["name"] != only:
            continue
        topics = read_topics(ROOT / ch["topics"])
        sts = [state(ch, t) for t, _ in topics]
        done = sts.count("done")
        lines.append(f"{ch['name']:<12} {done:>3}/{len(topics)} xong"
                     + (f" | còn: {', '.join(slugify(t) for (t, _), s in zip(topics, sts) if s != 'done')[:300]}"
                        if done < len(topics) else ""))
    txt = "\n".join(lines) + "\n"
    (BATCH / "TIEN_DO.txt").write_text(txt, encoding="utf-8")
    return txt


def keep_awake(on: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Viết kịch bản hàng loạt theo batch/queue.yaml")
    ap.add_argument("--queue", default=str(BATCH / "queue.yaml"))
    ap.add_argument("--channel", help="chỉ chạy kênh này (tên trong queue.yaml)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--parallel", type=int)
    a = ap.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)

    def _sigint(sig, frm):  # Ctrl+C: báo các luồng dừng, tắt các bước đang chạy (bước dở sẽ chạy lại lần sau)
        _stop.set()
        for pr in list(_children):
            try:
                pr.terminate()
            except Exception:  # noqa: BLE001
                pass
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint)
    q = load_queue(Path(a.queue))
    if a.status:
        print(status(q, a.channel))
        return
    par = a.parallel or int(q["parallel"])
    keep_awake(True)
    try:
        for ch in q["channels"]:
            if a.channel and ch["name"] != a.channel:
                continue
            if ch.get("enabled") is False:
                continue
            todo = [(t, y) for t, y in read_topics(ROOT / ch["topics"]) if state(ch, t) != "done"]
            say(f"== Kênh {ch['name']}: {len(todo)} chủ đề cần viết")
            if a.dry:
                for t, y in todo:
                    print(f"   {state(ch, t):<9} {t} {y}")
                continue
            for rnd in (1, 2):  # vòng 2: thử lại chủ đề lỗi / thiếu nguồn
                todo = [(t, y) for t, y in todo if state(ch, t) != "done"]
                if not todo:
                    break
                if rnd == 2:
                    say(f"   thử lại {len(todo)} chủ đề sau 10 phút")
                    sleep_until(600)
                with ThreadPoolExecutor(max_workers=par) as ex:
                    res = list(ex.map(lambda ty: (ty[0], do_topic(ch, *ty)), todo))
                for t, r in res:
                    if r == "ok":
                        say(f"  ✓ {slugify(t)}")
            say(f"== Xong kênh {ch['name']}")
            status(q)
    except KeyboardInterrupt:
        _stop.set()
        say("Đã dừng. Chạy lại lệnh để tiếp tục từ chỗ dở.")
    finally:
        keep_awake(False)
    print(status(q, a.channel))


if __name__ == "__main__":
    main()

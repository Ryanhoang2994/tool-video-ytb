"""Thư viện ảnh dùng chung cho mọi video (library/).

- Mọi ảnh cào về được lưu 1 lần, kèm metadata: nguồn, giấy phép, credit, từ khoá, kích thước, hash.
- Tự loại ảnh trùng / gần trùng (perceptual hash) - giữ bản phân giải cao hơn.
- Xếp hạng độ liên quan: từ khoá + (tuỳ chọn) AI CLIP hiểu nội dung ảnh (pip install sentence-transformers).
- Lệnh:  python studio.py collect "Lizzie Borden" --max 300      (cào hàng loạt theo chủ đề)
         python studio.py library --search "1890s police"         (tìm trong thư viện)
         python studio.py library --gallery                        (xem toàn bộ thư viện dạng web)
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

from . import sources
from .util import ROOT, download, log

LIB = ROOT / "library"
SRC_BONUS = {"wiki_article": 0.6, "loc_news": 0.25, "loc": 0.2, "wikimedia": 0.15, "smithsonian": 0.1,
             "europeana": 0.1, "flickr": 0.1}
_lock = threading.Lock()


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower())} - {"the", "and", "with", "from", "file", "jpg",
                                                                          "png", "photo", "image"}


def keyword_score(query: str, text: str) -> float:
    q = _words(query)
    return len(q & _words(text)) / len(q) if q else 0.0


def era_ok(query: str, text: str, tolerance: int = 20) -> bool:
    """Từ khoá có năm/thập niên (vd '1930s', '1971') thì loại tư liệu ghi năm lệch quá xa (vd video 2015 cho cảnh 1937)."""
    qy = [int(y) for y in re.findall(r"\b(1[89]\d\d|20[0-3]\d)s?\b", query)]
    if not qy:
        return True
    ty = [int(y) for y in re.findall(r"\b(1[89]\d\d|20[0-3]\d)\b", text or "")]
    if not ty:
        return True
    q = min(qy)
    return any(abs(y - q) <= tolerance for y in ty)


MODERN = re.compile(r"\b(f-\d\d\w*|drone|quadcopter|smartphone|iphone|android|4k|uhd|gopro|tesla|covid|"
                    r"airbus a3[2-8]0|boeing 7[78]7|a380|led screen|selfie|tiktok|youtube)\b", re.I)


def era_ok_strict(query: str, text: str) -> bool:
    """Như era_ok + loại thứ quá hiện đại khi từ khoá thuộc thời trước 1990."""
    qy = [int(y) for y in re.findall(r"\b(1[89]\d\d)s?\b", query)]
    if qy and min(qy) < 1990 and MODERN.search(text or ""):
        return False
    return era_ok(query, text)


def dhash(path: Path) -> int:
    with Image.open(path) as im:
        g = ImageOps.grayscale(im).resize((9, 8), Image.BILINEAR)
    px = list(g.getdata())
    return sum(1 << i for i in range(64) if px[(i // 8) * 9 + i % 8] > px[(i // 8) * 9 + i % 8 + 1])


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class Library:
    def __init__(self):
        (LIB / "images").mkdir(parents=True, exist_ok=True)
        self.index_path = LIB / "index.json"
        self.items: dict[str, dict] = json.loads(self.index_path.read_text("utf-8")) if self.index_path.exists() else {}
        self._clip = None

    def save(self):
        with _lock:
            tmp = self.index_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(self.index_path)

    @staticmethod
    def key(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:16]

    # ---------- thêm ảnh ----------
    def add(self, c: dict, query: str = "", min_w: int = 700) -> dict | None:
        k = self.key(c["url"])
        with _lock:
            if k in self.items:
                rec = self.items[k]
                if query and query not in rec["queries"]:
                    rec["queries"].append(query)
                return rec if Path(rec["file"]).exists() and not rec.get("dup_of") else None
        raw = LIB / "images" / f"{k}.part_img"
        if not download(c["url"], raw, max_mb=60):
            return None
        out = LIB / "images" / f"{k}.jpg"
        try:
            with Image.open(raw) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                if im.width < min_w and im.height < min_w:
                    raw.unlink(missing_ok=True)
                    return None
                if max(im.size) > 4200:
                    im.thumbnail((4200, 4200), Image.LANCZOS)
                im.save(out, quality=92)
                w, h = im.size
        except Exception:  # noqa: BLE001
            raw.unlink(missing_ok=True)
            return None
        raw.unlink(missing_ok=True)
        hsh = dhash(out)
        rec = {"id": k, "url": c["url"], "src": c["src"], "page": c.get("page", ""), "title": c.get("title", "")[:500],
               "credit": c.get("credit", ""), "license": c.get("license", ""), "queries": [query] if query else [],
               "file": str(out), "w": w, "h": h, "hash": hsh, "visual": c.get("visual", ""),
               "focus": c.get("focus"), "used_in": []}
        with _lock:
            for other in self.items.values():
                if other.get("dup_of") or other.get("hash") is None:
                    continue
                if hamming(other["hash"], hsh) <= 5:  # gần trùng
                    if w * h > other["w"] * other["h"]:
                        other["dup_of"] = k
                    else:
                        rec["dup_of"] = other["id"]
                    break
            self.items[k] = rec
        return None if rec.get("dup_of") else rec

    # ---------- tìm kiếm ----------
    def local_search(self, query: str, n: int = 20, exclude: set[str] | None = None) -> list[dict]:
        scored = []
        for r in self.items.values():
            if r.get("dup_of") or (exclude and r["id"] in exclude) or not Path(r["file"]).exists():
                continue
            s = keyword_score(query, r["title"] + " " + " ".join(r["queries"]))
            if query in r["queries"]:
                s += 0.5
            if s > 0:
                scored.append((s, r))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:n]]

    def rank(self, query: str, recs: list[dict], use_clip: bool = False) -> list[dict]:
        def base(r):
            s = keyword_score(query, r["title"] + " " + " ".join(r["queries"]))
            s += SRC_BONUS.get(_src_key(r["src"]), 0)
            s += min(r["w"], 2400) / 2400 * 0.15  # ưu tiên ảnh nét
            return s

        recs = [r for r in recs if era_ok(query, r["title"])] or recs
        scores = {r["id"]: base(r) for r in recs}
        if use_clip and recs:
            sims = self.clip_scores(query, recs)
            for r in recs:
                scores[r["id"]] += 2.0 * sims.get(r["id"], 0)
        return sorted(recs, key=lambda r: -scores[r["id"]])

    def clip_scores(self, query: str, recs: list[dict]) -> dict[str, float]:
        try:
            if self._clip is None:
                from sentence_transformers import SentenceTransformer  # type: ignore

                log("  (nạp model CLIP để chấm điểm ảnh...)")
                self._clip = SentenceTransformer("clip-ViT-B-32")
            import numpy as np

            cache_p = LIB / "clip_cache.npz"
            cache = dict(np.load(cache_p)) if cache_p.exists() else {}
            need = [r for r in recs if r["id"] not in cache]
            if need:
                ims = []
                for r in need:
                    with Image.open(r["file"]) as im:
                        ims.append(im.convert("RGB").copy())
                embs = self._clip.encode(ims, batch_size=16, convert_to_numpy=True, normalize_embeddings=True)
                for r, e in zip(need, embs):
                    cache[r["id"]] = e
                np.savez(cache_p, **cache)
            q = self._clip.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
            return {r["id"]: float(cache[r["id"]] @ q) for r in recs}
        except ImportError:
            return {}
        except Exception as e:  # noqa: BLE001
            log(f"  ! CLIP lỗi: {e}")
            return {}

    # ---------- cào từ nguồn ----------
    def fetch(self, query: str, srcs: list[str], per_source: int = 12, min_w: int = 800, workers: int = 3,
              max_dl: int = 16) -> list[dict]:
        cands = sources.search_images(query, srcs, per_source, min_w)
        cands.sort(key=lambda c: -(keyword_score(query, c["title"]) + SRC_BONUS.get(_src_key(c["src"]), 0)))
        cands = cands[:max_dl]  # chỉ tải những ảnh tiêu đề khớp nhất (trước đây tải hết -> rất chậm)
        with ThreadPoolExecutor(workers) as ex:
            recs = list(ex.map(lambda c: self.add(c, query, min_w), cands))
        self.save()
        return [r for r in recs if r]


def _src_key(src: str) -> str:
    s = src.lower()
    if s.startswith("wikipedia:"):
        return "wiki_article"
    if "chronicling" in s:
        return "loc_news"
    if "library of congress" in s:
        return "loc"
    if "commons" in s and "flickr" not in s:
        return "wikimedia"
    return s.split("/")[0].split()[0]


def collect_topic(topic: str, extra_queries: list[str], cfg: dict, max_images: int = 300) -> None:
    """Cào hàng loạt ảnh cho 1 chủ đề vào thư viện."""
    lib = Library()
    srcs = cfg["media"].get("image_sources", list(sources.IMAGE_SOURCES))
    queries = [topic] + extra_queries
    # tự sinh thêm biến thể truy vấn
    years = re.findall(r"\b1[6-9]\d\d\b", topic + " " + " ".join(extra_queries))
    for y in years[:1]:
        queries += [f"{y[:3]}0s police", f"{y[:3]}0s street", f"{y[:3]}0s newspaper"]
    total = 0
    for q in queries:
        if total >= max_images:
            break
        log(f"Cào: '{q}'")
        got = lib.fetch(q, srcs, per_source=min(30, max_images // max(1, len(srcs))))
        total += len(got)
        log(f"  +{len(got)} ảnh mới (tổng {total})")
    log(f"✓ Thư viện: {sum(1 for r in lib.items.values() if not r.get('dup_of'))} ảnh -> {LIB}")
    gallery(lib, LIB / "gallery.html", filter_query=topic if not extra_queries else "")


def gallery(lib: Library, out: Path, filter_query: str = "", recs: list[dict] | None = None) -> Path:
    recs = recs if recs is not None else [r for r in lib.items.values() if not r.get("dup_of")]
    if filter_query:
        recs = lib.local_search(filter_query, n=2000) or recs
    cards = []
    for r in recs:
        rel = os.path.relpath(r["file"], out.parent).replace("\\", "/")
        cards.append(f'<figure><a href="{html.escape(r["page"] or rel)}" target="_blank"><img loading="lazy" '
                     f'src="{html.escape(rel)}"></a><figcaption><b>{r["id"]}</b> · {html.escape(r["src"])} · '
                     f'{r["w"]}×{r["h"]}<br>{html.escape(r["title"][:140])}<br><i>{html.escape(r["license"])}</i>'
                     f'</figcaption></figure>')
    out.write_text(f"""<!doctype html><meta charset="utf-8"><title>Image library</title>
<style>body{{background:#111;color:#ddd;font:13px system-ui;margin:16px}}main{{display:grid;
grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}figure{{margin:0;background:#1c1c1c;padding:6px;
border-radius:6px}}img{{width:100%;height:170px;object-fit:cover;border-radius:4px}}figcaption{{margin-top:4px;
line-height:1.35;color:#aaa}}b{{color:#e8c070}}</style><h2>{len(recs)} ảnh</h2><main>{''.join(cards)}</main>""",
                   "utf-8")
    log(f"✓ Gallery: {out}")
    return out

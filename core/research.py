"""Thu thập tư liệu về vụ án từ các nguồn công khai.

Nguồn:
  - Wikipedia (vi/en...)       : tóm tắt + toàn văn bài viết
  - Chronicling America (LoC)  : báo Mỹ 1770-1963 (public domain) - OCR toàn văn
  - Internet Archive           : sách, báo, tài liệu cũ (full-text search)
  - URL bạn tự đưa vào          : bài báo, blog, hồ sơ... (--url)
  - File ghi chú của bạn        : .txt/.md (--notes)
Kết quả lưu vào projects/<slug>/research.json
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from .util import Project, http_get, http_json, log


# ---------------- Wikipedia ----------------

def wikipedia(query: str, lang: str = "en", limit: int = 3, max_chars: int = 12000) -> list[dict]:
    api = f"https://{lang}.wikipedia.org/w/api.php"
    out = []
    try:
        res = http_json(api, params={"action": "query", "list": "search", "srsearch": query,
                                     "srlimit": limit, "format": "json"})
        for hit in res.get("query", {}).get("search", []):
            title = hit["title"]
            page = http_json(api, params={"action": "query", "prop": "extracts|info", "explaintext": 1,
                                          "inprop": "url", "titles": title, "format": "json", "redirects": 1})
            for p in page.get("query", {}).get("pages", {}).values():
                text = (p.get("extract") or "").strip()
                if len(text) < 300:
                    continue
                out.append({"source": f"Wikipedia ({lang})", "title": p.get("title"),
                            "url": p.get("fullurl"), "date": "", "text": text[:max_chars]})
    except Exception as e:  # noqa: BLE001
        log(f"  ! Wikipedia {lang}: {e}")
    return out


# ---------------- Chronicling America (báo Mỹ cũ) ----------------

def chronicling_america(query: str, limit: int = 15, max_chars: int = 6000,
                        date_from: str = "", date_to: str = "") -> list[dict]:
    out = []
    # API cổ điển (trả OCR luôn)
    try:
        params = {"andtext": query, "format": "json", "rows": limit}
        if date_from or date_to:
            params.update({"dateFilterType": "yearRange", "date1": date_from or "1770", "date2": date_to or "1963"})
        res = http_json("https://chroniclingamerica.loc.gov/search/pages/results/", params=params, timeout=40)
        for it in res.get("items", [])[:limit]:
            text = re.sub(r"\s+", " ", it.get("ocr_eng") or "")
            text = _window_around(text, query, max_chars)
            if not text:
                continue
            out.append({"source": "Chronicling America (LoC)", "title": f"{it.get('title', '')} - {it.get('date', '')}",
                        "url": "https://chroniclingamerica.loc.gov" + it.get("id", ""), "date": it.get("date", ""),
                        "text": text})
        if out:
            return out
    except Exception as e:  # noqa: BLE001
        log(f"  ! ChroniclingAmerica (API cũ): {e}")
    # API mới loc.gov
    try:
        res = http_json("https://www.loc.gov/collections/chronicling-america/",
                        params={"q": query, "fo": "json", "c": limit}, timeout=40)
        for it in res.get("results", [])[:limit]:
            desc = it.get("description") or []
            text = " ".join(desc) if isinstance(desc, list) else str(desc)
            out.append({"source": "Chronicling America (loc.gov)", "title": it.get("title", ""),
                        "url": it.get("url", ""), "date": it.get("date", ""), "text": text[:max_chars]})
    except Exception as e:  # noqa: BLE001
        log(f"  ! ChroniclingAmerica (loc.gov): {e}")
    return out


def _window_around(text: str, query: str, max_chars: int) -> str:
    """Lấy đoạn văn bản quanh từ khoá (trang báo OCR rất dài)."""
    if len(text) <= max_chars:
        return text
    words = [w for w in re.findall(r"\w{4,}", query.lower())]
    low = text.lower()
    pos = min([low.find(w) for w in words if low.find(w) >= 0] or [0])
    start = max(0, pos - max_chars // 3)
    return text[start:start + max_chars]


# ---------------- Internet Archive ----------------

def internet_archive(query: str, limit: int = 10, max_chars: int = 6000) -> list[dict]:
    out = []
    try:
        res = http_json("https://archive.org/advancedsearch.php", params={
            "q": f'({query}) AND mediatype:texts', "fl[]": ["identifier", "title", "date", "description"],
            "rows": limit, "output": "json"}, timeout=40)
        for d in res.get("response", {}).get("docs", []):
            ident = d["identifier"]
            desc = d.get("description") or ""
            if isinstance(desc, list):
                desc = " ".join(desc)
            text = BeautifulSoup(desc, "html.parser").get_text(" ")
            # thử lấy full text OCR (_djvu.txt)
            try:
                meta = http_json(f"https://archive.org/metadata/{ident}", timeout=30)
                txt = next((f["name"] for f in meta.get("files", []) if f["name"].endswith("_djvu.txt")), None)
                if txt:
                    r = http_get(f"https://archive.org/download/{ident}/{txt}", timeout=60)
                    full = re.sub(r"\s+", " ", r.text)
                    text = _window_around(full, query, max_chars)
            except Exception:  # noqa: BLE001
                pass
            if len(text) < 200:
                continue
            out.append({"source": "Internet Archive", "title": d.get("title", ident),
                        "url": f"https://archive.org/details/{ident}", "date": str(d.get("date", "")),
                        "text": text[:max_chars]})
    except Exception as e:  # noqa: BLE001
        log(f"  ! Internet Archive: {e}")
    return out


# ---------------- URL / ghi chú ----------------

def fetch_url(url: str, max_chars: int = 15000) -> dict | None:
    try:
        html = http_get(url, timeout=40).text
        text = ""
        try:
            import trafilatura  # type: ignore

            text = trafilatura.extract(html) or ""
        except ImportError:
            pass
        if not text:
            soup = BeautifulSoup(html, "html.parser")
            for t in soup(["script", "style", "nav", "footer", "header", "aside"]):
                t.decompose()
            text = "\n".join(p.get_text(" ", strip=True) for p in soup.find_all(["p", "h1", "h2", "h3", "li"]))
        title = BeautifulSoup(html, "html.parser").title
        return {"source": "URL", "title": title.get_text(strip=True) if title else url, "url": url,
                "date": "", "text": text[:max_chars]}
    except Exception as e:  # noqa: BLE001
        log(f"  ! Không đọc được {url}: {e}")
        return None


def read_notes(path: str) -> dict:
    p = Path(path)
    return {"source": "Ghi chú riêng", "title": p.name, "url": "", "date": "",
            "text": p.read_text(encoding="utf-8", errors="ignore")}


# ---------------- Tổng hợp ----------------

def read_reference(path: str) -> dict:
    """Transcript video khác (vd lấy từ youtube-transcript.io). Chỉ dùng làm THAM KHẢO sự kiện,
    kịch bản sẽ được viết mới hoàn toàn."""
    p = Path(path)
    text = re.sub(r"\[?\d{1,2}:\d{2}(:\d{2})?\]?", " ", p.read_text(encoding="utf-8", errors="ignore"))
    return {"source": "REFERENCE", "title": f"Transcript tham khảo: {p.name}", "url": "", "date": "",
            "text": re.sub(r"[ \t]+", " ", text)}


def run_research(project: Project, topic: str, cfg: dict, *, en_query: str = "", urls: list[str] | None = None,
                 notes: list[str] | None = None, years: str = "", references: list[str] | None = None) -> list[dict]:
    rc = cfg.get("research", {})
    max_chars = rc.get("max_chars_per_source", 12000)
    q_en = en_query or topic
    date_from, date_to = (years.split("-") + [""])[:2] if years else ("", "")
    sources: list[dict] = []

    for lang in rc.get("wikipedia_langs", ["vi", "en"]):
        q = q_en if lang == "en" else topic
        log(f"Wikipedia [{lang}]: {q}")
        sources += wikipedia(q, lang, max_chars=max_chars)

    n = rc.get("max_newspaper_hits", 25)
    log(f"Báo cũ Chronicling America: {q_en}")
    sources += chronicling_america(q_en, limit=min(n, 20), date_from=date_from, date_to=date_to)
    log(f"Internet Archive: {q_en}")
    sources += internet_archive(q_en, limit=min(n, 8))

    for u in urls or []:
        log(f"URL: {u}")
        s = fetch_url(u, max_chars)
        if s:
            sources.append(s)
    for nfile in notes or []:
        sources.append(read_notes(nfile))
    for rfile in references or []:
        sources.append(read_reference(rfile))

    # bỏ trùng
    seen, uniq = set(), []
    for s in sources:
        key = (s["url"] or s["title"]).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)

    data = {"topic": topic, "en_query": q_en, "years": years, "sources": uniq}
    project.write_json("research.json", data)
    total = sum(len(s["text"]) for s in uniq)
    log(f"✓ {len(uniq)} nguồn, {total:,} ký tự -> {project.path('research.json')}")
    return uniq

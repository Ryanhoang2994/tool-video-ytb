"""Tất cả nguồn ảnh / video. Mỗi hàm trả về list "candidate":
  {kind, src, url, page, title, credit, license, width, height, [duration], [remote_cut], [focus]}
Chỉ lấy nguồn có giấy phép rõ ràng (public domain / CC / giấy phép stock miễn phí).

Nguồn ảnh                    Key cần có (.env)        Ghi chú
  wiki_article  Ảnh trong chính bài Wikipedia vụ án      -            đúng người/địa điểm thật nhất
  wikimedia     Wikimedia Commons                         -
  loc           Library of Congress - ảnh                 -            ảnh báo chí, cảnh sát Mỹ xưa
  loc_news      Library of Congress - trang báo scan      -            "newspaper clipping"
  openverse     Openverse (Flickr CC...)                  -
  europeana     Europeana (lưu trữ châu Âu)               EUROPEANA_API_KEY (mặc định key demo)
  smithsonian   Smithsonian Open Access (CC0)             SMITHSONIAN_API_KEY (mặc định DEMO_KEY)
  flickr        Flickr Commons (no known restrictions)    FLICKR_API_KEY
  archive_img   Internet Archive (ảnh)                    -
  pexels        Pexels                                    PEXELS_API_KEY
  pixabay       Pixabay                                   PIXABAY_API_KEY
  unsplash      Unsplash                                  UNSPLASH_ACCESS_KEY
Nguồn video: pexels_video, pixabay_video, archive_video
"""
from __future__ import annotations

import os
import re

from .util import http_json, log

NONFREE = re.compile(r"non-free|fair use|copyrighted|all rights reserved", re.I)


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", html or "")).strip()


def commons_url(orig: str, width: int, target: int = 1920) -> str:
    """URL ảnh Wikimedia sạch (bỏ ?utm_...), ảnh lớn thì lấy bản thu nhỏ chuẩn 1920px (được cache, ít bị 429)."""
    orig = orig.split("?")[0]
    if width <= target or "/commons/" not in orig or orig.lower().endswith((".gif", ".svg", ".tif", ".tiff")):
        return orig
    head, tail = orig.split("/commons/", 1)  # tail = a/ab/Name.jpg
    name = tail.rsplit("/", 1)[-1]
    return f"{head}/commons/thumb/{tail}/{target}px-{name}"


def _commons_pages(res: dict, min_w: int, src: str) -> list[dict]:
    out = []
    for p in (res.get("query", {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii or ii.get("width", 0) < min_w or "image" not in ii.get("mime", "image"):
            continue
        if ii.get("mime") in ("image/svg+xml",) and ii.get("width", 0) < 1200:
            continue
        meta = ii.get("extmetadata", {})
        lic = _strip(meta.get("LicenseShortName", {}).get("value", ""))
        if NONFREE.search(lic) or NONFREE.search(meta.get("UsageTerms", {}).get("value", "")):
            continue  # bỏ ảnh fair-use / không tự do
        artist = _strip(meta.get("Artist", {}).get("value", ""))[:80]
        desc = _strip(meta.get("ImageDescription", {}).get("value", ""))[:300]
        date = _strip(meta.get("DateTimeOriginal", {}).get("value", ""))[:40]
        title = p.get("title", "").replace("File:", "")
        url = commons_url(ii["url"], ii.get("width", 0))
        out.append({"kind": "image", "src": src, "url": url,
                    "page": ii.get("descriptionurl", ""), "title": f"{title} {desc} {date}",
                    "license": lic, "width": ii.get("width", 0), "height": ii.get("height", 0),
                    "credit": f"{title} - {artist or 'unknown'} ({lic}) via Wikimedia Commons"})
    return out


II_PROPS = {"prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1920, "format": "json"}
# Wikimedia chỉ phục vụ ảnh thu nhỏ ở kích thước chuẩn (vd 1920px); kích thước lạ dễ bị chặn 429


def wikimedia(q: str, n: int = 15, min_w: int = 900) -> list[dict]:
    res = http_json("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": n, **II_PROPS})
    return _commons_pages(res, min_w, "Wikimedia Commons")


def wiki_article(q: str, n: int = 40, min_w: int = 500, lang: str = "en") -> list[dict]:
    """Ảnh được dùng trong bài Wikipedia khớp nhất với q (thường là ảnh thật của vụ án)."""
    api = f"https://{lang}.wikipedia.org/w/api.php"
    s = http_json(api, params={"action": "query", "list": "search", "srsearch": q, "srlimit": 2, "format": "json"})
    out = []
    for hit in s.get("query", {}).get("search", []):
        res = http_json(api, params={"action": "query", "titles": hit["title"], "generator": "images",
                                     "gimlimit": n, **II_PROPS})
        for c in _commons_pages(res, min_w, f"Wikipedia: {hit['title']}"):
            if re.search(r"(icon|logo|symbol|flag|commons-|wiki|edit-clear|question_book)", c["url"], re.I):
                continue
            c["title"] += f" {hit['title']}"
            out.append(c)
    return out


def loc(q: str, n: int = 15, min_w: int = 0) -> list[dict]:
    res = http_json("https://www.loc.gov/photos/", params={"q": q, "fo": "json", "c": n})
    return _loc_items(res, "Library of Congress")


def loc_news(q: str, n: int = 8, min_w: int = 0) -> list[dict]:
    """Trang báo Mỹ 1770-1963 (public domain) - dựng thành 'mẩu báo cắt'."""
    res = http_json("https://www.loc.gov/collections/chronicling-america/", params={"q": q, "fo": "json", "c": n})
    items = _loc_items(res, "Chronicling America (LoC)", require_free=False)
    for it in items:
        it["visual"] = "newspaper"
        it["focus"] = [0.5, 0.18]  # tít báo thường ở phía trên
    return items


def _loc_items(res: dict, src: str, require_free: bool = True) -> list[dict]:
    out = []
    for it in res.get("results", []):
        imgs = [u for u in (it.get("image_url") or []) if isinstance(u, str)]
        if not imgs:
            continue
        url = imgs[-1].split("#")[0]
        if url.startswith("//"):
            url = "https:" + url
        rights = it.get("rights") or ""
        rights = " ".join(rights) if isinstance(rights, list) else str(rights)
        if require_free and rights and not re.search(r"no known restrictions|public domain", rights, re.I):
            continue
        title = it.get("title", "")
        date = it.get("date", "")
        out.append({"kind": "image", "src": src, "url": url, "page": it.get("url", ""),
                    "title": f"{title} {date} {' '.join(it.get('subject') or [])}", "license": "Public domain",
                    "width": 0, "height": 0, "credit": f"{title[:90]} ({date}) - {src}"})
    return out


def openverse(q: str, n: int = 15, min_w: int = 900) -> list[dict]:
    res = http_json("https://api.openverse.org/v1/images/", params={
        "q": q, "page_size": n, "license_type": "commercial,modification", "mature": "false"})
    out = []
    for it in res.get("results", []):
        if (it.get("width") or 0) and it["width"] < min_w:
            continue
        lic = f"{it.get('license', '').upper()} {it.get('license_version', '')}".strip()
        out.append({"kind": "image", "src": f"Openverse/{it.get('source', '')}", "url": it["url"],
                    "page": it.get("foreign_landing_url", ""), "license": lic,
                    "width": it.get("width") or 0, "height": it.get("height") or 0,
                    "title": it.get("title", "") + " " + " ".join(t.get("name", "") for t in it.get("tags") or []),
                    "credit": f"\"{it.get('title', '')}\" by {it.get('creator', '?')} ({lic})"})
    return out


def europeana(q: str, n: int = 15, min_w: int = 0) -> list[dict]:
    res = http_json("https://api.europeana.eu/record/v2/search.json", params={
        "wskey": os.getenv("EUROPEANA_API_KEY", "api2demo"), "query": q, "rows": n, "media": "true",
        "qf": "TYPE:IMAGE", "reusability": "open", "profile": "rich"})
    out = []
    for it in res.get("items", []):
        url = (it.get("edmIsShownBy") or it.get("edmPreview") or [None])[0]
        if not url:
            continue
        title = " ".join(it.get("title") or [])
        lic = (it.get("rights") or [""])[0]
        prov = " ".join(it.get("dataProvider") or [])
        out.append({"kind": "image", "src": "Europeana", "url": url, "page": it.get("guid", ""), "license": lic,
                    "width": 0, "height": 0, "title": f"{title} {' '.join(it.get('dcDescription') or [])[:200]}",
                    "credit": f"{title[:80]} - {prov} via Europeana ({lic})"})
    return out


def smithsonian(q: str, n: int = 15, min_w: int = 0) -> list[dict]:
    res = http_json("https://api.si.edu/openaccess/api/v1.0/search", params={
        "q": f'{q} AND online_media_type:"Images"', "rows": n,
        "api_key": os.getenv("SMITHSONIAN_API_KEY", "DEMO_KEY")})
    out = []
    for row in (res.get("response") or {}).get("rows", []):
        dn = (row.get("content") or {}).get("descriptiveNonRepeating", {})
        if (dn.get("metadata_usage") or {}).get("access") != "CC0":
            continue
        for m in ((dn.get("online_media") or {}).get("media") or [])[:1]:
            url = m.get("content") or ""
            res_list = m.get("resources") or []
            big = [r.get("url") for r in res_list if "jpg" in (r.get("label", "") + r.get("url", "")).lower()]
            url = big[-1] if big else url
            if not url:
                continue
            out.append({"kind": "image", "src": "Smithsonian", "url": url, "page": dn.get("record_link", ""),
                        "license": "CC0", "width": 0, "height": 0, "title": row.get("title", ""),
                        "credit": f"{row.get('title', '')[:90]} - Smithsonian Open Access (CC0)"})
    return out


def flickr(q: str, n: int = 15, min_w: int = 900) -> list[dict]:
    key = os.getenv("FLICKR_API_KEY")
    if not key:
        return []
    res = http_json("https://api.flickr.com/services/rest/", params={
        "method": "flickr.photos.search", "api_key": key, "text": q, "is_commons": "true", "per_page": n,
        "extras": "url_l,url_o,owner_name,description,date_taken", "format": "json", "nojsoncallback": 1})
    out = []
    for p in (res.get("photos") or {}).get("photo", []):
        url = p.get("url_o") or p.get("url_l")
        if not url or int(p.get("width_o") or p.get("width_l") or 0) < min_w:
            continue
        out.append({"kind": "image", "src": "Flickr Commons", "url": url, "license": "No known copyright restrictions",
                    "page": f"https://www.flickr.com/photos/{p['owner']}/{p['id']}", "width": 0, "height": 0,
                    "title": p.get("title", "") + " " + _strip((p.get("description") or {}).get("_content", ""))[:200],
                    "credit": f"\"{p.get('title', '')}\" - {p.get('ownername', '')} (Flickr Commons)"})
    return out


def archive_img(q: str, n: int = 10, min_w: int = 0) -> list[dict]:
    res = http_json("https://archive.org/advancedsearch.php", params={
        "q": f"({q}) AND mediatype:image AND (licenseurl:*publicdomain* OR licenseurl:*creativecommons*)",
        "fl[]": ["identifier", "title", "licenseurl"], "rows": n, "output": "json"}, timeout=40)
    out = []
    for d in res.get("response", {}).get("docs", []):
        ident = d["identifier"]
        try:
            meta = http_json(f"https://archive.org/metadata/{ident}", timeout=30)
        except Exception:  # noqa: BLE001
            continue
        imgs = [f for f in meta.get("files", []) if f["name"].lower().endswith((".jpg", ".jpeg", ".png"))
                and f.get("source") == "original"]
        if not imgs:
            continue
        f = max(imgs, key=lambda f: int(f.get("size", 0)))
        lic = d.get("licenseurl", "")
        out.append({"kind": "image", "src": "Internet Archive", "url": f"https://archive.org/download/{ident}/{f['name']}",
                    "page": f"https://archive.org/details/{ident}", "license": lic, "width": 0, "height": 0,
                    "title": str(d.get("title", ident)), "credit": f"\"{d.get('title', ident)}\" - Internet Archive ({lic})"})
    return out


def pexels(q: str, n: int = 15, min_w: int = 0) -> list[dict]:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    res = http_json("https://api.pexels.com/v1/search", params={"query": q, "per_page": n, "orientation": "landscape"},
                    headers={"Authorization": key})
    return [{"kind": "image", "src": "Pexels", "url": p["src"]["large2x"], "page": p["url"], "license": "Pexels License",
             "width": p.get("width", 0), "height": p.get("height", 0),
             "title": p.get("alt", ""), "credit": f"Photo by {p['photographer']} on Pexels"} for p in res.get("photos", [])]


def pixabay(q: str, n: int = 15, min_w: int = 0) -> list[dict]:
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return []
    res = http_json("https://pixabay.com/api/", params={"key": key, "q": q, "per_page": max(n, 3),
                                                        "orientation": "horizontal", "safesearch": "true"})
    return [{"kind": "image", "src": "Pixabay", "url": h["largeImageURL"], "page": h["pageURL"], "license": "Pixabay License",
             "width": h.get("imageWidth", 0), "height": h.get("imageHeight", 0), "title": h.get("tags", ""),
             "credit": f"Image by {h['user']} on Pixabay"} for h in res.get("hits", [])]


def unsplash(q: str, n: int = 15, min_w: int = 0) -> list[dict]:
    key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
    res = http_json("https://api.unsplash.com/search/photos", params={"query": q, "per_page": n,
                                                                      "orientation": "landscape"},
                    headers={"Authorization": f"Client-ID {key}"})
    return [{"kind": "image", "src": "Unsplash", "url": r["urls"]["full"] + "&w=2400", "page": r["links"]["html"],
             "license": "Unsplash License", "width": r.get("width", 0), "height": r.get("height", 0),
             "title": (r.get("alt_description") or "") + " " + (r.get("description") or ""),
             "credit": f"Photo by {r['user']['name']} on Unsplash"} for r in res.get("results", [])]


# ---------------- VIDEO ----------------

def _commons_transcode(orig: str, height: int) -> str:
    """URL bản chuyển mã nhẹ (480p/720p webm) mà Wikimedia tạo sẵn cho mọi video."""
    orig = orig.split("?")[0]
    head, tail = orig.split("/commons/", 1)
    name = tail.rsplit("/", 1)[-1]
    return f"{head}/commons/transcoded/{tail}/{name}.{height}p.vp9.webm"


def wikimedia_video(q: str, n: int = 8) -> list[dict]:
    """Video public domain / CC trên Wikimedia Commons (phim thời sự cũ, tư liệu chính phủ Mỹ, NASA...). Không cần key."""
    res = http_json("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "generator": "search", "gsrsearch": f"{q} filetype:video", "gsrnamespace": 6,
        "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mediatype", "format": "json"})
    out = []
    for p in (res.get("query", {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii or ii.get("mediatype") not in ("VIDEO", None) or (ii.get("width") or 0) < 320:
            continue
        if (ii.get("width") or 0) < (ii.get("height") or 0) * 1.25:  # bỏ video quay dọc / vuông
            continue
        meta = ii.get("extmetadata", {})
        lic = _strip(meta.get("LicenseShortName", {}).get("value", ""))
        if NONFREE.search(lic):
            continue
        dur = float(ii.get("duration") or 0)
        if dur and dur < 3:
            continue
        title = p.get("title", "").replace("File:", "")
        desc = _strip(meta.get("ImageDescription", {}).get("value", ""))[:200]
        h = 720 if (ii.get("height") or 0) >= 720 else 480
        alts = [_commons_transcode(ii["url"], x) for x in (480, 360) if x < h]
        out.append({"kind": "video", "src": "Wikimedia Commons", "url": _commons_transcode(ii["url"], h),
                    "alt_urls": alts,
                    "fallback_url": ii["url"].split("?")[0], "page": ii.get("descriptionurl", ""),
                    "duration": dur, "license": lic, "title": f"{title} {desc}",
                    "credit": f"{title} ({lic}) via Wikimedia Commons"})
    return out


def loc_video(q: str, n: int = 6) -> list[dict]:
    """(Thử nghiệm) Phim Library of Congress - phần lớn chỉ phát streaming, ít khi có MP4 tải trực tiếp."""
    res = http_json("https://www.loc.gov/film-and-videos/", params={"q": q, "fo": "json", "c": n})
    out = []
    for it in res.get("results", []):
        rights = it.get("rights") or ""
        rights = " ".join(rights) if isinstance(rights, list) else str(rights)
        if rights and not re.search(r"no known restrictions|public domain", rights, re.I):
            continue
        mp4 = None

        def walk(o):  # cấu trúc "resources" của loc.gov khác nhau giữa các mục -> duyệt mềm dẻo
            nonlocal mp4
            if isinstance(o, dict):
                u = o.get("url") or o.get("video") or ""
                if isinstance(u, str) and u.lower().endswith(".mp4"):
                    mp4 = u
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(it.get("resources") or [])
        if not mp4:
            continue
        out.append({"kind": "video", "src": "Library of Congress", "url": mp4, "page": it.get("url", ""),
                    "duration": 0, "license": "Public domain", "title": it.get("title", ""),
                    "credit": f"{it.get('title', '')[:90]} - Library of Congress"})
    return out

def pexels_video(q: str, n: int = 8) -> list[dict]:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    res = http_json("https://api.pexels.com/videos/search", params={"query": q, "per_page": n,
                                                                    "orientation": "landscape"},
                    headers={"Authorization": key})
    out = []
    for v in res.get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("width") and 1280 <= f["width"] <= 1920]
        files = files or v.get("video_files", [])
        if not files:
            continue
        f = max(files, key=lambda f: f.get("width") or 0)
        out.append({"kind": "video", "src": "Pexels", "url": f["link"], "page": v["url"], "duration": v.get("duration", 0),
                    "license": "Pexels License", "title": v["url"].rstrip("/").split("/")[-1].replace("-", " "),
                    "credit": f"Video by {v['user']['name']} on Pexels"})
    return out


def pixabay_video(q: str, n: int = 8) -> list[dict]:
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return []
    res = http_json("https://pixabay.com/api/videos/", params={"key": key, "q": q, "per_page": max(n, 3),
                                                               "safesearch": "true"})
    out = []
    for h in res.get("hits", []):
        v = h["videos"].get("large") or h["videos"].get("medium")
        if not v or not v.get("url"):
            continue
        out.append({"kind": "video", "src": "Pixabay", "url": v["url"], "page": h["pageURL"], "duration": h["duration"],
                    "license": "Pixabay License", "title": h.get("tags", ""), "credit": f"Video by {h['user']} on Pixabay"})
    return out


def archive_video(q: str, n: int = 5) -> list[dict]:
    """Phim tư liệu public domain trên Internet Archive (cắt đoạn trực tiếp qua ffmpeg, không tải cả phim)."""
    res = http_json("https://archive.org/advancedsearch.php", params={
        "q": f"({q}) AND mediatype:movies AND (collection:prelinger OR collection:newsandpublicaffairs OR "
             f"licenseurl:*publicdomain*)",
        "fl[]": ["identifier", "title"], "rows": n, "output": "json"}, timeout=40)
    out = []
    for d in res.get("response", {}).get("docs", []):
        ident = d["identifier"]
        try:
            meta = http_json(f"https://archive.org/metadata/{ident}", timeout=30)
        except Exception:  # noqa: BLE001
            continue
        mp4s = [f for f in meta.get("files", []) if f["name"].lower().endswith(".mp4")]
        if not mp4s:
            continue
        f = min(mp4s, key=lambda f: int(f.get("size", 1e12)))
        try:
            dur = float(f.get("length") or 0)
        except ValueError:
            dur = 0
        out.append({"kind": "video", "src": "Internet Archive", "url": f"https://archive.org/download/{ident}/{f['name']}",
                    "page": f"https://archive.org/details/{ident}", "duration": dur, "remote_cut": True,
                    "license": "Public domain", "title": d.get("title", ident),
                    "credit": f"\"{d.get('title', ident)}\" - Internet Archive (public domain)"})
    return out


IMAGE_SOURCES = {"wiki_article": wiki_article, "wikimedia": wikimedia, "loc": loc, "loc_news": loc_news,
                 "openverse": openverse, "europeana": europeana, "smithsonian": smithsonian, "flickr": flickr,
                 "archive_img": archive_img, "pexels": pexels, "pixabay": pixabay, "unsplash": unsplash}
VIDEO_SOURCES = {"wikimedia_video": wikimedia_video, "loc_video": loc_video, "pexels_video": pexels_video, "pixabay_video": pixabay_video, "archive_video": archive_video}


def search_images(q: str, sources: list[str], n: int = 15, min_w: int = 900) -> list[dict]:
    out = []
    for name in sources:
        fn = IMAGE_SOURCES.get(name)
        if not fn:
            continue
        try:
            got = fn(q, n, min_w)
            out += got
        except Exception as e:  # noqa: BLE001
            log(f"  ! {name}: {str(e).splitlines()[0][:120]}")
    return out


def search_videos(q: str, sources: list[str], n: int = 8) -> list[dict]:
    out = []
    for name in sources:
        fn = VIDEO_SOURCES.get(name)
        if not fn:
            continue
        try:
            out += fn(q, n)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {name}: {str(e).splitlines()[0][:120]}")
    return out

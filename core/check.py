"""Kiểm tra trước khi xuất: python studio.py check <slug>  ->  output/check_report.md

Kiểm tra: chính tả (cần Claude), phát âm (số/chữ viết tắt/ký hiệu), phụ đề, nhất quán nhân vật, phép tính,
nguồn & số chưa xác minh, khớp hình–lời, âm lượng, thời lượng. Mục nào không tự kiểm tra được thì ghi rõ.
"""
from __future__ import annotations

import ast
import operator
import os
import re
import subprocess
from pathlib import Path

from .util import Project, log

OK, WARN, FAIL, NA = "✅", "⚠️", "❌", "⬜ chưa kiểm tra được"

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_eval(expr: str) -> float:
    """Tính biểu thức số học an toàn (chỉ + - * / ** và số)."""
    expr = expr.replace(",", "").replace("%", "/100").replace("×", "*").replace("x", "*").replace("^", "**")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("biểu thức không hợp lệ")

    return float(ev(ast.parse(expr, mode="eval")))


def _scenes(script):
    return [s for c in script["chapters"] for s in c["scenes"]]


def check_math(script) -> list[str]:
    out = []
    for s in _scenes(script):
        for f in s.get("figures") or []:
            fm = (f.get("formula") or "").strip()
            if not fm:
                continue
            try:
                v = safe_eval(fm)
            except Exception:  # noqa: BLE001
                out.append(f"{WARN} {s['id']} «{f['label']}»: không tính được công thức `{fm}`")
                continue
            val = float(f.get("value") or 0)
            if abs(v - val) > max(0.5, abs(val) * 0.005):
                out.append(f"{FAIL} {s['id']} «{f['label']}»: ghi {val:g} nhưng `{fm}` = {v:g}")
            else:
                out.append(f"{OK} {s['id']} «{f['label']}»: `{fm}` = {v:g}")
    return out


def check_sources(script, cfg) -> list[str]:
    out = []
    unver = [(s["id"], f["label"]) for s in _scenes(script) for f in s.get("figures") or [] if not f.get("verified")]
    nosrc = [(s["id"], f["label"]) for s in _scenes(script) for f in s.get("figures") or []
             if f.get("verified") and not f.get("source")]
    for sid, lab in unver:
        out.append(f"{WARN} {sid} «{lab}»: số GIẢ ĐỊNH / chưa xác minh -> cần bổ sung nguồn hoặc ghi rõ là giả định")
    for sid, lab in nosrc:
        out.append(f"{FAIL} {sid} «{lab}»: đánh dấu đã xác minh nhưng không có nguồn")
    if not script.get("sources_used"):
        out.append(f"{WARN} Kịch bản chưa có danh sách nguồn (sources_used)")
    factual = [s["id"] for s in _scenes(script) if s.get("visual_type") in ("evidence", "species", "chart", "diagram")
               and not s.get("sources")]
    if factual:
        out.append(f"{WARN} Cảnh nêu dữ kiện nhưng chưa ghi nguồn: {', '.join(factual[:15])}")
    st = (cfg.get("project") or {}).get("story_type")
    if st == "fiction":
        first = _scenes(script)[0]["narration"].lower() if _scenes(script) else ""
        out.append((OK if "hư cấu" in first else WARN) + " Truyện hư cấu: câu báo 'hư cấu' ở cảnh đầu"
                   + ("" if "hư cấu" in first else " CHƯA có (thẻ cảnh báo vẫn được chèn tự động)"))
    return out or [f"{OK} Không có số liệu cần nguồn"]


def check_pronunciation(script) -> list[str]:
    out = []
    for s in _scenes(script):
        t = s["narration"]
        issues = []
        if re.search(r"\d", t):
            issues.append("có chữ số (" + ", ".join(sorted(set(re.findall(r"[\d.,/%]+", t)))[:5]) + ")")
        abbr = sorted(set(re.findall(r"\b[A-ZĐ]{2,}\b", t)))
        if abbr:
            issues.append("viết tắt " + ", ".join(abbr[:5]))
        if re.search(r"[%$€£/&#@]", t):
            issues.append("ký hiệu")
        if issues:
            out.append(f"{WARN} {s['id']}: {'; '.join(issues)} -> nghe lại, nên viết thành chữ")
    return out or [f"{OK} Không thấy số / viết tắt / ký hiệu dễ đọc sai"]


def check_subtitles(project: Project) -> list[str]:
    p = project.path("output", "subtitles.srt")
    if not p.exists():
        return [f"{FAIL} Chưa có subtitles.srt (chạy timeline/render)"]
    blocks = [b for b in p.read_text("utf-8").split("\n\n") if b.strip()]
    long_lines, overlaps, prev_end = 0, 0, 0.0

    def sec(ts):
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    for b in blocks:
        lines = b.strip().split("\n")
        if len(lines) < 3:
            continue
        a, z = [sec(x.strip()) for x in lines[1].split("-->")]
        if a < prev_end - 0.01:
            overlaps += 1
        prev_end = z
        if any(len(ln) > 48 for ln in lines[2:]):
            long_lines += 1
    out = [f"{OK} {len(blocks)} dòng phụ đề"]
    out.append((FAIL if overlaps else OK) + f" Chồng lấn thời gian: {overlaps}")
    out.append((WARN if long_lines else OK) + f" Dòng dài > 48 ký tự: {long_lines}")
    return out


def check_consistency(script, plan) -> list[str]:
    ch = [s["id"] for s in _scenes(script) if s.get("visual_type") == "character"]
    ai_people = [s["id"] for s in _scenes(script) if s.get("visual_type") not in ("character", "diagram", "chart")
                 and any((m.get("credit") or "").startswith("AI-generated") for m in plan.get(s["id"], []))]
    out = []
    if ch:
        out.append(f"{OK} {len(ch)} cảnh dùng nhân vật vẽ bằng code (brand kit) -> nhất quán 100%")
    if ai_people:
        out.append(f"{NA} Ảnh AI ở {len(ai_people)} cảnh ({', '.join(ai_people[:10])}): cần xem bằng mắt nhân vật/chi tiết")
    return out or [f"{OK} Không dùng nhân vật"]


def check_sync(script, plan) -> list[str]:
    from .library import keyword_score

    out = []
    for s in _scenes(script):
        if s.get("visual_type") in ("character", "diagram", "chart", "quote", "board"):
            continue
        items = plan.get(s["id"], [])
        if not items:
            out.append(f"{FAIL} {s['id']}: không có hình")
            continue
        q = " ".join(s.get("search_queries_en") or [])
        real = [m for m in items if not (m.get("credit") or "").startswith("AI-generated") and m.get("title")]
        if q and real and max(keyword_score(q, m["title"]) for m in real) < 0.2:
            out.append(f"{WARN} {s['id']}: ảnh có thể lạc đề với lời đọc ({real[0]['title'][:50]})")
    return out or [f"{OK} Mọi cảnh đều có hình phù hợp từ khoá"]


def check_audio(project: Project) -> list[str]:
    f = project.path("output", "final.mp4")
    if not f.exists():
        return [f"{NA} Chưa có final.mp4"]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(f), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore").stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)
    out = []
    if i:
        lufs = float(i[-1])
        ok = -17.5 <= lufs <= -12.5
        out.append((OK if ok else WARN) + f" Độ lớn tổng: {lufs:.1f} LUFS (YouTube ~ -14)")
    if tp:
        peak = float(tp[-1])
        out.append((OK if peak <= -0.5 else WARN) + f" Đỉnh: {peak:.1f} dBFS" + ("" if peak <= -0.5 else " (có thể vỡ tiếng)"))
    return out or [f"{NA} Không đo được âm lượng"]


def check_spelling(script, cfg) -> list[str]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return [f"{NA} Chính tả/ngữ pháp: cần ANTHROPIC_API_KEY để Claude rà soát"]
    from .scriptgen import ClaudeWriter

    schema = {"type": "object", "properties": {"issues": {"type": "array", "items": {
        "type": "object", "properties": {"scene_id": {"type": "string"}, "text": {"type": "string"},
                                         "suggestion": {"type": "string"}},
        "required": ["scene_id", "text", "suggestion"], "additionalProperties": False}}},
        "required": ["issues"], "additionalProperties": False}
    body = "\n".join(f"[{s['id']}] {s['narration']}" for s in _scenes(script))
    res = ClaudeWriter(cfg).ask_json("Bạn là biên tập viên. Chỉ ra lỗi chính tả, ngữ pháp, câu khó đọc thành tiếng.",
                                     f"Rà soát lời dẫn sau, chỉ liệt kê lỗi thật sự:\n{body}", schema)
    return [f"{WARN} {x['scene_id']}: «{x['text']}» -> {x['suggestion']}" for x in res["issues"]] or [f"{OK} Không thấy lỗi"]


def run_check(project: Project, cfg: dict) -> Path:
    script = project.read_json("script.json")
    plan = project.read_json("media_plan.json", {})
    tl = project.read_json("timeline.json", {}) or {}
    target = cfg["channel"].get("target_minutes", 10)
    dur = tl.get("duration", 0) / 60
    sections = {
        "Thời lượng": [(OK if abs(dur - target) <= max(1.5, target * 0.2) else WARN)
                       + f" {dur:.1f} phút (mục tiêu {target} phút)"],
        "Chính tả": check_spelling(script, cfg),
        "Phát âm (đọc thử các cảnh này)": check_pronunciation(script),
        "Phụ đề": check_subtitles(project),
        "Nhất quán nhân vật": check_consistency(script, plan),
        "Phép tính": check_math(script) or [f"{OK} Không có công thức cần kiểm"],
        "Nguồn & số liệu chưa xác minh": check_sources(script, cfg),
        "Khớp hình – lời": check_sync(script, plan),
        "Âm lượng": check_audio(project),
        "Chi tiết hình ảnh AI (tay, chữ, logo lạ...)": [f"{NA} cần xem bằng mắt trước khi đăng"],
    }
    lines = [f"# Báo cáo kiểm tra – {script['title']}\n"]
    n_fail = n_warn = 0
    for k, v in sections.items():
        lines.append(f"\n## {k}\n")
        lines += [f"- {x}" for x in v]
        n_fail += sum(x.startswith(FAIL) for x in v)
        n_warn += sum(x.startswith(WARN) for x in v)
    lines.insert(1, f"**{n_fail} lỗi, {n_warn} cảnh báo.** {FAIL} phải sửa · {WARN} nên xem lại · {NA}\n")
    out = project.path("output", "check_report.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    log(f"✓ Kiểm tra: {n_fail} lỗi, {n_warn} cảnh báo -> {out}")
    return out


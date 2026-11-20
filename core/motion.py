"""Ngôn ngữ chuyển động của video kể chuyện bằng ảnh (cold case / true crime / history).

Chuyển động camera trên ảnh tĩnh (ffmpeg zoompan, có easing mượt):
  push_in     zoom chậm vào điểm nhấn (mặt người, chữ, vật chứng)      - nhấn mạnh, tạo căng thẳng
  pull_out    bắt đầu cận điểm nhấn rồi lùi ra toàn cảnh             - "hé lộ" bối cảnh
  pan_lr/rl   lia ngang trái->phải / phải->trái                       - ảnh phong cảnh, đường phố, nhóm người
  tilt_down/up lia dọc (đọc tài liệu, trang báo, ảnh chân dung dọc)
  punch       cận chi tiết, trôi rất nhẹ                              - "nhìn kỹ vào đây..."
  snap_zoom   zoom nhanh vào chi tiết rồi giữ                         - khoảnh khắc phát hiện / twist
  float       ảnh in đặt trên bàn, trôi chéo nhẹ                     - hồ sơ, ảnh kỷ vật
  shake       rung máy cầm tay rất nhẹ                                - không khí bất an
Chuyển cảnh: fade (hoà tan), flash (chớp trắng như đèn máy ảnh), black (tối dần), cut.
"""
from __future__ import annotations

import random

from .util import split_sentences

MOTIONS = ["push_in", "pull_out", "pan_lr", "pan_rl", "tilt_down", "tilt_up", "punch", "snap_zoom", "float", "shake",
           "slam", "torch", "hold"]


def zoompan_expr(motion: str, frames: int, fx: float, fy: float, zoom: float, W: int, H: int, fps: int,
                 punches: list[int] | None = None, shake: float = 0.0, amp: float = 0.075) -> str:
    """Biểu thức zoompan cho 1 shot. frames = tổng frame của stream (kể cả phần chồng chuyển cảnh).
    punches: các frame "nhấn" -> camera giật vào nhanh rồi nhả (+ rung nếu shake > 0)."""
    zp = _zoompan_core(motion, frames, fx, fy, zoom, W, H, fps)
    if not punches:
        return zp
    m = __import__("re").match(r"zoompan=z='(.*)':x='(.*)':y='(.*)':d=1:(.*)$", zp)
    z, x, y, rest = m.groups()
    pul = "+".join(f"if(gte(on,{f}),exp(-(on-{f})/7),0)" for f in punches)
    z2 = f"({z})*(1+{amp:.3f}*({pul}))"
    if shake > 0:
        sh = "+".join(f"if(gte(on,{f}),exp(-(on-{f})/9),0)" for f in punches)
        x = f"max(0,min(iw-iw/zoom,({x})+{shake * W:.1f}*sin(on*2.3)*({sh})))"
        y = f"max(0,min(ih-ih/zoom,({y})+{shake * H:.1f}*cos(on*1.7)*({sh})))"
    return f"zoompan=z='{z2}':x='{x}':y='{y}':d=1:{rest}"


def _zoompan_core(motion: str, frames: int, fx: float, fy: float, zoom: float, W: int, H: int, fps: int) -> str:
    N = max(frames - 1, 1)
    p = f"(on/{N})"
    e = f"((1-cos(PI*{p}))/2)"  # ease in-out
    Z = zoom

    def center(cx: str, cy: str, zexpr: str) -> tuple[str, str, str]:
        x = f"max(0,min(iw-iw/zoom,({cx})*iw-iw/zoom/2))"
        y = f"max(0,min(ih-ih/zoom,({cy})*ih-ih/zoom/2))"
        return zexpr, x, y

    if motion == "push_in":
        z, x, y = center(f"0.5+({fx}-0.5)*{e}", f"0.5+({fy}-0.5)*{e}", f"1+{Z}*{e}")
    elif motion == "pull_out":
        z, x, y = center(f"{fx}+(0.5-{fx})*{e}", f"{fy}+(0.5-{fy})*{e}", f"1+{Z}*(1-{e})")
    elif motion in ("pan_lr", "pan_rl"):
        zz = 1 + Z * 1.1
        prog = e if motion == "pan_lr" else f"(1-{e})"
        z = f"{zz}"
        x = f"(iw-iw/zoom)*{prog}"
        y = f"max(0,min(ih-ih/zoom,{fy}*ih-ih/zoom/2))"
    elif motion in ("tilt_down", "tilt_up"):
        zz = 1 + Z * 1.2
        prog = e if motion == "tilt_down" else f"(1-{e})"
        z = f"{zz}"
        x = f"max(0,min(iw-iw/zoom,{fx}*iw-iw/zoom/2))"
        y = f"(ih-ih/zoom)*{prog}"
    elif motion == "punch":
        z, x, y = center(f"{fx}", f"{fy}", f"1.04+{Z * 0.5}*{e}")
    elif motion == "snap_zoom":
        fast = f"(1-pow(1-min(1,{p}*4),3))"  # 25% đầu zoom nhanh, sau đó giữ
        z, x, y = center(f"0.5+({fx}-0.5)*{fast}", f"0.5+({fy}-0.5)*{fast}", f"1+{Z * 1.8}*{fast}+{Z * 0.2}*{p}")
    elif motion == "slam":  # báo/tài liệu "đập" vào màn hình: từ rất gần lùi nhanh về rồi trôi chậm
        fast = f"(1-pow(1-min(1,{p}*5),3))"
        z, x, y = center(f"{fx}", f"{fy}", f"1+{Z * 0.4}*{p}+0.9*(1-{fast})")
    elif motion == "torch":  # soi đèn pin: camera gần như đứng yên, vùng sáng di chuyển (thêm ở bước render)
        z, x, y = center(f"0.5+({fx}-0.5)*0.3*{e}", f"0.5+({fy}-0.5)*0.3*{e}", f"1.05+{Z * 0.3}*{e}")
    elif motion == "hold":  # giữ khung gần như yên để người xem quan sát
        z, x, y = center(f"0.5+({fx}-0.5)*0.1*{e}", f"0.5+({fy}-0.5)*0.1*{e}", f"1.02+0.015*{e}")
    elif motion == "float":
        z, x, y = center(f"0.47+0.06*{e}", f"0.53-0.06*{e}", f"1.06+{Z * 0.4}*{e}")
    elif motion == "shake":
        z = "1.1"
        x = f"(iw-iw/zoom)/2+sin(on*0.21)*{W * 0.004}+sin(on*0.53)*{W * 0.002}"
        y = f"(ih-ih/zoom)/2+cos(on*0.17)*{H * 0.004}+sin(on*0.61)*{H * 0.002}"
    else:
        z, x, y = center("0.5", "0.5", "1")
    return f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={fps}"


# ---------------- Lập kế hoạch shot cho 1 scene ----------------

def sentence_cuts(text: str, dur: float, n: int) -> list[float]:
    """Thời điểm cắt cảnh, ưu tiên rơi vào cuối câu (nghe tự nhiên hơn cắt giữa câu)."""
    if n <= 1:
        return []
    sents = split_sentences(text) or [text]
    total = sum(len(s) for s in sents) or 1
    bounds, acc = [], 0
    for s in sents[:-1]:
        acc += len(s)
        bounds.append(dur * acc / total)
    cuts = []
    for k in range(1, n):
        ideal = dur * k / n
        near = min(bounds, key=lambda b: abs(b - ideal)) if bounds else ideal
        t = near if abs(near - ideal) < dur / n * 0.4 else ideal
        lo = (cuts[-1] if cuts else 0) + 2.0
        cuts.append(min(max(t, lo), dur - 2.0 * (n - k)))
    return sorted(set(round(c, 3) for c in cuts if 1.5 < c < dur - 1.5))


def plan_scene(scene: dict, media: list[dict], start: float, dur: float, cfg: dict, state: dict) -> list[dict]:
    """Chia scene thành các shot: chọn ảnh, khung, chuyển động, chuyển cảnh."""
    ed = cfg.get("edit", {})
    shot_len = cfg["media"]["shot_seconds"]
    if state.pop("hook", False):  # 30 giây đầu: cắt nhanh hơn để giữ người xem
        shot_len *= ed.get("hook_pace", 0.6)
    shot_len *= state.pop("pace_once", 1.0)  # cảnh hành động: cắt nhanh hơn
    rnd = random.Random(scene["id"])
    n = max(1, round(dur / shot_len))
    cuts = sentence_cuts(scene["narration"], dur, n)
    bounds = [0.0] + cuts + [dur]
    n = len(bounds) - 1

    # gán media: mỗi media 1 shot, dư shot thì "punch-in" chi tiết trên ảnh lớn nhất
    seq: list[dict] = []
    imgs = [m for m in media if m["kind"] == "image"]
    big = sorted(imgs, key=lambda m: -(m.get("w") or 0))
    for k in range(n):
        if k < len(media):
            seq.append(dict(media[k]))
        elif not media:  # cảnh vẽ bằng code (biểu đồ/sơ đồ) không cần ảnh
            break
        else:
            base = (big or media)[(k - len(media)) % len(big or media)]
            d = dict(base)
            large = max(d.get("w") or 0, d.get("h") or 0) >= 1500
            if d["kind"] == "image" and ed.get("detail_shots", True) and large:
                d["detail"] = True
            elif d["kind"] == "image" and len(state.get("board_imgs", [])) >= 3 and (k % 2):
                d = {"kind": "image", "file": d["file"], "board": list(dict.fromkeys(
                    [d["file"]] + state["board_imgs"][-5:]))[:6]}
            elif d["kind"] == "image":
                d["force_frame"] = "pinned"
            seq.append(d)
    # đặt shot chi tiết ngay sau shot gốc của nó (rộng -> cận)
    ordered = []
    for m in seq:
        if not m.get("detail"):
            ordered.append(m)
    for m in seq:
        if m.get("detail"):
            idx = max((i for i, o in enumerate(ordered) if o["file"] == m["file"]), default=len(ordered) - 1)
            ordered.insert(idx + 1, m)
    seq = ordered[:n]

    shots = []
    vt = scene.get("visual_type", "")
    dark = cfg["render"].get("look") == "dark"
    ent = scene.get("entity")
    if vt == "board" and media:
        imgs_b = [m["file"] for m in media if m["kind"] == "image"] + state.get("board_imgs", [])
        imgs_b = list(dict.fromkeys(imgs_b))[:7]
        seq = [{"kind": "image", "file": imgs_b[0], "board": imgs_b}] + seq[: max(0, n - 1)]
    cam = scene.get("camera") if scene.get("camera") not in (None, "", "auto") else None
    if vt in ("character", "diagram", "chart", "insert"):
        from .mascot import INTENSE

        ch = dict(scene.get("character") or {})
        if ch.get("outside") and ch.get("inside"):
            ch["contrast"] = {"outside": ch["outside"], "inside": ch["inside"]}
        mood = scene.get("mood") or ""
        if mood and mood != "auto":
            ch["mood"] = mood
        bg = media[0]["file"] if media else "none"
        ins = scene.get("insert") or {}
        has_ins = (ins.get("type") or "none") not in ("", "none")
        bnds = list(bounds)
        if has_ins and len(bnds) == 2 and dur > 4:  # 1 shot -> tách: nhân vật rồi màn hình chèn
            bnds = [0.0, round(dur * 0.45, 3), dur]
        n_s = len(bnds) - 1
        ins_k = -1
        if has_ins:
            ins_k = 0 if vt == "insert" or n_s == 1 else 1
        shots = []
        seq_m = ([cam] if cam else []) + (["push_in", "pull_out", "pan_lr", "hold"] if vt == "character"
                                          else ["hold", "push_in"])
        framing = ch.get("framing") or "auto"
        prev_char = state.get("prev_vt") == "character"
        for k in range(n_s):
            s0, s1 = bnds[k], bnds[k + 1]
            sh = {"kind": "image", "file": bg, "start": start + s0, "duration": s1 - s0, "zoom": ed.get("zoom", 0.1),
                  "transition": "cut", "motion": seq_m[k % len(seq_m)]}
            if k == ins_k:
                sh.update(frame="insert", insert=ins, mood=mood or "night", motion="hold", focus=(0.5, 0.45))
            elif vt in ("character", "insert"):
                c2 = dict(ch)
                if framing == "auto":  # shot đầu toàn thân; cảm xúc mạnh -> shot sau cận mặt
                    c2["framing"] = "closeup" if (k % 2 == 1 and c2.get("expression") in INTENSE) else "wide"
                if k > 0:  # bong bóng & chữ nội tâm chỉ ở shot đầu
                    c2["thought"] = ""
                    c2["shadow_text_done"] = True
                    if c2.get("framing") != "closeup":
                        c2["position"] = {"left": "right", "right": "left"}.get(ch.get("position", "left"), "left") \
                            if k % 2 else ch.get("position", "left")
                if c2.pop("shadow_text_done", False) and c2.get("shadow"):
                    c2["shadow"] = " "  # bóng đen vẫn đứng đó nhưng không lặp lại câu nói
                sh.update(frame="character", char=c2, seed=k, enter=(k == 0 and not prev_char))
                if c2.get("framing") == "closeup":
                    sh["motion"] = "push_in" if not cam else cam
            else:
                sh.update(frame="diagram", diagram=scene.get("diagram") or {}, figures=scene.get("figures") or [],
                          title=scene.get("on_screen_text") or "", visual=vt)
            shots.append(sh)
        state["prev_motion"] = shots[-1]["motion"]
        state["prev_vt"] = "character" if vt in ("character", "insert") else vt
        return shots
    if vt == "quote" and scene.get("on_screen_text") and state.get("quote_bg"):
        state["prev_vt"] = vt
        return [{"kind": "image", "file": state["quote_bg"], "start": start, "duration": dur, "frame": "full",
                 "motion": "push_in", "zoom": 0.04, "transition": "cut",
                 "quote": [scene["on_screen_text"], (ent or {}).get("name", "")]}]
    if ent:
        seq = [{"kind": "image", "file": ent.get("file") or "", "entity": ent}] + seq[: max(1, n - 1)]
        if len(bounds) - 1 < len(seq) and dur > 6:  # thêm 1 nhát cắt cho thẻ nhân vật
            bounds = [0.0, min(4.5, dur * 0.45)] + [b for b in bounds[1:] if b > min(4.5, dur * 0.45) + 1.5]
    n = min(len(seq), len(bounds) - 1)
    seq = seq[:n]
    for k, m in enumerate(seq):
        s0, s1 = bounds[k], bounds[k + 1]
        shot = {"kind": m["kind"], "file": m["file"], "start": start + s0, "duration": s1 - s0,
                "focus": m.get("focus"), "zoom": ed.get("zoom", 0.14)}
        if m.get("entity"):
            e = m["entity"]
            shot.update(frame="pinned", motion="push_in", zoom=0.2, transition="cut",
                        namecard=[e.get("name", ""), e.get("role", "")])
            if cfg["render"].get("look") == "collage":  # chân dung cắt dán (tách nền nếu có rembg)
                shot.update(frame="collage", seed=k, zoom=0.1)
            if e.get("file"):
                state.setdefault("board_imgs", []).append(e["file"])
            state["prev_motion"] = "push_in"
            shots.append(shot)
            continue
        if m.get("board") and cfg["render"].get("look") == "collage":  # bảng điều tra -> cắt dán nhiều ảnh
            shot.update(frame="collage", files=m["board"][:3], seed=k + len(shots), zoom=0.1,
                        motion=rnd.choice(["pan_lr", "pan_rl", "push_in"]), transition="cut")
            state["prev_motion"] = shot["motion"]
            shots.append(shot)
            continue
        if m.get("board"):
            shot.update(frame="board", files=m["board"], seed=k + len(shots), zoom=0.22,
                        motion=rnd.choice(["pan_lr", "pan_rl", "push_in"]), transition="cut" if k == 0 else "flash")
            state["prev_motion"] = shot["motion"]
            shots.append(shot)
            continue
        if m["kind"] == "image":
            shot["frame"] = m.get("force_frame") or _pick_frame(m, vt, ed, rnd)
            if cfg["render"].get("look") == "collage":  # kiểu cắt dán tư liệu
                shot["frame"] = "collage"
                shot["seed"] = k
                if k == 0:
                    extra = [x["file"] for x in media if x["kind"] == "image" and x["file"] != m["file"]]
                    if len(extra) >= 2:
                        shot["files"] = [m["file"], extra[0]]
                shot["color"] = vt in ("species", "location", "atmosphere") and "AI-generated" in (m.get("credit") or "")
            small = (m.get("w") or 0) and max(m.get("w") or 0, m.get("h") or 0) < 1100
            if dark and shot["frame"] == "clipping":
                shot["frame"] = "poster"
            elif dark and (shot["frame"] in ("print", "polaroid") or (small and not m.get("detail"))):
                shot["frame"] = "pinned"
            if m.get("detail"):
                shot["crop"] = "detail"
                shot["seed"] = k
            shot["motion"] = _pick_motion(shot, m, vt, k, state, ed, rnd)
            if shot["frame"] == "pinned" and shot["motion"] in ("tilt_down", "tilt_up", "float"):
                shot["motion"] = rnd.choice(["push_in", "pull_out"])
            if m["kind"] == "image" and m["file"] not in state.setdefault("board_imgs", []):
                state["board_imgs"].append(m["file"])
            first_of_kind = m["file"] not in state.setdefault("seen_files", [])
            state["seen_files"].append(m["file"])
            if shot["frame"] in ("poster", "clipping") and first_of_kind and "slam" in ed.get("motions", MOTIONS):
                shot["motion"] = "slam"           # tờ báo đập vào màn hình
                shot["transition"] = "flash" if k else "cut"
            elif vt in ("document", "evidence") and dark and rnd.random() < ed.get("torch_rate", 0.4) \
                    and "torch" in ed.get("motions", MOTIONS) and not m.get("detail"):
                shot["motion"] = "torch"          # soi đèn pin trong bóng tối
            is_ai = (m.get("credit") or "").startswith("AI-generated")
            if vt == "evidence" and first_of_kind and not m.get("detail") and not is_ai \
                    and rnd.random() < ed.get("circle_rate", 0.5):
                shot["circle"] = True             # khoanh đỏ chi tiết
            if shot["frame"] == "clipping":  # đọc trang báo/tài liệu: vào gần hơn
                shot["zoom"] = max(shot["zoom"], ed.get("document_zoom", 0.45))
            if shot["frame"] == "collage":  # cắt dán: nền trôi nhẹ, các mảnh tự bật ra
                shot.pop("circle", None)
                shot.pop("crop", None)
                shot["motion"] = cam or rnd.choice(["push_in", "pan_lr", "pan_rl", "pull_out"])
                shot["zoom"] = 0.1
                if shot.get("transition") == "flash":
                    shot.pop("transition")
        else:
            shot["motion"] = "video"
        # chuyển cảnh vào shot này
        if k == 0:
            shot["transition"] = "cut"
        elif "transition" in shot:
            pass
        elif shot.get("frame") in ("clipping",) or vt == "evidence" and rnd.random() < ed.get("flash_rate", 0.35):
            shot["transition"] = "flash"
        else:
            shot["transition"] = ed.get("transition", "fade")
        if cam and k == 0 and shot.get("motion") != "video":
            shot["motion"] = cam  # camera do storyboard chỉ định
        state["prev_motion"] = shot["motion"]
        shots.append(shot)
    if cfg["render"].get("look") == "collage":  # mảnh đầu tiên của cảnh: dải giấy ngày/địa điểm + con số lớn
        col = [sh for sh in shots if sh.get("frame") == "collage"]
        if col:
            col[0]["label_text"] = scene.get("on_screen_text") or ""
            st = scene.get("stat") or {}
            if st.get("value") not in (None, "", 0):
                col[0]["stat"] = st
                col[0]["files"] = (col[0].get("files") or [col[0]["file"]])[:1]
    state["prev_vt"] = vt
    return shots


def _pick_frame(m: dict, vt: str, ed: dict, rnd: random.Random) -> str:
    from .stylize import image_size

    if m.get("detail"):
        return "full"
    t = (m.get("title") or "").lower()
    if m.get("visual") == "newspaper" or vt in ("newspaper", "document") or \
            any(k in t for k in ("poster", "wanted", "newspaper", "headline", "front page", "ticket")):
        return "clipping"
    w, h = m.get("w") or 0, m.get("h") or 0
    if not w:
        w, h = image_size(m["file"])
    tall = h > w * 1.1 if w else False
    if m.get("credit", "").startswith("AI-generated"):
        return "full"
    r = rnd.random()
    if (tall or vt == "person") and r < ed.get("print_rate", 0.35):
        return rnd.choice(["print", "polaroid"])
    if not tall and r < ed.get("print_rate", 0.35) * 0.3:
        return "print"
    return "auto"


def _pick_motion(shot: dict, m: dict, vt: str, k: int, state: dict, ed: dict, rnd: random.Random) -> str:
    allowed = ed.get("motions", MOTIONS)
    prev = state.get("prev_motion")
    if m.get("detail"):
        if prev == "punch":
            return rnd.choice([x for x in ("snap_zoom", "pan_lr", "pull_out") if x in allowed] or ["punch"])
        choice = "snap_zoom" if rnd.random() < ed.get("snap_rate", 0.2) and "snap_zoom" in allowed else "punch"
    elif shot.get("frame") == "clipping":
        choice = "tilt_down" if prev != "tilt_down" else "push_in"
    elif shot.get("frame") in ("print", "polaroid"):
        choice = "float"
    else:
        from .stylize import image_size

        w, h = image_size(m["file"])
        if h > w * 1.1:
            pool = ["tilt_down", "push_in", "tilt_up"]
        elif w > h * 1.9:
            pool = ["pan_lr", "pan_rl"]
        else:
            pool = ["push_in", "pull_out", "pan_lr", "pan_rl", "push_in"]
        if vt == "atmosphere" and rnd.random() < ed.get("shake_rate", 0.15):
            pool = ["shake"]
        if state.get("chapter_open"):
            pool = ["pull_out"]
            state["chapter_open"] = False
        pool = [p for p in pool if p != prev] or pool
        choice = rnd.choice(pool)
    return choice if choice in allowed else rnd.choice([a for a in allowed if a != "shake"] or ["push_in"])

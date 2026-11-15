"""Render video hoàn chỉnh bằng ffmpeg (không cần CapCut):
Ken Burns cho ảnh, cắt/ghép B-roll, màu phim cũ, nhiễu hạt, vignette, nhãn chữ, giọng đọc, nhạc nền tự hạ âm (ducking),
phụ đề (tuỳ chọn in cứng)."""
from __future__ import annotations

import hashlib
import json
import os
import random
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import graphics, motion, stylize
from .util import ROOT, Project, ffprobe_duration, log, need_ffmpeg, run

LOOKS = {
    "bright": "eq=saturation=1.06:contrast=1.03,unsharp=5:5:0.4",
    "deep_blue": "eq=contrast=1.08:saturation=1.1:gamma=0.95,colorbalance=rs=-0.08:gs=0.0:bs=0.1:rm=-0.06:bm=0.06,"
                 "vignette=angle=PI/4",
    "noir_red": "eq=contrast=1.12:brightness=-0.02:saturation=1.1,noise=alls=5:allf=t,vignette=angle=PI/3.6",
    "dark": "eq=saturation=0.32:contrast=1.2:brightness=-0.045:gamma=0.9,"
            "colorbalance=rs=-0.04:gs=-0.01:bs=0.05:rh=0.02:bh=-0.02,"
            "noise=alls=7:allf=t,vignette=angle=PI/3.4",
    "vintage": "eq=saturation=0.55:contrast=1.08:brightness=-0.02:gamma=0.97,"
               "colorchannelmixer=rr=0.95:rg=0.05:gr=0.02:gg=0.92:gb=0.04:br=0.03:bg=0.06:bb=0.82,"
               "noise=alls=9:allf=t,vignette=angle=PI/4.5",
    "noir": "hue=s=0,eq=contrast=1.18:brightness=-0.03,noise=alls=12:allf=t,vignette=angle=PI/4",
    "clean": "eq=saturation=0.85,vignette=angle=PI/6",
    "collage": "eq=contrast=1.04:saturation=0.95,noise=alls=4:allf=t,vignette=angle=PI/5",
}


_NVENC: bool | None = None


def has_nvenc() -> bool:
    """Có card NVIDIA + ffmpeg hỗ trợ h264_nvenc không (thử mã hoá 1 frame)."""
    global _NVENC
    if _NVENC is None:
        import subprocess

        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.1", "-frames:v", "1",
                            "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
        _NVENC = r.returncode == 0
    return _NVENC


def _enc(cfg: dict) -> list[str]:
    rc = cfg["render"]
    enc = rc.get("encoder", "auto")
    common = ["-pix_fmt", "yuv420p", "-r", str(rc["fps"]), "-video_track_timescale", "90000", "-an"]
    if enc == "nvenc" or (enc == "auto" and has_nvenc()):
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(rc.get("crf", 20) + 2), "-b:v", "0",
                *common]
    return ["-c:v", "libx264", "-preset", rc.get("preset", "medium"), "-crf", str(rc.get("crf", 20)), *common]


RENDER_VERSION = 12  # tăng số này khi đổi cách dựng để bỏ cache cũ
BRAND = {"name": None, "dark": False}  # brand kit đang dùng (đặt trong render_video)
STYLE = {"story_caps": False}  # phụ đề kiểu kể chuyện (trên cao) -> dời bong bóng/từ khoá xuống
TRANS_SEC = {"fade": 0.6, "flash": 0.3, "black": 0.8, "dissolve": 0.7, "cut": 0.0}
XFADE = {"fade": "fade", "flash": "fadewhite", "black": "fadeblack", "dissolve": "dissolve"}


def _plate(shot: dict, plates: Path, W: int, H: int, aged: bool) -> tuple[Path, tuple[float, float]]:
    """Ảnh -> plate đã đóng khung (cache). Trả về đường dẫn + điểm nhấn (cảnh nhân vật: ảnh gộp, dùng cho CapCut)."""
    path, focus, layers = _plate_full(shot, plates, W, H, aged)
    if layers is not None and shot.get("frame") == "character":
        meta = json.loads(path.with_name(path.name.replace("_bg.jpg", "_layers.json")).read_text("utf-8"))
        return Path(meta["flat"]), focus
    if layers:  # cắt dán / màn hình chèn: gộp các lớp ở trạng thái cuối thành 1 ảnh
        from PIL import Image

        from .emotion import _paste_clip

        flat = path.with_name(path.stem + "_flat.jpg")
        if not flat.exists():
            with Image.open(path) as im:
                base = im.convert("RGBA").resize((W, H), Image.LANCZOS)
            for ly in layers:
                f = ly["file"] % (ly.get("frames", 1) - 1) if "%" in ly["file"] else ly["file"]
                with Image.open(f) as li:
                    _paste_clip(base, li.convert("RGBA"), int(ly["x"]), int(ly["y"]))
            base.convert("RGB").resize((int(W * 1.5), int(H * 1.5)), Image.LANCZOS).save(flat, quality=90)
        return flat, focus
    return path, focus


def _layers_ok(mp: Path) -> bool:
    """File mô tả lớp còn và mọi ảnh lớp còn đủ (bị xoá bớt thì dựng lại)."""
    if not mp.exists():
        return False
    try:
        meta = json.loads(mp.read_text("utf-8"))
    except ValueError:
        return False
    files = [meta.get("bg", "")] + [ly["file"] for ly in meta.get("layers", []) if "%" not in ly["file"]]
    return all(Path(f).exists() for f in files)


def _plate_full(shot: dict, plates: Path, W: int, H: int, aged: bool):
    """-> (plate, điểm nhấn, các lớp động hoặc None)."""
    from PIL import Image

    key = json.dumps([RENDER_VERSION, shot["file"], shot.get("frame"), shot.get("crop"), shot.get("seed"), W, aged,
                      shot.get("files"), shot.get("circle"), shot.get("char"), shot.get("diagram"), shot.get("figures"),
                      shot.get("title"), BRAND["name"], shot.get("insert"), shot.get("mood"), STYLE["story_caps"],
                      shot.get("label_text"), shot.get("stat"), shot.get("color")],
                     sort_keys=True)
    out = plates / f"plate_{hashlib.md5(key.encode()).hexdigest()[:14]}.jpg"
    fr = shot.get("frame")
    if fr == "character" and not (shot.get("char") or {}).get("contrast"):
        from . import emotion, mascot

        base = out.with_suffix("")
        mp = base.with_name(base.name + "_layers.json")
        if not _layers_ok(mp):
            look = mascot.load_look(mascot.brand_kit(BRAND["name"]))
            bg = Path(shot["file"]) if shot.get("file") not in (None, "", "none") else None
            emotion.compose_layers(bg, base, W, H, shot.get("char") or {}, look, graphics.title_font,
                                   STYLE["story_caps"])
        meta = json.loads(mp.read_text("utf-8"))
        return Path(meta["bg"]), tuple(meta["focus"]), meta["layers"]
    if fr == "collage":
        from . import collage

        base = out.with_suffix("")
        mp = base.with_name(base.name + "_layers.json")
        if not _layers_ok(mp):
            collage.compose(shot.get("files") or [shot["file"]], base, W, H, seed=shot.get("seed", 0) +
                            zlib.crc32(shot["file"].encode()) % 1000, label=shot.get("label_text", ""),
                            stat=shot.get("stat"), color=bool(shot.get("color")))
        meta = json.loads(mp.read_text("utf-8"))
        return Path(meta["bg"]), tuple(meta["focus"]), meta["layers"]
    if fr == "insert":
        from . import emotion, mascot

        mp = out.with_suffix(".layers.json")
        if not (out.exists() and mp.exists()):
            look = mascot.load_look(mascot.brand_kit(BRAND["name"]))
            bg = Path(shot["file"]) if shot.get("file") not in (None, "", "none") else None
            _, lys = emotion.insert_plate(shot.get("insert") or {}, out, int(W * 1.5), int(H * 1.5), bg, look,
                                          shot.get("mood") or "night")
            meta = []
            for i, ly in enumerate(lys):
                f = out.with_name(f"{out.stem}_l{i}.png")
                ly["img"].save(f)
                meta.append({"kind": ly["kind"], "file": str(f), "x": ly["x"], "y": ly["y"],
                             "order": ly.get("order", 0)})
            mp.write_text(json.dumps(meta), encoding="utf-8")
        return out, (0.5, 0.45), json.loads(mp.read_text("utf-8"))
    meta = out.with_suffix(".json")
    if out.exists() and meta.exists():
        return out, tuple(json.loads(meta.read_text())), None
    if fr in ("character", "diagram"):
        from . import mascot

        W2, H2 = int(W * 1.5), int(H * 1.5)
        look = mascot.load_look(mascot.brand_kit(BRAND["name"]))
        if fr == "character":
            bg = Path(shot["file"]) if shot.get("file") not in (None, "", "none") else None
            _, focus = mascot.compose_scene(bg, out, W2, H2, shot.get("char") or {}, look, graphics.title_font,
                                            shot.get("seed", 0))
        else:
            dg = shot.get("diagram") or {}
            typ = dg.get("type") or ("cost_breakdown" if shot.get("figures") else "none")
            title = shot.get("title") or dg.get("subject", "")
            if typ == "size_compare":
                graphics.size_compare(dg.get("subject", ""), dg.get("size_m") or 1, out, W2, H2, look=look)
            elif typ == "depth_chart":
                graphics.depth_chart(dg.get("subject", ""), dg.get("depth_m") or 0, out, W2, H2)
            elif typ == "rent_vs_buy":
                graphics.rent_vs_buy(shot.get("figures") or [], out, title, W2, H2)
            else:
                graphics.figures_chart(shot.get("figures") or [], out, title, W2, H2,
                                       dark=BRAND.get("dark", False), kind=typ)
            focus = (0.5, 0.5)
        meta.write_text(json.dumps(list(focus)))
        return out, tuple(focus), None
    if fr in ("pinned", "poster", "board"):
        W2, H2 = int(W * 1.5), int(H * 1.5)
        seed = zlib.crc32(shot["file"].encode()) % 1000
        if fr == "board":
            _, pins = graphics.evidence_board(shot.get("files") or [shot["file"]], out, W2, H2, seed=shot.get("seed", 0))
            focus = pins[shot.get("seed", 0) % len(pins)] if pins else (0.5, 0.5)
        else:
            graphics.pinned_photo(Path(shot["file"]), out, W2, H2, seed=seed, poster=fr == "poster")
            focus = (0.5, 0.42)
        if shot.get("circle"):
            stylize.red_circle(out, focus, seed, radius=0.1)
        meta.write_text(json.dumps(list(focus)))
        return out, tuple(focus), None
    crop = None
    if shot.get("crop") == "detail":
        with Image.open(shot["file"]) as im:
            im = im.convert("RGB")
            f = stylize.focal_point(im)
            crop = stylize.detail_box(im, tuple(shot.get("focus") or f), 0.5, shot.get("seed", 0))
    path, focus, _ = stylize.make_plate(Path(shot["file"]), out, W, H, shot.get("frame", "auto"), crop,
                                        seed=zlib.crc32(shot["file"].encode()) % 1000, aged=aged)
    if shot.get("focus") and shot.get("frame") in ("full", "auto") and not crop:
        focus = tuple(shot["focus"])
    if shot.get("circle"):
        stylize.red_circle(out, focus, zlib.crc32(shot["file"].encode()) % 1000)
    meta.write_text(json.dumps(list(focus)))
    return path, focus, None


def typewriter_frames(text: str, folder: Path, fps: int, W: int, H: int, cps: float = 16) -> tuple[str, int]:
    """Chuỗi PNG chữ hiện dần từng ký tự (kiểu máy đánh chữ)."""
    folder.mkdir(parents=True, exist_ok=True)
    n_chars = len(text)
    frames = max(1, int(n_chars / cps * fps)) + int(fps * 0.3)
    if not (folder / f"f_{frames - 1:04d}.png").exists():
        for i in range(frames):
            k = min(n_chars, int(i * cps / fps) + 1)
            cursor = "_" if (i // max(1, fps // 4)) % 2 == 0 and k < n_chars else ""
            graphics.label_png(text[:k] + cursor, folder / f"f_{i:04d}.png", W, H, box_text=text)
    return str(folder / "f_%04d.png"), frames


def _layer_chain(ly: dict, idx: int, tag: str, dur: float, sh: dict, H: int) -> tuple[str, str]:
    """Bộ lọc cho 1 lớp động: (chuỗi tiền xử lý, tham số overlay)."""
    X, Y, kind = ly["x"], ly["y"], ly["kind"]
    pre = f"[{idx}:v]format=rgba"
    x, y, extra = str(X), str(Y), ""
    if kind in ("char", "blink"):
        amp = 3.5 if (sh.get("char") or {}).get("framing") != "closeup" else 6
        ent = f"+if(lt(t,0.45),pow(1-t/0.45,3)*{int(H * 0.55)},0)" if sh.get("enter") else ""
        y = f"'{Y}+{amp}*sin(2*PI*t/3.4){ent}'"
        if kind == "blink":
            ofs = (zlib.crc32(ly["file"].encode()) % 100) / 30
            extra = f":enable='lt(mod(t+{ofs:.2f},3.8),0.13)'"
    elif kind == "shadow":
        pre += ",fade=t=in:st=0.1:d=0.7:alpha=1"
        x, y = f"'{X}+9*sin(2*PI*t/4.3)'", f"'{Y}+6*sin(2*PI*t/3.1)'"
    elif kind == "bubble":
        pre += ",fade=t=in:st=0.35:d=0.25:alpha=1"
        y = f"'{Y}+120*max(0,0.6-t)'"
    elif kind == "voice":
        st = min(1.2, dur * 0.2)
        pre += f",fade=t=in:st={st:.2f}:d=0.6:alpha=1"
    elif kind == "notif":
        pre += ",fade=t=in:st=0.6:d=0.2:alpha=1"
        y = f"'{Y}-300*max(0,0.8-t)'"
    elif kind in ("pop", "fade", "slide", "count"):  # mảnh cắt dán
        t0 = float(ly.get("t0", 0))
        en = f":enable='gte(t,{t0:.2f})'"
        if kind == "pop":
            S = (f"if(lt(t,{t0}),0.05,if(lt(t,{t0 + 0.16}),0.05+1.1*(t-{t0})/0.16,"
                 f"if(lt(t,{t0 + 0.28}),1.15-0.15*(t-{t0 + 0.16})/0.12,1)))")
            pre += f",scale=w='max(4,iw*{S})':h='max(4,ih*{S})':eval=frame"
            cx, cy = X + ly["w"] / 2, Y + ly["h"] / 2
            x, y = f"'{cx:.0f}-overlay_w/2'", f"'{cy:.0f}-overlay_h/2'"
        elif kind == "fade":
            pre += f",fade=t=in:st={t0:.2f}:d=0.35:alpha=1"
        elif kind == "slide":
            x = f"'{X}-{int(H * 0.8)}*pow(max(0,1-(t-{t0})/0.35),3)'"
        elif kind == "count":
            pre += f",tpad=stop_mode=clone:stop_duration={dur + 1:.2f},setpts=PTS+{t0:.2f}/TB"
            S = f"if(lt(t,{t0 + 0.14}),0.3+0.85*(t-{t0})/0.14,if(lt(t,{t0 + 0.26}),1.15-0.15*(t-{t0 + 0.14})/0.12,1))"
            pre += f",scale=w='max(4,iw*{S})':h='max(4,ih*{S})':eval=frame"
            cx, cy = X + ly["w"] / 2, Y + ly["h"] / 2
            x, y = f"'{cx:.0f}-overlay_w/2'", f"'{cy:.0f}-overlay_h/2'"
        return pre + f"[{tag}]", f"x={x}:y={y}{en}:eof_action=pass"
    elif kind == "msg":
        st = 0.4 + 0.9 * ly.get("order", 0)
        pre += f",fade=t=in:st={st:.2f}:d=0.2:alpha=1"
        y = f"'{Y}+250*max(0,{st + 0.2:.2f}-t)'"
    return pre + f"[{tag}]", f"x={x}:y={y}{extra}:eof_action=pass"


def render_item(item: dict, out: Path, cfg: dict, plates: Path, labels: Path) -> Path:
    rc, ed = cfg["render"], cfg.get("edit", {})
    W, H, fps = rc["width"], rc["height"], rc["fps"]
    look_name = rc.get("look", "vintage")
    look = LOOKS.get(look_name, "")
    aged = look_name == "vintage" and ed.get("age_photos", True)
    shots = item["shots"]
    F = [round((sh["start"] + sh["duration"]) * fps) - round(sh["start"] * fps) for sh in shots]
    T = [0]
    for k in range(1, len(shots)):
        t = int(TRANS_SEC.get(shots[k].get("transition", "fade"), 0.6) * fps)
        T.append(min(t, F[k - 1] // 2, F[k] // 2))
    inputs: list[str] = []
    chains: list[str] = []
    nin = [0]

    def inp(*args) -> int:
        inputs.extend(str(a) for a in args)
        nin[0] += 1
        return nin[0] - 1

    for k, sh in enumerate(shots):
        L = F[k] + (T[k + 1] if k + 1 < len(shots) else 0)
        if sh["kind"] == "image":
            plate, (fx, fy), layers = _plate_full(sh, plates, W, H, aged)
            ii = inp("-loop", "1", "-framerate", fps, "-t", f"{L / fps + 0.5:.3f}", "-i", plate)
            zoom = sh.get("zoom", 0.14) * (0.5 if layers is not None else 1)  # cảnh lớp: nền trôi chậm (parallax)
            zp = motion.zoompan_expr(sh.get("motion", "push_in"), L, fx, fy, zoom, W, H, fps,
                                     sh.get("punches"), sh.get("shake", 0.0))
            torch = ""
            if sh.get("motion") == "torch":  # vùng sáng đèn pin lượn trên ảnh, xung quanh tối
                torch = (f",vignette=angle=PI/2.1:eval=frame:x0='w*({fx}+0.18*sin(2*PI*n/{max(L, 1)}*0.9))'"
                         f":y0='h*({fy}+0.12*cos(2*PI*n/{max(L, 1)}*0.7))'")
            chains.append(f"[{ii}:v]{zp}{torch},format=yuv420p[z{k}]")
            cur = f"z{k}"
            for j, ly in enumerate(layers or []):
                if ly["kind"] == "count":
                    li = inp("-framerate", fps, "-i", ly["file"])
                else:
                    li = inp("-loop", "1", "-framerate", fps, "-t", f"{L / fps + 0.5:.3f}", "-i", ly["file"])
                pre, ov = _layer_chain(ly, li, f"ly{k}_{j}", L / fps, sh, H)
                chains.append(pre)
                chains.append(f"[{cur}][ly{k}_{j}]overlay={ov}[o{k}_{j}]")
                cur = f"o{k}_{j}"
            chains.append(f"[{cur}]trim=end_frame={L},settb=1/{fps},setpts=N,format=yuv420p,setsar=1[s{k}]")
        else:
            src_dur = ffprobe_duration(sh["file"])
            need = L / fps
            if src_dur > need + 1:
                ss = random.Random(sh["file"] + str(sh["start"])).uniform(0, src_dur - need - 0.5)
                ii = inp("-ss", f"{ss:.2f}", "-i", sh["file"])
            else:
                ii = inp("-stream_loop", "-1", "-i", sh["file"])
            from .util import video_size

            vw, vh = video_size(sh["file"])
            if vw and vh and abs(vw / vh - W / H) > 0.25:  # lệch tỉ lệ: đặt giữa trên nền mờ của chính nó
                chains.append(f"[{ii}:v]fps={fps},split=2[bg{k}][fg{k}];"
                              f"[bg{k}]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
                              f"boxblur=10:2,scale={W}:{H},eq=brightness=-0.12[bgb{k}];"
                              f"[fg{k}]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs{k}];"
                              f"[bgb{k}][fgs{k}]overlay=(W-w)/2:(H-h)/2,"
                              f"trim=end_frame={L},settb=1/{fps},setpts=N,format=yuv420p,setsar=1[s{k}]")
            else:
                chains.append(f"[{ii}:v]fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                              f"trim=end_frame={L},settb=1/{fps},setpts=N,format=yuv420p,setsar=1[s{k}]")
    cur = "s0"
    acc = F[0]
    for k in range(1, len(shots)):
        tr = shots[k].get("transition", "fade")
        if T[k] <= 0 or tr == "cut":
            chains.append(f"[{cur}][s{k}]concat=n=2:v=1:a=0,settb=1/{fps}[x{k}]")
        else:
            chains.append(f"[{cur}][s{k}]xfade=transition={XFADE.get(tr, 'fade')}:duration={T[k] / fps:.3f}:"
                          f"offset={acc / fps:.3f}[x{k}]")
        cur = f"x{k}"
        acc += F[k]
    total = sum(F)
    span = total / fps
    post = [look] if look else []
    if item.get("type") == "scene":  # nhấn nhá theo cảnh (rùng mình / hành động / chấn động...)
        from . import fx as fxmod

        post += fxmod.post_filters(item.get("fx") or "none", item.get("accents") or [], total / fps)
    if look_name in ("vintage", "noir") and ed.get("flicker", True):
        post.append("eq=brightness='0.012*sin(2*PI*t*7.3)+0.008*sin(2*PI*t*13.1)':eval=frame")
    if item["type"] in ("title", "chapter"):
        post += ["fade=t=in:st=0:d=0.6", f"fade=t=out:st={max(0, span - 0.6):.2f}:d=0.6"]
    post_s = ",".join(post) if post else "null"
    chains.append(f"[{cur}]{post_s},format=yuv420p[base0]")
    final = "base0"
    nstep = [0]

    def over(src_chain: str, ov: str = "overlay=0:0:shortest=1"):
        nonlocal final
        nstep[0] += 1
        tag = f"ov{nstep[0]}"
        chains.append(src_chain + f"[in{nstep[0]}]")
        chains.append(f"[{final}][in{nstep[0]}]{ov},format=yuv420p[{tag}]")
        final = tag

    if look_name == "dark" and ed.get("fog", True):
        fog = graphics.fog_texture(ROOT / "assets" / "fog.png", W * 2, H)
        fi = inp("-loop", "1", "-framerate", fps, "-t", f"{span + 0.5:.3f}", "-i", fog)
        sp = ed.get("fog_speed", 35)
        over(f"[{fi}:v]format=rgba,crop={W}:{H}:x='mod(t*{sp},{W})':y=0,"
             f"colorchannelmixer=aa={ed.get('fog_opacity', 0.28)}")
    if item.get("mood") == "rain":  # mưa rơi
        from . import emotion

        rt = emotion.rain_texture(ROOT / "assets" / f"_rain_{W}.png", W, H)
        ri = inp("-loop", "1", "-framerate", fps, "-t", f"{span + 0.5:.3f}", "-i", rt)
        over(f"[{ri}:v]format=rgba,crop={W}:{H}:x=0:y='{H}-mod(t*{int(H * 1.6)},{H})'")
    label_delay = 0.4
    nc = shots[0].get("namecard") if shots else None
    if nc and nc[0]:
        png = labels / f"name_{hashlib.md5(('|'.join(nc)).encode()).hexdigest()[:10]}.png"
        if not png.exists():
            graphics.name_card_png(nc[0], nc[1], png, W, H)
        show = min(F[0] / fps, 4.5)
        ni = inp("-loop", "1", "-framerate", fps, "-t", f"{show:.2f}", "-i", png)
        over(f"[{ni}:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1,"
             f"fade=t=out:st={max(0.5, show - 0.4):.2f}:d=0.4:alpha=1,setpts=PTS+0.25/TB",
             "overlay=x='min(0,-260+(t-0.25)*1300)':y=0:eof_action=pass")
        label_delay = show + 0.3
    kws = [k for k in (item.get("keywords") or []) if k][:3]
    if kws:  # từ khoá hiện lần lượt đúng nhịp lời đọc (chữ dựng ở bước render -> dễ sửa)
        from . import mascot

        ch0 = (shots[0].get("char") or {}) if shots else {}
        if ch0.get("contrast"):
            kx, ky0 = 0.5, 0.3  # màn chia đôi: giữa khung, dưới nhãn BÊN NGOÀI/BÊN TRONG
        else:  # phía đối diện nhân vật để không đè bong bóng suy nghĩ
            kx = {"left": 0.72, "right": 0.28, "center": 0.5}.get(ch0.get("position", "left"), 0.72)
            ky0 = 0.12 if kx != 0.5 else 0.08
            if ch0.get("thought") or STYLE["story_caps"]:
                ky0 = 0.42 if ch0.get("thought") else 0.2
            if ch0.get("shadow"):
                ky0 = 0.62
        for i, kw in enumerate(kws):
            png = labels / f"kw_{hashlib.md5((kw + str(kx) + str(ky0) + str(i)).encode()).hexdigest()[:10]}.png"
            if not png.exists():
                pill = mascot.keyword_pill(kw, graphics.title_font(int(H * 0.06)))
                canvas = graphics.Image.new("RGBA", (W, H), (0, 0, 0, 0))
                px = int(W * kx - pill.width / 2)
                if kx == 0.5 and not ch0.get("contrast"):  # nhân vật ở giữa: xếp từ khoá 2 bên
                    px = int(W * (0.2 if i % 2 == 0 else 0.8) - pill.width / 2)
                canvas.alpha_composite(pill, (max(20, min(W - pill.width - 20, px)), int(H * (ky0 + 0.11 * i))))
                canvas.save(png)
            t0 = span * (0.15 + 0.6 * i / max(1, len(kws)))
            ki = inp("-loop", "1", "-framerate", fps, "-t", f"{span:.2f}", "-i", png)
            over(f"[{ki}:v]format=rgba,fade=t=in:st={t0:.2f}:d=0.25:alpha=1,"
                 f"fade=t=out:st={max(t0 + 0.5, span - 0.4):.2f}:d=0.3:alpha=1")
    q = shots[0].get("quote") if shots else None
    if q and q[0]:
        qp, qn = graphics.quote_frames(q[0], q[1], labels / f"q_{hashlib.md5(q[0].encode()).hexdigest()[:10]}", fps, W, H)
        qi = inp("-framerate", fps, "-i", qp)
        over(f"[{qi}:v]format=rgba,tpad=stop_mode=clone:stop_duration={max(0.1, span - qn / fps):.2f},"
             f"setpts=PTS+0.3/TB", "overlay=0:0:eof_action=pass")
    style = "collage" if look_name == "collage" else (
        "bold" if rc.get("card_style", "") == "bold_light" or (rc.get("card_style", "").startswith("bold")
                                                             and look_name not in ("noir_red", "dark", "noir")) else "dark")
    for k_, (ph, at) in enumerate(item.get("emph") or []):  # chữ nhấn mạnh đập ra màn hình
        from . import fx as fxmod

        png = labels / f"emph_{hashlib.md5((ph + style + str(W)).encode()).hexdigest()[:10]}.png"
        if not png.exists():
            fxmod.emphasis_png(ph, png, W, H, style)
        ei = inp("-loop", "1", "-framerate", fps, "-t", f"{span:.2f}", "-i", png)
        S = f"if(lt(t,{at:.2f}),1,if(lt(t,{at + 0.12:.2f}),1.6-0.6*(t-{at:.2f})/0.12,1))"
        over(f"[{ei}:v]format=rgba,fade=t=in:st={at:.2f}:d=0.05:alpha=1,"
             f"fade=t=out:st={min(span - 0.2, at + 1.4):.2f}:d=0.25:alpha=1,"
             f"scale=w='iw*{S}':h='ih*{S}':eval=frame",
             f"overlay=x='(W-overlay_w)/2':y='(H-overlay_h)/2':enable='gte(t,{at:.2f})':eof_action=pass")
    ov_ = item.get("overlay")
    if ov_:  # tên video / tên chương hiện đè, lời kể vẫn chạy
        from . import fx as fxmod

        png = labels / f"ovl_{hashlib.md5((ov_['small'] + ov_['big'] + style + str(W)).encode()).hexdigest()[:10]}.png"
        if not png.exists():
            fxmod.title_overlay_png(ov_["small"], ov_["big"], png, W, H, style, ov_["kind"])
        hold = min(span - 0.3, 3.6 if ov_["kind"] == "title" else 2.8)
        oi = inp("-loop", "1", "-framerate", fps, "-t", f"{span:.2f}", "-i", png)
        over(f"[{oi}:v]format=rgba,fade=t=in:st=0.1:d=0.3:alpha=1,fade=t=out:st={max(0.5, hold):.2f}:d=0.4:alpha=1",
             f"overlay=x='-{int(W * 0.06)}*max(0,1-(t-0.1)/0.35)':y=0:shortest=1")
    if item.get("hud"):  # bộ đếm góc trái trên (số dư, số ngày...) - đổi số thì chạy số
        from . import emotion

        hk = hashlib.md5((item.get("hud_prev", "") + "|" + item["hud"] + str(W) + str(RENDER_VERSION)).encode()).hexdigest()[:10]
        hp, hn = emotion.hud_frames(item.get("hud_prev", ""), item["hud"], labels / f"hud_{hk}", fps, W, H)
        hi = inp("-framerate", fps, "-i", hp)
        delay = 0.3 if hn > 1 else 0
        over(f"[{hi}:v]format=rgba,tpad=stop_mode=clone:stop_duration={span + 1:.2f},setpts=PTS+{delay}/TB",
             "overlay=0:0:eof_action=repeat")
    if item.get("type") == "scene" and item.get("label") and look_name != "collage":
        pattern, nfr = typewriter_frames(item["label"], labels / f"tw_{hashlib.md5(item['label'].encode()).hexdigest()[:10]}",
                                         fps, W, H)
        li = inp("-framerate", fps, "-i", pattern)
        hold_end = min(5.5, span - 0.8)
        over(f"[{li}:v]format=rgba,tpad=stop_mode=clone:stop_duration={max(0.1, hold_end - nfr / fps):.2f},"
             f"fade=t=out:st={max(0.2, hold_end - 0.5):.2f}:d=0.5:alpha=1,setpts=PTS+{label_delay:.2f}/TB",
             "overlay=0:0:eof_action=pass")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chains), "-map", f"[{final}]",
         "-frames:v", str(total), *_enc(cfg), str(out)])
    return out


def _silence(dur: float, out: Path) -> Path:
    if not out.exists():
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{dur:.4f}",
             "-c:a", "pcm_s16le", str(out)])
    return out


def build_voice_track(project: Project, tl: dict) -> Path:
    """Ghép giọng đọc + khoảng lặng thành 1 file WAV khớp chính xác timeline."""
    sil = project.path("audio", "_sil")
    sil.mkdir(exist_ok=True)
    parts = []
    for it in tl["items"]:
        if it["type"] == "scene":
            parts.append(Path(it["audio"]))
            gap = it["duration"] - it["audio_dur"]
        else:
            gap = it["duration"]
        if gap > 0.001:
            parts.append(_silence(gap, sil / f"sil_{gap:.4f}.wav"))
    parts.append(_silence(3.0, sil / "sil_3000.wav"))
    lst = project.path("audio", "_voice_list.txt")
    lst.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    out = project.path("audio", "voice_full.wav")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "44100", "-ac", "1",
         "-c:a", "pcm_s16le", str(out)])
    return out


def _music_file(auto: bool = True, style: str = "dark") -> Path | None:
    files = sorted([p for p in (ROOT / "assets" / "music").glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")])
    if files:
        return random.choice(files)
    if auto:
        from .sfx import auto_music

        return auto_music(ROOT / "assets" / "_auto_music.wav", style=style)
    return None


def render_video(project: Project, cfg: dict, workers: int = 0, preview: bool = False) -> Path:
    need_ffmpeg()
    tl = project.read_json("timeline.json")
    if not tl:
        raise SystemExit("Chưa có timeline.json")
    rc = cfg["render"]
    fps = rc["fps"]
    BRAND["name"] = rc.get("brand")
    BRAND["dark"] = rc.get("card_style") == "bold_dark"
    STYLE["story_caps"] = rc.get("subtitle_style") == "story" and bool(rc.get("burn_subtitles"))
    shots_dir = project.path("media", "shots")
    plates = project.path("media", "plates")
    plates.mkdir(exist_ok=True)
    labels = project.path("cards")

    jobs = []
    for it in tl["items"]:
        key = json.dumps([RENDER_VERSION, it["shots"], it.get("label"), it.get("keywords"), it["type"], rc.get("look"),
                          it.get("hud"), it.get("hud_prev"), it.get("mood"), STYLE["story_caps"],
                          it.get("fx"), it.get("accents"), it.get("emph"), it.get("overlay"),
                          rc["width"], cfg.get("edit", {}), rc.get("brand"),
                          round(it["start"] * fps)], sort_keys=True)
        out = shots_dir / f"item_{hashlib.md5(key.encode()).hexdigest()[:14]}.mp4"
        if out.with_suffix(".failed").exists():  # lần trước lỗi (nền đen tạm) -> dựng lại
            out.unlink(missing_ok=True)
            out.with_suffix(".failed").unlink()
        jobs.append((it, out))
    if preview:
        jobs = jobs[:6]

    todo = [j for j in jobs if not j[1].exists()]
    log(f"Render {len(todo)}/{len(jobs)} đoạn (đã cache {len(jobs) - len(todo)})...")
    workers = workers or max(1, (os.cpu_count() or 2) // 2)
    done = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(render_item, it, out, cfg, plates, labels): (it, out) for it, out in todo}
        for f in as_completed(futs):
            done += 1
            it, out = futs[f]
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                log(f"  ! đoạn {it.get('id', it['type'])} lỗi -> nền đen: {str(e).splitlines()[0][:200]}")
                out.with_suffix(".failed").write_text(str(e)[-3000:], encoding="utf-8")
                fr = sum(round((sh["start"] + sh["duration"]) * fps) - round(sh["start"] * fps) for sh in it["shots"])
                run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={rc['width']}x{rc['height']}:r={fps}",
                     "-frames:v", str(fr), *_enc(cfg), str(out)])
            if done % 10 == 0 or done == len(todo):
                log(f"  {done}/{len(todo)}")

    lst = project.path("media", "_concat.txt")
    lst.write_text("\n".join(f"file '{j[1].resolve().as_posix()}'" for j in jobs), encoding="utf-8")
    silent = project.path("output", "_video_silent.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])

    log("Ghép giọng đọc + nhạc nền...")
    voice = build_voice_track(project, tl)
    out = project.path("output", "preview.mp4" if preview else "final.mp4")
    from .sfx import build_music_track, build_sfx_track

    total = ffprobe_duration(silent)
    inputs = ["-i", str(silent), "-i", str(voice)]
    mood_track = build_music_track(tl, cfg, project.path("audio", "music_track.wav"))
    music = mood_track or _music_file(rc.get("auto_music", True), rc.get("auto_music_style", "dark"))

    sfx = build_sfx_track(tl, cfg, project.path("audio", "sfx_track.wav"))
    if music:
        inputs += (["-i", str(music)] if mood_track else ["-stream_loop", "-1", "-i", str(music)])
        mv = rc.get("music_volume", 0.1)
        af = (f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[v1][v2];"
              f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={mv},"
              f"afade=t=in:d=3,afade=t=out:st={max(0, total - 4):.2f}:d=4[m];"
              f"[m][v2]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
              f"[v1][md]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        af = "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a]"
    if sfx:
        idx = 3 if music else 2
        inputs += ["-i", str(sfx)]
        af = af.replace("[a]", "[a0]") + (f";[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                                          f"volume={cfg.get('sfx', {}).get('volume', 1.0)}[fx];"
                                          f"[a0][fx]amix=inputs=2:duration=first:normalize=0[a]")
    vf = []
    if rc.get("burn_subtitles"):
        srt = project.path("output", "subtitles.srt").resolve().as_posix().replace(":", r"\:")
        fdir = (ROOT / "assets" / "fonts").resolve().as_posix().replace(":", r"\:")
        if rc.get("subtitle_style") == "story":  # chữ kể chuyện viết tay phía trên khung (kiểu phim hoạt hình ngắn)
            style = ("FontName=Patrick Hand,FontSize=19,PrimaryColour=&H00F5F5F5,OutlineColour=&H00101010,"
                     "BackColour=&H64000000,BorderStyle=1,Outline=1,Shadow=1.5,Alignment=6,MarginV=18")
        elif rc.get("card_style", "").startswith("bold"):  # phụ đề đậm kiểu kênh giải thích
            style = ("FontName=Roboto Condensed,Bold=1,FontSize=20,PrimaryColour=&H00FFFFFF,"
                     "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,MarginV=36")
        else:
            style = ("FontName=Roboto Condensed,FontSize=18,PrimaryColour=&H00F0F0F0,"
                     "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=40")
        vf = ["-vf", f"subtitles='{srt}':fontsdir='{fdir}':force_style='{style}'"]
        vcodec = ["-c:v", "libx264", "-preset", rc.get("preset", "medium"), "-crf", str(rc.get("crf", 20)),
                  "-pix_fmt", "yuv420p"]
    else:
        vcodec = ["-c:v", "copy"]
    run(["ffmpeg", "-y", *inputs, "-filter_complex", af, "-map", "0:v", "-map", "[a]", *vf, *vcodec,
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)])
    silent.unlink(missing_ok=True)
    log(f"✓ Video: {out} ({ffprobe_duration(out) / 60:.1f} phút)")
    return out


def make_thumbnail(project: Project, cfg: dict) -> Path:
    script = project.read_json("script.json")
    plan = project.read_json("media_plan.json", {})
    imgs = [m for v in plan.values() for m in v if m["kind"] == "image" and Path(m["file"]).exists()
            and m.get("credit") != "AI-generated illustration"]
    out = project.path("output", "thumbnail.jpg")
    text = script.get("thumbnail_text") or script["title"]
    cs = cfg["render"].get("card_style", "")
    if cs.startswith("bold"):
        ai_imgs = [m for v in plan.values() for m in v if m["kind"] == "image" and Path(m["file"]).exists()]
        graphics.bold_thumbnail(Path(ai_imgs[0]["file"]) if ai_imgs else None, text, out, dark=cs == "bold_dark")
        log(f"✓ Thumbnail: {out}")
        return out
    if cfg["render"].get("look") == "dark":
        ent = [v[0] for k, v in plan.items() if k.endswith(":entity") and v]
        face = Path(ent[0]["file"]) if ent else (Path(imgs[0]["file"]) if imgs else None)
        bg = Path(imgs[1]["file"]) if len(imgs) > 1 else None
        stamp = cfg.get("thumbnail", {}).get("stamp", "CHƯA CÓ LỜI GIẢI" if cfg["channel"]["language"] == "vi"
                                                     else "UNSOLVED")
        graphics.crime_thumbnail(bg, face, text, stamp, out)
    else:
        graphics.thumbnail(Path(imgs[0]["file"]) if imgs else None, text, cfg["channel"]["name"], out,
                           cfg["render"].get("font", ""))
    log(f"✓ Thumbnail: {out}")
    return out

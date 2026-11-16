"""Giọng đọc (TTS) - nhiều backend mã nguồn mở trên GitHub.

  edge   : github.com/rany2/edge-tts        - giọng Neural của Microsoft, miễn phí, cần mạng.
  kokoro : github.com/hexgrad/kokoro        - tiếng Anh offline, chất lượng cao, chạy CPU.
  piper  : github.com/OHF-Voice/piper1-gpl   - offline, chạy CPU nhanh, có giọng vi_VN (vais1000).
  xtts   : viXTTS (huggingface capleaf/viXTTS, dựa trên coqui XTTS-v2) - CLONE giọng từ file mẫu, cần GPU.
  api    : VoiceStudio (github.com/debpalash/VoiceStudio) hoặc server bất kỳ chuẩn OpenAI /v1/audio/speech.
  omnivoice: github.com/k2-fsa/OmniVoice chạy trực tiếp bằng Python (GPU).
  command: chạy tool bất kỳ (F5-TTS-Vietnamese, GPT-SoVITS...) qua dòng lệnh.
Mỗi scene -> audio/<id>.wav, thời lượng ghi vào timing.json
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from .util import ROOT, Project, ffprobe_duration, log, run


POLISH = {"on": True}
# "Làm đẹp giọng" kiểu phòng thu: ấm dải trầm, rõ dải giữa, giảm xì 's', nén nhẹ, chút không gian phòng
POLISH_CHAIN = ("equalizer=f=140:t=q:w=1:g=2.5,equalizer=f=3200:t=q:w=1.2:g=1.8,equalizer=f=7000:t=q:w=2:g=-3,"
                "deesser=i=0.4,acompressor=threshold=-22dB:ratio=3.5:attack=4:release=120:makeup=2,"
                "aecho=0.8:0.85:28|46:0.12|0.07,")


def _norm(src: Path, dst: Path) -> None:
    """Chuẩn hoá về WAV 44.1kHz mono, cân bằng âm lượng, cắt khoảng lặng đầu/cuối (+ làm đẹp giọng nếu bật)."""
    polish = POLISH_CHAIN if POLISH["on"] else "acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
    run(["ffmpeg", "-y", "-i", str(src), "-af",
         "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
         f"highpass=f=70,{polish}loudnorm=I=-16:TP=-1.5",
         "-ar", "44100", "-ac", "1", str(dst)])


class EdgeTTS:
    def __init__(self, vc: dict):
        import edge_tts

        self.edge_tts = edge_tts
        self.voice = vc.get("edge_voice", "vi-VN-NamMinhNeural")
        self.rate = vc.get("edge_rate", "+0%")
        self.pitch = vc.get("edge_pitch", "+0Hz")

    def synth(self, text: str, out: Path, voice: str | None = None) -> None:
        tmp = out.with_suffix(".mp3")

        async def go():
            c = self.edge_tts.Communicate(text, voice or self.voice, rate=self.rate, pitch=self.pitch,
                                          proxy=os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or None)
            await c.save(str(tmp))

        import time

        tries = 10  # dịch vụ Edge thỉnh thoảng không trả âm thanh (NoAudioReceived) -> chờ lâu dần rồi thử lại
        for i in range(tries):
            try:
                asyncio.run(go())
                break
            except Exception as e:  # noqa: BLE001
                if i == tries - 1:
                    raise
                wait = min(45, 4 * (i + 1))
                log(f"  edge-tts thử lại sau {wait}s ({type(e).__name__})")
                time.sleep(wait)
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class PiperTTS:
    def __init__(self, vc: dict):
        from piper import PiperVoice, SynthesisConfig

        model = Path(vc.get("piper_model", "voices/vi_VN-vais1000-medium.onnx"))
        if not model.is_absolute():
            model = ROOT / model
        if not model.exists():
            raise SystemExit(f"Chưa có model piper {model}. Chạy: python studio.py voices --piper en_US-ryan-high")
        self.voice = PiperVoice.load(str(model))
        self.cfg = SynthesisConfig(length_scale=vc.get("piper_length_scale", 1.0))

    def synth(self, text: str, out: Path) -> None:
        tmp = out.with_name(out.stem + "_raw.wav")
        with wave.open(str(tmp), "wb") as wf:
            self.voice.synthesize_wav(text, wf, syn_config=self.cfg)
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class KokoroTTS:
    """github.com/hexgrad/kokoro - pip install kokoro soundfile (Windows cần thêm espeak-ng nếu báo lỗi)."""

    def __init__(self, vc: dict, lang: str):
        from kokoro import KPipeline  # type: ignore

        voice = vc.get("kokoro_voice", "am_michael")
        self.voice = voice
        self.speed = vc.get("kokoro_speed", 0.95)
        # a = American English, b = British English (theo chữ cái đầu tên giọng)
        self.pipe = KPipeline(lang_code=voice[0] if voice[0] in "ab" else "a")

    def synth(self, text: str, out: Path) -> None:
        import numpy as np

        chunks = [np.asarray(audio) for _, _, audio in self.pipe(text, voice=self.voice, speed=self.speed)
                  if audio is not None]
        audio = np.concatenate(chunks)
        tmp = out.with_name(out.stem + "_raw.wav")
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class XTTS:
    """viXTTS: pip install coqui-tts ; tải model: python studio.py voices --vixtts"""

    def __init__(self, vc: dict, lang: str):
        import torch
        from TTS.tts.configs.xtts_config import XttsConfig  # type: ignore
        from TTS.tts.models.xtts import Xtts  # type: ignore

        mdir = ROOT / vc.get("xtts_model_dir", "voices/viXTTS")
        ref = ROOT / vc.get("xtts_ref_wav", "voices/my_voice.wav")
        if not ref.exists():
            raise SystemExit(f"Cần file giọng mẫu {ref} (6-15 giây, giọng rõ, không nhạc nền)")
        config = XttsConfig()
        config.load_json(str(mdir / "config.json"))
        self.model = Xtts.init_from_config(config)
        self.model.load_checkpoint(config, checkpoint_dir=str(mdir), use_deepspeed=False)
        if torch.cuda.is_available():
            self.model.cuda()
        self.lat, self.spk = self.model.get_conditioning_latents(audio_path=str(ref), gpt_cond_len=30,
                                                                 max_ref_length=60, sound_norm_refs=False)
        self.lang = lang
        self.torch = torch

    def synth(self, text: str, out: Path) -> None:
        import numpy as np

        wavs = []
        try:
            from vinorm import TTSnorm  # type: ignore  # chuẩn hoá số/ngày tháng tiếng Việt

            if self.lang == "vi":
                text = TTSnorm(text, unknown=False, lower=False, rule=True)
        except ImportError:
            pass
        r = self.model.inference(text, self.lang, self.lat, self.spk, temperature=0.3, length_penalty=1.0,
                                 repetition_penalty=10.0, top_k=30, top_p=0.85, enable_text_splitting=True)
        wavs.append(np.asarray(r["wav"]))
        audio = np.concatenate(wavs)
        tmp = out.with_name(out.stem + "_raw.wav")
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class OmniVoiceTTS:
    """github.com/k2-fsa/OmniVoice - clone giọng 600+ ngôn ngữ (engine mặc định của VoiceStudio).
    pip install omnivoice soundfile  (+ torch bản CUDA). LƯU Ý: code Apache-2.0 nhưng trọng số model
    được ghi là CC-BY-NC (phi thương mại) - kiểm tra kỹ trước khi dùng cho kênh bật kiếm tiền."""

    def __init__(self, vc: dict, lang: str):
        import torch
        from omnivoice import OmniVoice, VoiceClonePrompt  # type: ignore

        dev = "cuda:0" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        self.model = OmniVoice.from_pretrained(vc.get("omnivoice_model", "k2-fsa/OmniVoice"), device_map=dev,
                                               dtype=torch.float16 if dev != "cpu" else torch.float32)
        ref = ROOT / vc.get("xtts_ref_wav", "voices/my_voice.wav")
        cache = ref.with_suffix(".omnivoice.pt")
        self.kw = {}
        if cache.exists():
            self.kw["voice_clone_prompt"] = VoiceClonePrompt.load(str(cache))
        elif ref.exists():
            prompt = self.model.create_voice_clone_prompt(ref_audio=str(ref), ref_text=vc.get("ref_text") or None)
            prompt.save(str(cache))
            self.kw["voice_clone_prompt"] = prompt
        elif vc.get("omnivoice_instruct"):
            self.kw["instruct"] = vc["omnivoice_instruct"]  # voice design: "male, deep voice, american accent"
        self.lang = lang
        self.speed = vc.get("omnivoice_speed", 1.0)

    def synth(self, text: str, out: Path) -> None:
        import numpy as np

        audio = self.model.generate(text=text, language=self.lang, speed=self.speed, **self.kw)[0]
        tmp = out.with_name(out.stem + "_raw.wav")
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes((np.clip(np.asarray(audio), -1, 1) * 32767).astype("<i2").tobytes())
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class OpenAICompatTTS:
    """Gọi server TTS chuẩn OpenAI (/v1/audio/speech). Dùng cho VoiceStudio (github.com/debpalash/VoiceStudio):
    mở app VoiceStudio -> clone giọng, lưu thành voice profile -> đặt tên profile vào voice.api_voice.
    Cũng chạy với các server khác có API tương thích OpenAI (Kokoro-FastAPI, AllTalk...)."""

    def __init__(self, vc: dict):
        import requests

        self.requests = requests
        self.url = vc.get("api_url", "http://127.0.0.1:3900/v1").rstrip("/") + "/audio/speech"
        self.body = {"model": vc.get("api_model", "tts-1"), "voice": vc.get("api_voice", "default"),
                     "speed": vc.get("api_speed", 1.0), "response_format": "wav"}
        self.headers = {"Authorization": f"Bearer {os.getenv('TTS_API_KEY', 'local')}"}

    def synth(self, text: str, out: Path) -> None:
        tmp = out.with_name(out.stem + "_raw.wav")
        for i in range(3):
            try:
                r = self.requests.post(self.url, json={**self.body, "input": text}, headers=self.headers,
                                       timeout=900)
                if r.status_code >= 400:
                    raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
                tmp.write_bytes(r.content)
                break
            except Exception as e:  # noqa: BLE001
                if i == 2:
                    raise SystemExit(f"Lỗi TTS API {self.url}: {e}\n(VoiceStudio đã mở chưa? Đúng cổng chưa?)")
                log(f"  TTS API thử lại ({e})")
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class CommandTTS:
    def __init__(self, vc: dict):
        self.tpl = vc["command"]

    def synth(self, text: str, out: Path) -> None:
        tmp = out.with_name(out.stem + "_raw.wav")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
        cmd = self.tpl.format(text_file=f.name, out_wav=str(tmp), text=text.replace('"', "'"))
        subprocess.run(cmd, shell=True, check=True)
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class VieNeuTTS:
    """VieNeu-TTS (github.com/pnnbao97/VieNeu-TTS) - tiếng Việt mã nguồn mở, rất tự nhiên, clone giọng từ 3-8 giây.
    pip install vieneu   | chạy được CPU (~1x thời gian thực trên 4 nhân), nhanh hơn nhiều nếu có GPU.
    Giọng dựng sẵn: Thiền Tâm Đức, Thanh Bình, Thái Sơn, Đức Trí, Ngọc Linh... (python studio.py voices --vieneu)"""

    def __init__(self, vc: dict):
        from vieneu import Vieneu  # type: ignore

        kw = {}
        if vc.get("vieneu_precision"):
            kw["precision"] = vc["vieneu_precision"]
        self.tts = Vieneu(**kw)
        self.voice = vc.get("vieneu_voice", "Thiền Tâm Đức")
        ref = vc.get("vieneu_ref_wav", "")
        refp = ROOT / ref if ref and not Path(ref).is_absolute() else Path(ref) if ref else None
        self.ref = str(refp) if refp and refp.exists() else None

    def synth(self, text: str, out: Path, voice: str | None = None) -> None:
        tmp = out.with_name(out.stem + "_raw.wav")
        v = voice or self.voice
        if voice and (voice.lower().endswith((".wav", ".mp3", ".flac")) or "/" in voice or "\\" in voice):
            ref = Path(voice) if Path(voice).is_absolute() else ROOT / voice  # giọng clone từ file mẫu
            audio = self.tts.infer(text, ref_audio=str(ref), denoise=True)
        elif self.ref and not voice:  # clone giọng của bạn
            audio = self.tts.infer(text, ref_audio=self.ref, denoise=True)
        else:
            audio = self.tts.infer(text, voice=v)
        self.tts.save(audio, str(tmp))
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class GoogleTTS:
    """Google Cloud Text-to-Speech - giọng Chirp 3 HD tiếng Việt (rất tự nhiên). Miễn phí 1 triệu ký tự/tháng.
    Xác thực (1 trong 2): GOOGLE_TTS_API_KEY trong .env, hoặc chạy trên VPS Google Cloud (tự lấy quyền của máy)."""

    URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

    def __init__(self, vc: dict, lang: str):
        import requests

        self.requests = requests
        self.voice = vc.get("google_voice", "vi-VN-Chirp3-HD-Charon")
        self.lang = "-".join(self.voice.split("-")[:2]) if self.voice.count("-") >= 2 else (lang + "-VN")
        self.rate = vc.get("google_rate", 0.95)
        self.key = os.getenv("GOOGLE_TTS_API_KEY", "")

    def _headers(self) -> dict:
        if self.key:
            return {"X-Goog-Api-Key": self.key}
        try:  # VPS Google Cloud: lấy token từ metadata server
            r = self.requests.get("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/"
                                  "default/token", headers={"Metadata-Flavor": "Google"}, timeout=5)
            r.raise_for_status()
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        except Exception:  # noqa: BLE001
            import subprocess

            tok = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True).stdout.strip()
            if not tok:
                raise SystemExit("Google TTS: cần GOOGLE_TTS_API_KEY trong .env, hoặc chạy trên VPS Google Cloud")
            return {"Authorization": f"Bearer {tok}"}

    def synth(self, text: str, out: Path, voice: str | None = None) -> None:
        import base64
        import time

        body = {"input": {"text": text}, "voice": {"languageCode": self.lang, "name": voice or self.voice},
                "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000, "speakingRate": self.rate}}
        for i in range(4):
            r = self.requests.post(self.URL, json=body, headers=self._headers(), timeout=120)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(3 * (i + 1))
                continue
            if r.status_code >= 400:
                raise SystemExit(f"Google TTS lỗi {r.status_code}: {r.text[:300]}")
            break
        tmp = out.with_name(out.stem + "_raw.wav")
        tmp.write_bytes(base64.b64decode(r.json()["audioContent"]))
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


class ElevenLabsTTS:
    """ElevenLabs API. Tiếng Việt: model eleven_v3 (tự nhiên, biểu cảm nhất) hoặc eleven_flash_v2_5 (rẻ, nhanh).
    Cần ELEVENLABS_API_KEY trong .env; voice_id lấy trong Voice Library (có thể là giọng bạn clone)."""

    def __init__(self, vc: dict, lang: str):
        import requests

        self.requests = requests
        self.key = os.getenv("ELEVENLABS_API_KEY", "")
        if not self.key:
            raise SystemExit("Thiếu ELEVENLABS_API_KEY trong .env")
        self.voice_id = vc.get("elevenlabs_voice_id", "")
        if not self.voice_id:
            raise SystemExit("Đặt voice.elevenlabs_voice_id trong config.yaml (ID giọng trong ElevenLabs)")
        self.model = vc.get("elevenlabs_model", "eleven_v3")
        self.lang = lang
        self.settings = {"stability": vc.get("elevenlabs_stability", 0.5),
                         "similarity_boost": vc.get("elevenlabs_similarity", 0.75),
                         "style": vc.get("elevenlabs_style", 0.15), "use_speaker_boost": True}

    def synth(self, text: str, out: Path, voice: str | None = None) -> None:
        import time

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice or self.voice_id}?output_format=mp3_44100_128"
        body = {"text": text, "model_id": self.model, "voice_settings": self.settings}
        if self.lang:
            body["language_code"] = self.lang
        for i in range(4):
            r = self.requests.post(url, json=body, headers={"xi-api-key": self.key}, timeout=300)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (i + 1))
                continue
            if r.status_code >= 400:
                raise SystemExit(f"ElevenLabs lỗi {r.status_code}: {r.text[:300]}")
            break
        tmp = out.with_name(out.stem + "_raw.mp3")
        tmp.write_bytes(r.content)
        _norm(tmp, out)
        tmp.unlink(missing_ok=True)


def get_engine(cfg: dict):
    vc = cfg["voice"]
    POLISH["on"] = vc.get("polish", True)
    b = vc.get("backend", "edge")
    if cfg["channel"].get("language") == "en":  # video tiếng Anh: VieNeu / giọng edge tiếng Việt không đọc được
        if b == "vieneu":
            b = vc.get("en_backend", "edge")
            log(f"  Video tiếng Anh -> dùng giọng {b}")
        if b == "edge" and str(vc.get("edge_voice", "")).startswith("vi-"):
            vc = {**vc, "edge_voice": vc.get("en_edge_voice", "en-US-AndrewNeural"),
                  "edge_rate": vc.get("en_edge_rate", vc.get("edge_rate", "-4%"))}
    if b == "edge":
        return EdgeTTS(vc)
    if b == "vieneu":
        return VieNeuTTS(vc)
    if b == "google":
        return GoogleTTS(vc, cfg["channel"]["language"])
    if b == "elevenlabs":
        return ElevenLabsTTS(vc, cfg["channel"]["language"])
    if b == "kokoro":
        return KokoroTTS(vc, cfg["channel"]["language"])
    if b == "piper":
        return PiperTTS(vc)
    if b == "xtts":
        return XTTS(vc, cfg["channel"]["language"])
    if b == "command":
        return CommandTTS(vc)
    if b == "omnivoice":
        return OmniVoiceTTS(vc, cfg["channel"]["language"])
    if b in ("api", "voicestudio"):
        return OpenAICompatTTS(vc)
    raise SystemExit(f"Backend giọng không hợp lệ: {b}")


def _concat_with_gap(a: Path, b: Path, gap: float) -> None:
    tmp = a.with_name(a.stem + "_cat.wav")
    run(["ffmpeg", "-y", "-i", str(a), "-i", str(b), "-filter_complex",
         f"[0:a]apad=pad_dur={gap}[x];[x][1:a]concat=n=2:v=0:a=1[o]", "-map", "[o]",
         "-ar", "44100", "-ac", "1", str(tmp)])
    tmp.replace(a)


def make_voice(project: Project, cfg: dict, redo: set[str] | None = None) -> dict:
    script = project.read_json("script.json")
    if not script:
        raise SystemExit("Chưa có script.json")
    eng = get_engine(cfg)
    cast = {k.strip().upper(): v for k, v in (cfg["voice"].get("cast") or {}).items() if v}
    timing = project.read_json("timing.json", {})
    scenes = [s for c in script["chapters"] for s in c["scenes"]]
    if not scenes:
        raise SystemExit("Kịch bản chưa có cảnh nào - chạy lại bước Kịch bản (chủ đề nên cụ thể hơn).")
    for i, s in enumerate(scenes, 1):
        out = project.path("audio", f"{s['id']}.wav")
        if s.get("locked") and out.exists() and s["id"] in timing:  # cảnh đã khoá: giữ giọng đã chọn
            continue
        if out.exists() and s["id"] in timing and not (redo and s["id"] in redo) \
                and timing[s["id"]].get("text") == s["narration"]:
            continue
        log(f"[{i}/{len(scenes)}] đọc {s['id']} ({len(s['narration'].split())} từ)")
        eng.synth(s["narration"], out)
        # Dàn giọng: câu trích dẫn (cảnh "quote") đọc bằng giọng riêng của nhân vật ngay sau lời dẫn
        who = ((s.get("entity") or {}).get("name") or "").strip().upper()
        cvoice = cast.get(who)
        quote = (s.get("on_screen_text") or "").strip()
        already = quote and quote.lower().strip('"“”.') in s["narration"].lower()
        if s.get("visual_type") == "quote" and quote and not already:
            qwav = out.with_name(out.stem + "_quote.wav")
            try:
                if cvoice:
                    eng.synth(quote, qwav, voice=cvoice)
                else:
                    eng.synth(quote, qwav)
                _concat_with_gap(out, qwav, cfg["voice"].get("quote_gap", 0.45))
                log(f"    + trích dẫn bằng giọng {'riêng của ' + who if cvoice else 'người dẫn chuyện'}")
            except TypeError:
                log("    ! engine này chưa hỗ trợ đổi giọng theo nhân vật")
            qwav.unlink(missing_ok=True)
        timing[s["id"]] = {"duration": ffprobe_duration(out), "text": s["narration"]}
        project.write_json("timing.json", timing)
    total = sum(t["duration"] for t in timing.values())
    log(f"✓ Giọng đọc xong: {total / 60:.1f} phút")
    return timing


def download_voices(piper: str = "", vixtts: bool = False, xtts_en: bool = False) -> None:
    vdir = ROOT / "voices"
    vdir.mkdir(exist_ok=True)
    if piper:
        subprocess.run([sys.executable, "-m", "piper.download_voices", piper, "--data-dir", str(vdir)], check=True)
        log(f"✓ Piper voice -> {vdir}")
    if vixtts:
        try:
            from huggingface_hub import snapshot_download  # type: ignore
        except ImportError:
            raise SystemExit("pip install huggingface_hub coqui-tts vinorm")
        snapshot_download("capleaf/viXTTS", local_dir=str(vdir / "viXTTS"))
        log(f"✓ viXTTS -> {vdir / 'viXTTS'} . Đặt file giọng mẫu vào voices/my_voice.wav")
    if xtts_en:
        try:
            from huggingface_hub import snapshot_download  # type: ignore
        except ImportError:
            raise SystemExit("pip install huggingface_hub coqui-tts")
        snapshot_download("coqui/XTTS-v2", local_dir=str(vdir / "XTTS-v2"))
        log(f"✓ XTTS-v2 -> {vdir / 'XTTS-v2'} . Đặt file giọng mẫu vào voices/my_voice.wav")


def list_vieneu_voices() -> None:
    from vieneu import Vieneu  # type: ignore

    for label, _ in Vieneu().list_preset_voices():
        print(label)


def list_edge_voices(lang_prefix: str = "vi") -> None:
    import edge_tts

    async def go():
        for v in await edge_tts.list_voices():
            if v["Locale"].lower().startswith(lang_prefix.lower()):
                print(f"{v['ShortName']:35} {v['Gender']:7} {v['Locale']}")

    asyncio.run(go())


def preview_duration(path: Path) -> float:
    return ffprobe_duration(path)

"""
Core TTS engine – multi-backend wrapper (Qwen, Piper, Coqui).
Handles model loading, text chunking, and audio generation.
"""
import os
import shlex
import shutil
import subprocess
import sys
import threading
import asyncio

import numpy as np
import soundfile as sf
import torch

from text_processor import TextProcessor

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPER_DEFAULT_MODELS = (
    os.path.join(PROJECT_DIR, "models", "piper", "pt_BR-faber-medium.onnx"),
    os.path.join(PROJECT_DIR, "pt_BR-faber-medium.onnx"),
)

# Speakers actually supported by Qwen3-TTS CustomVoice.
# Each entry's native language is listed in SPEAKER_NATIVE_LANGUAGE for reference.
SPEAKERS = [
    "Ryan",      # English (default)
    "Aiden",     # English
    "Vivian",    # Chinese
    "Serena",    # Chinese
    "Uncle_Fu",  # Chinese
    "Dylan",     # Chinese (Beijing dialect)
    "Eric",      # Chinese (Sichuan dialect)
    "Ono_Anna",  # Japanese
    "Sohee",     # Korean
]

SPEAKER_NATIVE_LANGUAGE = {
    "Ryan": "English",
    "Aiden": "English",
    "Vivian": "Chinese",
    "Serena": "Chinese",
    "Uncle_Fu": "Chinese",
    "Dylan": "Chinese",
    "Eric": "Chinese",
    "Ono_Anna": "Japanese",
    "Sohee": "Korean",
}

# Languages supported by Qwen3-TTS (10 total).
LANGUAGES = [
    "English",
    "Chinese",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
]

QWEN_SPEAKER_IDS = {
    "Ryan": "ryan",
    "Aiden": "aiden",
    "Vivian": "vivian",
    "Serena": "serena",
    "Uncle_Fu": "uncle_fu",
    "Dylan": "dylan",
    "Eric": "eric",
    "Ono_Anna": "ono_anna",
    "Sohee": "sohee",
}

QWEN_LANGUAGE_IDS = {
    "Auto": "auto",
    "Chinese": "chinese",
    "English": "english",
    "French": "french",
    "German": "german",
    "Italian": "italian",
    "Japanese": "japanese",
    "Korean": "korean",
    "Portuguese": "portuguese",
    "Russian": "russian",
    "Spanish": "spanish",
}

BACKENDS = {
    "qwen": "Qwen3-TTS",
    "edge": "Edge-TTS (Light)",
    "piper": "Piper TTS",
    "coqui": "Coqui TTS",
    "gemini": "Gemini TTS (Cloud)",
}

EDGE_LANGUAGE_DEFAULT_VOICE = {
    "English": "en-US-GuyNeural",
    "Portuguese": "pt-BR-AntonioNeural",
    "Spanish": "es-ES-AlvaroNeural",
    "French": "fr-FR-HenriNeural",
    "German": "de-DE-ConradNeural",
    "Italian": "it-IT-DiegoNeural",
    "Japanese": "ja-JP-KeitaNeural",
    "Korean": "ko-KR-InJoonNeural",
    "Chinese": "zh-CN-YunxiNeural",
    "Arabic": "ar-SA-HamedNeural",
    "Hindi": "hi-IN-MadhurNeural",
    "Russian": "ru-RU-DmitryNeural",
}

EDGE_VOICES = [
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-GB-RyanNeural",
    "pt-BR-AntonioNeural",
    "pt-BR-FranciscaNeural",
    "es-ES-AlvaroNeural",
    "es-MX-DaliaNeural",
    "fr-FR-HenriNeural",
    "fr-FR-DeniseNeural",
    "de-DE-ConradNeural",
    "de-DE-KatjaNeural",
    "it-IT-DiegoNeural",
    "it-IT-ElsaNeural",
    "ja-JP-KeitaNeural",
    "ja-JP-NanamiNeural",
    "ko-KR-InJoonNeural",
    "ko-KR-SunHiNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-XiaoxiaoNeural",
    "ar-SA-HamedNeural",
    "ar-SA-ZariyahNeural",
    "hi-IN-MadhurNeural",
    "hi-IN-SwaraNeural",
    "ru-RU-DmitryNeural",
    "ru-RU-SvetlanaNeural",
]

# Voices exposed by the Google Gemini TTS prebuilt voice set.
GEMINI_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]

# Selectable Coqui models. XTTS v2 is multilingual (incl. pt-BR) and is the
# default; the pt-BR VITS model is a lighter, monolingual alternative.
COQUI_MODELS = {
    "tts_models/multilingual/multi-dataset/xtts_v2": "XTTS v2 (multilíngue)",
    "tts_models/pt/cv/vits": "VITS pt-BR (leve)",
}
COQUI_DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

# Curated subset of XTTS v2 built-in studio speakers (the model ships ~58).
COQUI_XTTS_SPEAKERS = [
    "Ana Florence", "Sofia Hellen", "Alison Dietlinde", "Gracie Wise",
    "Tammie Ema", "Annmarie Nele", "Brenda Stern", "Henriette Usha",
    "Daisy Studious", "Alexandra Hisakawa", "Claribel Dervla", "Andrew Chipper",
    "Damien Black", "Craig Gutsy", "Marcos Rudaski", "Viktor Eka",
]

# XTTS per-language character limit (text longer than this is truncated by the
# model). Used to size chunks so long blocks synthesize fully instead of failing.
COQUI_CHAR_LIMITS = {
    "en": 250, "de": 253, "fr": 273, "es": 239, "it": 213, "pt": 203,
    "pl": 224, "tr": 226, "ru": 182, "nl": 251, "cs": 186, "ar": 166,
    "zh-cn": 82, "hu": 224, "ko": 95, "ja": 71, "hi": 150,
}

# Coqui / XTTS expect 2-letter language codes.
COQUI_LANG_CODES = {
    "English": "en",
    "Portuguese": "pt",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Chinese": "zh-cn",
    "Russian": "ru",
}

# Voice names available per backend, surfaced as metadata so the UI can show
# only the voices that belong to the selected backend. Piper's voice is
# determined by the loaded .onnx model, so it has no selectable list here.
BACKEND_VOICES = {
    "qwen": SPEAKERS,
    "edge": EDGE_VOICES,
    "coqui": COQUI_XTTS_SPEAKERS,
    "gemini": GEMINI_VOICES,
    "piper": [],
}

# Languages each backend can actually handle, surfaced as metadata so the UI
# filters the language dropdown to what the selected backend supports. Coqui
# reflects the default XTTS v2 model; Piper's language is baked into the loaded
# .onnx voice (the bundled default is pt-BR).
BACKEND_LANGUAGES = {
    "qwen": LANGUAGES,
    "edge": list(EDGE_LANGUAGE_DEFAULT_VOICE.keys()),
    "coqui": [
        "Portuguese", "English", "Spanish", "French", "German", "Italian",
        "Russian", "Chinese", "Japanese", "Korean",
    ],
    "gemini": LANGUAGES,
    "piper": ["Portuguese"],
}


def _auto_backend_for_device() -> str:
    requested = os.getenv("TTS_BACKEND")
    if requested:
        return requested.strip().lower()
    if not torch.cuda.is_available():
        return "edge"
    try:
        total_mem = torch.cuda.get_device_properties(0).total_memory
        gb = total_mem / (1024 ** 3)
        return "edge" if gb <= 4.5 else "qwen"
    except Exception:
        return "qwen"


DEFAULT_BACKEND = _auto_backend_for_device()
DEFAULT_DEVICE = os.getenv("TTS_DEVICE", "cuda:0").strip()


def _is_cuda_device(device: str) -> bool:
    return (device or "").strip().lower().startswith("cuda")


def _require_torch_cuda(device: str, backend: str) -> None:
    if not _is_cuda_device(device):
        return
    if torch.cuda.is_available():
        return
    raise RuntimeError(
        f"{backend} was requested with device={device}, but PyTorch cannot see a CUDA GPU. "
        "Check nvidia-smi/driver installation or select device=cpu."
    )


class CancelledError(RuntimeError):
    """Raised when a generation is aborted because should_cancel() became true."""


# ── Subprocess tracking ─────────────────────────────────────────────────────
# Every subprocess a backend spawns (piper, ffmpeg, ...) is registered here so
# it can be actually terminated on cancel or on server shutdown, instead of
# being left running as an orphan.
_active_processes: set[subprocess.Popen] = set()
_active_processes_lock = threading.Lock()


def _register_process(proc: subprocess.Popen) -> None:
    with _active_processes_lock:
        _active_processes.add(proc)


def _unregister_process(proc: subprocess.Popen) -> None:
    with _active_processes_lock:
        _active_processes.discard(proc)


def terminate_all_processes() -> None:
    """Terminate every tracked backend subprocess (used on server shutdown)."""
    with _active_processes_lock:
        procs = list(_active_processes)
    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            pass
    for proc in procs:
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _run_subprocess(cmd, *, input_bytes=None, should_cancel=None, poll_interval=0.25):
    """Run *cmd* as a tracked subprocess while polling *should_cancel*.

    Returns ``(returncode, stdout_bytes, stderr_bytes)``. If *should_cancel*
    returns true before the process finishes, the process is terminated (then
    killed if it does not exit) and :class:`CancelledError` is raised.
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_bytes is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _register_process(proc)
    result: dict = {}

    def _communicate():
        try:
            result["out"], result["err"] = proc.communicate(input=input_bytes)
        except Exception as exc:  # pragma: no cover - defensive
            result["exc"] = exc

    worker = threading.Thread(target=_communicate, daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(timeout=poll_interval)
            if should_cancel and should_cancel():
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                worker.join(timeout=2)
                raise CancelledError("Job cancelled")
    finally:
        _unregister_process(proc)
    if "exc" in result:
        raise result["exc"]
    return proc.returncode, result.get("out"), result.get("err")


class BaseBackend:
    name = "base"

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        raise NotImplementedError

    def is_loaded(self) -> bool:
        raise NotImplementedError

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None, speed: float = 1.0, should_cancel=None):
        raise NotImplementedError


class QwenBackend(BaseBackend):
    name = "qwen"

    def __init__(self):
        self.model = None
        self.sample_rate = 24000

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        try:
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError(
                "qwen-tts not installed. Install it with: pip install qwen-tts"
            ) from exc
        if progress_cb:
            progress_cb("Loading model...", 0)
        _require_torch_cuda(device, "Qwen")
        dtype = torch.bfloat16 if _is_cuda_device(device) else torch.float32
        self.model = Qwen3TTSModel.from_pretrained(
            os.getenv("QWEN_MODEL_ID", MODEL_ID),
            device_map=device,
            dtype=dtype,
        )
        if progress_cb:
            progress_cb("Model ready.", 100)

    def is_loaded(self) -> bool:
        return self.model is not None

    @staticmethod
    def _normalize_choice(value: str, mapping: dict[str, str], fallback_label: str) -> str:
        if not value:
            return mapping[fallback_label]
        raw = value.strip()
        if raw in mapping:
            return mapping[raw]
        lowered = raw.lower()
        for label, backend_id in mapping.items():
            if lowered == label.lower() or lowered == backend_id.lower():
                return backend_id
        return mapping[fallback_label]

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None, speed: float = 1.0, should_cancel=None):
        speaker_id = self._normalize_choice(speaker, QWEN_SPEAKER_IDS, "Ryan")
        language_id = self._normalize_choice(language, QWEN_LANGUAGE_IDS, "English")
        if speaker_id != (speaker or "").strip():
            print(f"[QwenBackend] Normalized speaker '{speaker}' -> '{speaker_id}'.")
        if language_id != (language or "").strip():
            print(f"[QwenBackend] Normalized language '{language}' -> '{language_id}'.")

        # Cross-check with the model's own runtime-reported lists, when available.
        try:
            supported_speakers = self.model.get_supported_speakers()
            if supported_speakers:
                speaker_lookup = {item.lower(): item for item in supported_speakers}
                if speaker_id.lower() not in speaker_lookup:
                    print(f"[QwenBackend] Speaker '{speaker_id}' not in model list {supported_speakers}; using first available.")
                    speaker_id = supported_speakers[0]
                else:
                    speaker_id = speaker_lookup[speaker_id.lower()]
        except Exception:
            pass
        try:
            supported_langs = self.model.get_supported_languages()
            if supported_langs:
                language_lookup = {item.lower(): item for item in supported_langs}
                if language_id.lower() not in language_lookup:
                    print(f"[QwenBackend] Language '{language_id}' not in model list {supported_langs}; using 'english'.")
                    language_id = language_lookup.get("english", supported_langs[0])
                else:
                    language_id = language_lookup[language_id.lower()]
        except Exception:
            pass

        print(f"[QwenBackend] generate(language={language_id!r}, speaker={speaker_id!r}, chars={len(text)})")

        chunks = TextProcessor.split_for_tts(text)
        n = len(chunks)
        all_wavs: list[np.ndarray] = []

        for i, chunk in enumerate(chunks):
            if should_cancel and should_cancel():
                raise CancelledError("Job cancelled")
            if progress_cb:
                progress_cb(f"Chunk {i + 1}/{n}...", int(i / n * 90))
            wavs, sr = self.model.generate_custom_voice(
                text=chunk,
                language=language_id,
                speaker=speaker_id,
            )
            self.sample_rate = sr
            all_wavs.append(wavs[0])

        audio = np.concatenate(all_wavs) if len(all_wavs) > 1 else all_wavs[0]
        sf.write(output_path, audio, self.sample_rate)

        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, self.sample_rate


class EdgeBackend(BaseBackend):
    name = "edge"

    def __init__(self):
        self._loaded = False

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        if progress_cb:
            progress_cb("Preparing Edge-TTS...", 20)
        self._loaded = True
        if progress_cb:
            progress_cb("Edge-TTS ready.", 100)

    def is_loaded(self) -> bool:
        return self._loaded

    @staticmethod
    def _resolve_voice(language: str, speaker: str | None) -> str:
        # If UI provides a full Edge voice id, use it directly.
        if speaker and "Neural" in speaker and "-" in speaker:
            return speaker.strip()
        return EDGE_LANGUAGE_DEFAULT_VOICE.get(language, "en-US-GuyNeural")

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None, speed: float = 1.0, should_cancel=None):
        try:
            import edge_tts
        except ImportError as exc:
            raise ImportError("edge-tts not installed. Run: pip install edge-tts") from exc

        voice = self._resolve_voice(language=language, speaker=speaker)

        # Convert speed multiplier to Edge-TTS rate string (e.g. 1.5 → "+50%")
        rate_pct = int((speed - 1.0) * 100)
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

        # Synthesize in sentence-sized chunks so cancellation is responsive and
        # progress reflects real work — a single whole-document save() blocks for
        # minutes and only checks should_cancel before/after (i.e. never mid-run).
        chunks = TextProcessor.split_for_tts(text)
        if not chunks:
            raise RuntimeError("No text to synthesize with Edge-TTS.")
        n = len(chunks)
        tmp_mp3 = f"{output_path}.edge.mp3"

        def _cancelled() -> bool:
            return bool(should_cancel and should_cancel())

        async def _run():
            with open(tmp_mp3, "wb") as mp3:
                for i, chunk in enumerate(chunks):
                    if _cancelled():
                        raise CancelledError("Job cancelled")
                    if progress_cb:
                        progress_cb(f"Chunk {i + 1}/{n}...", int(i / n * 90))
                    comm = edge_tts.Communicate(chunk, voice=voice, rate=rate_str)
                    async for part in comm.stream():
                        # Check between streamed packets for near-instant cancel.
                        if _cancelled():
                            raise CancelledError("Job cancelled")
                        if part.get("type") == "audio" and part.get("data"):
                            mp3.write(part["data"])

        try:
            asyncio.run(_run())
            if _cancelled():
                raise CancelledError("Job cancelled")
            if progress_cb:
                progress_cb("Converting audio...", 92)
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", tmp_mp3,
                "-ac", "1", "-ar", "24000", output_path,
            ]
            returncode, _out, _err = _run_subprocess(ffmpeg_cmd, should_cancel=should_cancel)
            if returncode != 0:
                raise RuntimeError("ffmpeg failed during Edge-TTS WAV conversion.")
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg is required for Edge-TTS WAV conversion. Install ffmpeg or use another backend.") from exc
        finally:
            if os.path.exists(tmp_mp3):
                os.remove(tmp_mp3)

        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, 24000


class PiperBackend(BaseBackend):
    name = "piper"

    def __init__(self):
        self._loaded = False
        self.model_path = None
        self.config_path = None
        self.use_cuda = False
        self._invoke: list[str] = []

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        if progress_cb:
            progress_cb("Loading model...", 0)

        # Resolve how to invoke piper: prefer the standalone CLI if present,
        # otherwise fall back to `python -m piper` (piper-tts python package).
        piper_bin = shutil.which("piper")
        if piper_bin:
            self._invoke = [piper_bin]
        else:
            try:
                import piper  # noqa: F401
                self._invoke = [sys.executable, "-m", "piper"]
            except ImportError as exc:
                raise RuntimeError(
                    "Piper not found. Install it with: pip install piper-tts "
                    "or download a binary from https://github.com/rhasspy/piper/releases."
                ) from exc

        configured_model = os.getenv("PIPER_MODEL", "").strip()
        if configured_model and not os.path.isabs(configured_model):
            configured_model = os.path.join(PROJECT_DIR, configured_model)
        model_path = configured_model or next(
            (path for path in PIPER_DEFAULT_MODELS if os.path.exists(path)),
            None,
        )
        if not model_path:
            raise RuntimeError(
                "PIPER_MODEL environment variable not set. Point it to a Piper .onnx "
                "voice model, e.g. export PIPER_MODEL=/path/to/voice.onnx, "
                "or run: python scripts/ensure_models.py --piper"
            )
        if not os.path.exists(model_path):
            raise RuntimeError(f"PIPER_MODEL file does not exist: {model_path}")
        config_path = os.getenv("PIPER_CONFIG", "").strip()
        if config_path and not os.path.isabs(config_path):
            config_path = os.path.join(PROJECT_DIR, config_path)
        if not config_path:
            candidate = f"{model_path}.json"
            if os.path.exists(candidate):
                config_path = candidate
        if config_path and not os.path.exists(config_path):
            raise RuntimeError(f"PIPER_CONFIG file does not exist: {config_path}")
        self.model_path = model_path
        self.config_path = config_path
        self.use_cuda = _is_cuda_device(device)
        if self.use_cuda:
            # CUDA is best-effort for Piper: if ONNX Runtime can't expose the
            # CUDA provider (e.g. the CPU-only `onnxruntime` wheel is installed
            # instead of `onnxruntime-gpu`, or CUDA/driver is missing), fall back
            # to CPU with a warning instead of failing synthesis entirely.
            reason = ""
            try:
                import onnxruntime as ort
                if "CUDAExecutionProvider" not in set(ort.get_available_providers()):
                    reason = (
                        "ONNX Runtime does not expose CUDAExecutionProvider "
                        "(install onnxruntime-gpu with matching CUDA/cuDNN)"
                    )
            except Exception as exc:
                reason = f"onnxruntime not available ({exc})"
            if reason:
                self.use_cuda = False
                msg = f"Piper CUDA requested but unavailable: {reason}. Falling back to CPU."
                print(f"[PiperBackend] {msg}")
                if progress_cb:
                    progress_cb(msg, 90)
        self._loaded = True
        if progress_cb:
            progress_cb("Model ready.", 100)

    def is_loaded(self) -> bool:
        return self._loaded

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None, speed: float = 1.0, should_cancel=None):
        if progress_cb:
            progress_cb("Generating...", 40)
        cmd = list(self._invoke) + ["-m", self.model_path, "-f", output_path]
        if self.config_path:
            cmd += ["-c", self.config_path]
        if self.use_cuda:
            cmd += ["--cuda"]
        if speed != 1.0:
            cmd += ["--length-scale", str(1.0 / speed)]
        extra_args = os.getenv("PIPER_ARGS", "").strip()
        if extra_args:
            cmd += shlex.split(extra_args)

        returncode, _out, err = _run_subprocess(
            cmd,
            input_bytes=text.encode("utf-8"),
            should_cancel=should_cancel,
        )
        if returncode != 0:
            stderr = err.decode("utf-8", errors="replace") if err else ""
            raise RuntimeError(f"Piper failed: {stderr.strip() or f'exit code {returncode}'}")

        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, 0


class CoquiBackend(BaseBackend):
    name = "coqui"

    def __init__(self):
        self.tts = None
        self.model_name = None

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        try:
            from TTS.api import TTS as CoquiTTS
        except ImportError as exc:
            raise RuntimeError(
                "Coqui TTS not installed. Install it with: pip install 'coqui-tts[codec]' "
                "(maintained Idiap fork; works on Python 3.10–3.14)."
            ) from exc
        if progress_cb:
            progress_cb("Loading model...", 0)
        model_name = os.getenv("COQUI_MODEL", COQUI_DEFAULT_MODEL)
        # Auto-accept the Coqui model license (required for XTTS) so loading
        # does not block on an interactive prompt.
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        _require_torch_cuda(device, "Coqui")
        self.tts = CoquiTTS(model_name=model_name)
        if _is_cuda_device(device):
            try:
                self.tts.to(device)
            except Exception as exc:  # fall back to CPU if the move fails
                print(f"[CoquiBackend] could not move model to {device}: {exc}")
        self.model_name = model_name
        if progress_cb:
            progress_cb("Model ready.", 100)

    def is_loaded(self) -> bool:
        return self.tts is not None

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None, speed: float = 1.0, should_cancel=None):
        if should_cancel and should_cancel():
            raise CancelledError("Job cancelled")

        kwargs: dict = {}

        # Multi-speaker models (e.g. XTTS) require a valid speaker; the Qwen/Edge
        # names ("Ryan", "pt-BR-...") mean nothing here, so pick a real one.
        speakers = list(getattr(self.tts, "speakers", None) or [])
        if speakers:
            if speaker and speaker in speakers:
                kwargs["speaker"] = speaker
            else:
                default_speaker = next(
                    (s for s in COQUI_XTTS_SPEAKERS if s in speakers),
                    speakers[0],
                )
                kwargs["speaker"] = default_speaker

        # Multilingual models (e.g. XTTS) require a 2-letter language code.
        code = None
        languages = list(getattr(self.tts, "languages", None) or [])
        if languages:
            code = COQUI_LANG_CODES.get(language, language)
            if code not in languages:
                code = "pt" if "pt" in languages else languages[0]
            kwargs["language"] = code

        # XTTS enforces a per-language character limit and truncates/raises past
        # it. Split into chunks under that limit so long blocks synthesize fully
        # and cancellation/progress stay responsive.
        limit = COQUI_CHAR_LIMITS.get(code or COQUI_LANG_CODES.get(language, ""), 200)
        chunks = TextProcessor.split_for_tts(text, max_chars=max(80, limit - 3))
        if not chunks:
            raise RuntimeError("No text to synthesize with Coqui TTS.")
        n = len(chunks)

        sample_rate = getattr(
            getattr(self.tts, "synthesizer", None), "output_sample_rate", 24000
        )
        all_wavs: list[np.ndarray] = []
        for i, chunk in enumerate(chunks):
            if should_cancel and should_cancel():
                raise CancelledError("Job cancelled")
            if progress_cb:
                progress_cb(f"Chunk {i + 1}/{n}...", int(i / n * 90))
            wav = self.tts.tts(text=chunk, **kwargs)
            all_wavs.append(np.asarray(wav, dtype=np.float32))

        audio = np.concatenate(all_wavs) if len(all_wavs) > 1 else all_wavs[0]
        sf.write(output_path, audio, int(sample_rate))
        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, int(sample_rate)


class GeminiBackend(BaseBackend):
    """Google Gemini TTS backend using the google-genai streaming API."""
    name = "gemini"

    def __init__(self):
        self._loaded = False

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        try:
            from google import genai  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "google-genai not installed. Run: pip install google-genai"
            ) from exc
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable not set. "
                "Set it to your Google AI Studio API key."
            )
        if progress_cb:
            progress_cb("Gemini TTS ready.", 100)
        self._loaded = True

    def is_loaded(self) -> bool:
        return self._loaded

    @staticmethod
    def _convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
        import struct
        bits_per_sample = 16
        rate = 24000
        for param in mime_type.split(";"):
            param = param.strip()
            if param.lower().startswith("rate="):
                try:
                    rate = int(param.split("=", 1)[1])
                except (ValueError, IndexError):
                    pass
            elif param.startswith("audio/L"):
                try:
                    bits_per_sample = int(param.split("L", 1)[1])
                except (ValueError, IndexError):
                    pass
        num_channels = 1
        data_size = len(audio_data)
        bytes_per_sample = bits_per_sample // 8
        block_align = num_channels * bytes_per_sample
        byte_rate = rate * block_align
        chunk_size = 36 + data_size
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", chunk_size, b"WAVE", b"fmt ",
            16, 1, num_channels, rate, byte_rate,
            block_align, bits_per_sample, b"data", data_size,
        )
        return header + audio_data

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None, speed: float = 1.0, should_cancel=None):
        try:
            from google import genai
            from google.genai import types  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai not installed. Run: pip install google-genai") from exc

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set.")

        if progress_cb:
            progress_cb("Connecting to Gemini TTS...", 10)

        client = genai.Client(api_key=api_key)
        model = "gemini-3.1-flash-tts-preview"
        voice_name = speaker if speaker in GEMINI_VOICES else "Zephyr"
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=text)])]
        config = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        )

        if progress_cb:
            progress_cb("Generating with Gemini TTS...", 40)

        audio_chunks: list[bytes] = []
        mime_type = "audio/L16;rate=24000"
        for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
            if should_cancel and should_cancel():
                raise CancelledError("Job cancelled")
            if not chunk.parts:
                continue
            part = chunk.parts[0]
            if part.inline_data and part.inline_data.data:
                audio_chunks.append(part.inline_data.data)
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type

        if not audio_chunks:
            raise RuntimeError("Gemini TTS returned no audio data")

        raw_audio = b"".join(audio_chunks)
        wav_data = self._convert_to_wav(raw_audio, mime_type)
        with open(output_path, "wb") as f:
            f.write(wav_data)

        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, 24000


class TTSEngine:
    _instance = None
    _class_lock = threading.Lock()

    def __init__(self):
        self._gen_lock = threading.Lock()
        self._backends = {
            "qwen": QwenBackend(),
            "edge": EdgeBackend(),
            "piper": PiperBackend(),
            "coqui": CoquiBackend(),
            "gemini": GeminiBackend(),
        }

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls):
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def list_backends(self) -> list[dict[str, str]]:
        return [{"id": k, "label": BACKENDS[k]} for k in self._backends]

    def _normalize_backend(self, backend: str | None) -> str:
        name = (backend or DEFAULT_BACKEND).strip().lower()
        return name if name in self._backends else "qwen"

    # ── Model ─────────────────────────────────────────────────────────────────

    def load_model(self, backend: str | None = None, device: str = DEFAULT_DEVICE, progress_cb=None):
        name = self._normalize_backend(backend)
        return self._backends[name].load_model(device=device, progress_cb=progress_cb)

    def is_loaded(self, backend: str | None = None) -> bool:
        name = self._normalize_backend(backend)
        return self._backends[name].is_loaded()

    # ── Generation ────────────────────────────────────────────────────────────

    def generate(
        self,
        text: str,
        language: str = "English",
        speaker: str = "Ryan",
        output_path: str = "output.wav",
        backend: str | None = None,
        device: str = DEFAULT_DEVICE,
        progress_cb=None,
        normalize_text: bool = True,
        speed: float = 1.0,
        should_cancel=None,
    ) -> tuple[str, int]:
        """Generate speech and write to *output_path*.

        *progress_cb(message, pct)* is called with status updates.
        When *normalize_text* is True (default) the input is reflowed and
        numbers/dates/currencies/abbreviations are expanded for the given
        language before being sent to the backend.
        Returns *(output_path, sample_rate)*.
        """
        name = self._normalize_backend(backend)
        if normalize_text:
            try:
                from text_normalizer import normalize as _normalize
                text = _normalize(text, language=language)
            except Exception as exc:  # never let normalization break generation
                print(f"[TTSEngine] text normalization skipped: {exc}")

        with self._gen_lock:
            if not self._backends[name].is_loaded():
                self._backends[name].load_model(device=device, progress_cb=progress_cb)
            return self._backends[name].generate(
                text=text,
                language=language,
                speaker=speaker,
                output_path=output_path,
                progress_cb=progress_cb,
                speed=speed,
                should_cancel=should_cancel,
            )

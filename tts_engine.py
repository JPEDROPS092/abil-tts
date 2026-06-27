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
PIPER_DEFAULT_MODEL = os.path.join(
    PROJECT_DIR,
    "models",
    "piper",
    "pt_BR-faber-medium.onnx",
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

BACKENDS = {
    "qwen": "Qwen3-TTS",
    "edge": "Edge-TTS (Light)",
    "piper": "Piper TTS",
    "coqui": "Coqui TTS",
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


class BaseBackend:
    name = "base"

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        raise NotImplementedError

    def is_loaded(self) -> bool:
        raise NotImplementedError

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None):
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
            MODEL_ID,
            device_map=device,
            dtype=dtype,
        )
        if progress_cb:
            progress_cb("Model ready.", 100)

    def is_loaded(self) -> bool:
        return self.model is not None

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None):
        # Validate against what the model actually supports — fall back gracefully.
        if speaker not in SPEAKERS:
            print(f"[QwenBackend] Unknown speaker '{speaker}', falling back to 'Ryan'.")
            speaker = "Ryan"
        if language not in LANGUAGES:
            print(f"[QwenBackend] Unknown language '{language}', falling back to 'English'.")
            language = "English"

        # Cross-check with the model's own runtime-reported lists, when available.
        try:
            supported_speakers = self.model.get_supported_speakers()
            if supported_speakers and speaker not in supported_speakers:
                print(f"[QwenBackend] Speaker '{speaker}' not in model list {supported_speakers}; using first available.")
                speaker = supported_speakers[0]
        except Exception:
            pass
        try:
            supported_langs = self.model.get_supported_languages()
            if supported_langs and language not in supported_langs:
                print(f"[QwenBackend] Language '{language}' not in model list {supported_langs}; using 'English'.")
                language = "English" if "English" in supported_langs else supported_langs[0]
        except Exception:
            pass

        print(f"[QwenBackend] generate(language={language!r}, speaker={speaker!r}, chars={len(text)})")

        chunks = self._chunk_text(text)
        chunks = TextProcessor.split_for_tts(text)
        n = len(chunks)
        all_wavs: list[np.ndarray] = []

        for i, chunk in enumerate(chunks):
            if progress_cb:
                progress_cb(f"Chunk {i + 1}/{n}...", int(i / n * 90))
            wavs, sr = self.model.generate_custom_voice(
                text=chunk,
                language=language,
                speaker=speaker,
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

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None):
        try:
            import edge_tts
        except ImportError as exc:
            raise ImportError("edge-tts not installed. Run: pip install edge-tts") from exc

        voice = self._resolve_voice(language=language, speaker=speaker)
        if progress_cb:
            progress_cb(f"Synthesizing with Edge-TTS ({voice})...", 40)

        async def _run():
            tmp_mp3 = f"{output_path}.edge.mp3"
            try:
                comm = edge_tts.Communicate(TextProcessor.normalize(text), voice=voice)
                await comm.save(tmp_mp3)
                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-i", tmp_mp3,
                    "-ac", "1", "-ar", "24000", output_path,
                ]
                subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            finally:
                if os.path.exists(tmp_mp3):
                    os.remove(tmp_mp3)

        try:
            asyncio.run(_run())
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg is required for Edge-TTS WAV conversion. Install ffmpeg or use another backend.") from exc
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

        model_path = os.getenv("PIPER_MODEL") or (
            PIPER_DEFAULT_MODEL if os.path.exists(PIPER_DEFAULT_MODEL) else None
        )
        if not model_path:
            raise RuntimeError(
                "PIPER_MODEL environment variable not set. Point it to a Piper .onnx "
                "voice model, e.g. export PIPER_MODEL=/path/to/voice.onnx, "
                "or run: python scripts/ensure_models.py --piper"
            )
        if not os.path.exists(model_path):
            raise RuntimeError(f"PIPER_MODEL file does not exist: {model_path}")
        config_path = os.getenv("PIPER_CONFIG")
        if not config_path:
            candidate = f"{model_path}.json"
            if os.path.exists(candidate):
                config_path = candidate
        self.model_path = model_path
        self.config_path = config_path
        self.use_cuda = _is_cuda_device(device)
        if self.use_cuda:
            try:
                import onnxruntime as ort
                providers = set(ort.get_available_providers())
            except Exception as exc:
                raise RuntimeError(
                    "Piper CUDA was requested, but onnxruntime is not available. "
                    "Install onnxruntime-gpu or select device=cpu."
                ) from exc
            if "CUDAExecutionProvider" not in providers:
                raise RuntimeError(
                    "Piper CUDA was requested, but ONNX Runtime does not expose "
                    "CUDAExecutionProvider. Install/configure onnxruntime-gpu, CUDA, "
                    "and the NVIDIA driver, or select device=cpu."
                )
        self._loaded = True
        if progress_cb:
            progress_cb("Model ready.", 100)

    def is_loaded(self) -> bool:
        return self._loaded

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None):
        if progress_cb:
            progress_cb("Generating...", 40)
        cmd = list(self._invoke) + ["-m", self.model_path, "-f", output_path]
        if self.config_path:
            cmd += ["-c", self.config_path]
        if self.use_cuda:
            cmd += ["--cuda"]
        extra_args = os.getenv("PIPER_ARGS", "").strip()
        if extra_args:
            cmd += shlex.split(extra_args)

        try:
            subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            raise RuntimeError(f"Piper failed: {stderr.strip() or exc}") from exc

        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, 0


class CoquiBackend(BaseBackend):
    name = "coqui"

    def __init__(self):
        self.tts = None

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
        model_name = os.getenv("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")
        _require_torch_cuda(device, "Coqui")
        use_cuda = _is_cuda_device(device)
        self.tts = CoquiTTS(model_name=model_name, gpu=use_cuda)
        if progress_cb:
            progress_cb("Model ready.", 100)

    def is_loaded(self) -> bool:
        return self.tts is not None

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None):
        if progress_cb:
            progress_cb("Generating...", 40)
        kwargs = {}
        if hasattr(self.tts, "speakers") and speaker in (self.tts.speakers or []):
            kwargs["speaker"] = speaker
        if hasattr(self.tts, "languages") and language in (self.tts.languages or []):
            kwargs["language"] = language
        self.tts.tts_to_file(text=text, file_path=output_path, **kwargs)
        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, 0


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
            )

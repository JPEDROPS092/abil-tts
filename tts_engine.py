"""
Core TTS engine – multi-backend wrapper (Qwen, Piper, Coqui).
Handles model loading, text chunking, and audio generation.
"""
import os
import shlex
import subprocess
import threading
import asyncio

import numpy as np
import soundfile as sf
import torch

from text_processor import TextProcessor

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"

SPEAKERS = [
    "Ryan", "Alice", "Bob", "Charlie", "Diana",
    "Ethan", "Fiona", "George", "Hannah", "Ivan",
    "Julia", "Kevin", "Laura", "Mike", "Nina",
    "Oscar", "Penny", "Quinn", "Rachel", "Sam",
]

LANGUAGES = [
    "English", "Chinese", "Japanese", "Korean",
    "French", "German", "Spanish", "Portuguese",
    "Italian", "Russian", "Arabic", "Hindi",
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
        from qwen_tts import Qwen3TTSModel
        if progress_cb:
            progress_cb("Loading model...", 0)
        dtype = torch.bfloat16 if "cuda" in device else torch.float32
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

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        if progress_cb:
            progress_cb("Loading model...", 0)
        model_path = os.getenv("PIPER_MODEL")
        if not model_path:
            raise ValueError("PIPER_MODEL is not set. Provide a Piper .onnx model path.")
        config_path = os.getenv("PIPER_CONFIG")
        if not config_path:
            candidate = f"{model_path}.json"
            if os.path.exists(candidate):
                config_path = candidate
        self.model_path = model_path
        self.config_path = config_path
        self.use_cuda = device.startswith("cuda")
        self._loaded = True
        if progress_cb:
            progress_cb("Model ready.", 100)

    def is_loaded(self) -> bool:
        return self._loaded

    def generate(self, text: str, language: str, speaker: str, output_path: str, progress_cb=None):
        if progress_cb:
            progress_cb("Generating...", 40)
        cmd = ["piper", "--model", self.model_path, "--output_file", output_path]
        if self.config_path:
            cmd += ["--config", self.config_path]
        if self.use_cuda:
            cmd += ["--use_cuda"]
        extra_args = os.getenv("PIPER_ARGS", "").strip()
        if extra_args:
            cmd += shlex.split(extra_args)
        subprocess.run(cmd, input=text.encode("utf-8"), check=True)
        if progress_cb:
            progress_cb("Done.", 100)
        return output_path, 0


class CoquiBackend(BaseBackend):
    name = "coqui"

    def __init__(self):
        self.tts = None

    def load_model(self, device: str = "cuda:0", progress_cb=None):
        from TTS.api import TTS as CoquiTTS
        if progress_cb:
            progress_cb("Loading model...", 0)
        model_name = os.getenv("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")
        use_cuda = device.startswith("cuda")
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
    ) -> tuple[str, int]:
        """Generate speech and write to *output_path*.

        *progress_cb(message, pct)* is called with status updates.
        Returns *(output_path, sample_rate)*.
        """
        name = self._normalize_backend(backend)
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

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from document_pipeline import (
    DocumentBlock,
    ProcessedDocument,
    process_document,
    render_document,
    translate_document,
    tts_text,
)
from storage import StudioStore
from llm_client import MAAS_BASE_URL, get_llm_client, update_llm_client
from model_registry import list_text_models
from text_diagram import build_mermaid_flowchart
from tts_engine import (
    BACKEND_LANGUAGES,
    BACKEND_VOICES,
    BACKENDS,
    COQUI_DEFAULT_MODEL,
    COQUI_MODELS,
    DEFAULT_BACKEND,
    DEFAULT_DEVICE,
    EDGE_VOICES,
    LANGUAGES,
    SPEAKERS,
    TTSEngine,
    terminate_all_processes,
)


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "outputs"
STATIC_DIR = PROJECT_DIR / "static"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
store = StudioStore(PROJECT_DIR / "data" / "abil-studio.db")

app = FastAPI(title="Abil TTS API")
engine = TTSEngine.get_instance()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("shutdown")
def _shutdown_cleanup() -> None:
    """Kill any backend subprocess still running when the server stops."""
    with jobs_lock:
        for job in jobs.values():
            if job.get("status") in ("queued", "processing"):
                job["cancel_requested"] = True
    terminate_all_processes()


class LoadRequest(BaseModel):
    backend: str = DEFAULT_BACKEND
    device: str = DEFAULT_DEVICE


class NormalizeRequest(BaseModel):
    text: str = ""
    language: str = "Portuguese"


class GenerateRequest(BaseModel):
    text: str
    document_id: str | None = None
    backend: str = DEFAULT_BACKEND
    device: str = DEFAULT_DEVICE
    language: str = "Portuguese"
    speaker: str = "Ryan"
    normalize_text: bool = True
    review_before_tts: bool = False
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


class DiagramRequest(BaseModel):
    text: str = ""
    selected_text: str = ""
    scope: str = "auto"
    title: str = "Text Flow"
    max_nodes: int = Field(default=12, ge=3, le=24)


class SayRequest(BaseModel):
    text: str
    language: str | None = None
    speaker: str | None = None
    backend: str | None = None
    device: str | None = None
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    normalize_text: bool | None = None


class DocumentUpdateRequest(BaseModel):
    display_name: str = ""
    description: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class ListeningRequest(BaseModel):
    document_id: str
    source_name: str = ""
    display_name: str = ""
    block_idx: int = Field(default=0, ge=0)
    snippet: str = ""


class BlockPayload(BaseModel):
    type: str = "paragraph"
    text: str = ""
    level: int = Field(default=0, ge=0, le=6)
    exclude: bool = False


class BlocksUpdateRequest(BaseModel):
    blocks: list[BlockPayload] = Field(min_length=0)


BLOCK_TYPES = {"heading", "paragraph", "equation", "code", "table", "list", "reference"}


class RuntimeSettings(BaseModel):
    backend: str = DEFAULT_BACKEND
    device: str = DEFAULT_DEVICE
    speaker: str = "Ryan"
    language: str = "Portuguese"
    normalize_text: bool = True
    diagram_scope: str = "auto"
    diagram_title: str = "Text Flow"
    qwen_model_id: str = Field(default_factory=lambda: os.getenv("QWEN_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"))
    piper_model: str = Field(default_factory=lambda: os.getenv("PIPER_MODEL", ""))
    piper_config: str = Field(default_factory=lambda: os.getenv("PIPER_CONFIG", ""))
    piper_args: str = Field(default_factory=lambda: os.getenv("PIPER_ARGS", ""))
    coqui_model: str = Field(default_factory=lambda: os.getenv("COQUI_MODEL", COQUI_DEFAULT_MODEL))
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))


class LLMConfig(BaseModel):
    api_key: str = Field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = Field(default_factory=lambda: os.getenv("LLM_BASE_URL", MAAS_BASE_URL))
    model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "qwen3.6-flash"))


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
    document_context: str = ""


class LLMTextRequest(BaseModel):
    text: str
    language: str = ""


class TranslateRequest(LLMTextRequest):
    target_language: str = "Portuguese (Brazil)"


settings_lock = threading.Lock()
runtime_settings = RuntimeSettings()

llm_config_lock = threading.Lock()
llm_config = LLMConfig()

backend_state_lock = threading.Lock()
backend_state: dict[str, dict[str, str]] = {}

jobs_lock = threading.Lock()
jobs: dict[str, dict[str, Any]] = {}

say_lock = threading.Lock()


def _dump_model(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key != "file_path"}


def _validate_backend(backend: str) -> str:
    name = (backend or DEFAULT_BACKEND).strip().lower()
    if name not in BACKENDS:
        raise HTTPException(status_code=400, detail=f"Unsupported backend '{name}'")
    return name


def _validate_device(device: str) -> str:
    value = (device or DEFAULT_DEVICE).strip()
    if value not in {"cuda:0", "cuda:1", "cpu"}:
        raise HTTPException(status_code=400, detail=f"Unsupported device '{value}'")
    return value


def _apply_runtime_settings(settings: RuntimeSettings) -> None:
    mapping = {
        "qwen_model_id": "QWEN_MODEL_ID",
        "piper_model": "PIPER_MODEL",
        "piper_config": "PIPER_CONFIG",
        "piper_args": "PIPER_ARGS",
        "coqui_model": "COQUI_MODEL",
        "gemini_api_key": "GEMINI_API_KEY",
    }
    data = _dump_model(settings)
    for setting_key, env_key in mapping.items():
        value = str(data.get(setting_key) or "").strip()
        if value:
            os.environ[env_key] = value
        else:
            os.environ.pop(env_key, None)


def _set_backend_state(backend: str, status: str, message: str = "") -> None:
    with backend_state_lock:
        backend_state[backend] = {"status": status, "message": message}


def _get_backend_state(backend: str) -> dict[str, str]:
    with backend_state_lock:
        return dict(backend_state.get(backend, {"status": "idle", "message": ""}))


def _load_backend_bg(backend: str, device: str) -> None:
    _set_backend_state(backend, "loading", "Loading model")
    try:
        with settings_lock:
            _apply_runtime_settings(runtime_settings)
        engine.load_model(backend=backend, device=device)
        _set_backend_state(backend, "ready", "Model ready")
    except Exception as exc:
        _set_backend_state(backend, "error", str(exc))


def _update_job(task_id: str, **fields: Any) -> None:
    with jobs_lock:
        job = jobs.get(task_id) or store.get_job(task_id)
        if job:
            job.update(fields)
            jobs[task_id] = job
            store.save_job(job)


def _get_job(task_id: str) -> dict[str, Any] | None:
    with jobs_lock:
        job = jobs.get(task_id) or store.get_job(task_id)
        return dict(job) if job else None


def _bg_generate(
    task_id: str,
    text: str,
    language: str,
    speaker: str,
    backend: str,
    device: str,
    normalize_text: bool,
    speed: float = 1.0,
    review_before_tts: bool = False,
) -> None:
    output_path = OUTPUT_DIR / f"{task_id}.wav"

    def should_cancel() -> bool:
        job = _get_job(task_id)
        return bool(job and job.get("cancel_requested"))

    def progress(message: str, pct: int | None = None) -> None:
        job = _get_job(task_id)
        if job and job.get("cancel_requested"):
            raise RuntimeError("Job cancelled")
        fields: dict[str, Any] = {"message": message}
        if pct is not None:
            fields["progress"] = pct
        # Parse "Chunk X/N" messages to update chunk tracking
        if message.startswith("Chunk "):
            try:
                parts = message.split("/")
                current = int(parts[0].split()[-1])
                total = int(parts[1].split(".")[0].strip())
                fields["current_chunk"] = current
                fields["total_chunks"] = total
            except (ValueError, IndexError):
                pass
        _update_job(task_id, **fields)

    try:
        job = _get_job(task_id)
        if job and job.get("cancel_requested"):
            _update_job(task_id, status="cancelled", message="Cancelled", progress=0)
            return

        _update_job(task_id, status="processing", message="Starting", progress=0)
        with settings_lock:
            _apply_runtime_settings(runtime_settings)

        # Optionally review/format text with LLM before synthesis
        if review_before_tts:
            try:
                _update_job(task_id, message="Revisando texto com LLM...", progress=2)
                client = get_llm_client()
                text = client.review_text(text)
                _update_job(task_id, message="Texto revisado.", progress=5)
            except Exception as llm_exc:
                print(f"[api] LLM review skipped: {llm_exc}")

        engine.generate(
            text=text,
            language=language,
            speaker=speaker,
            output_path=str(output_path),
            backend=backend,
            device=device,
            progress_cb=progress,
            normalize_text=normalize_text,
            speed=speed,
            should_cancel=should_cancel,
        )

        job = _get_job(task_id)
        if job and job.get("cancel_requested"):
            _update_job(task_id, status="cancelled", message="Cancelled")
            return
        _update_job(
            task_id,
            status="done",
            message="Done",
            progress=100,
            file_path=str(output_path),
        )
    except Exception as exc:
        if str(exc) == "Job cancelled":
            _update_job(task_id, status="cancelled", message="Cancelled")
        else:
            _update_job(task_id, status="error", message=str(exc), error=str(exc))


@app.get("/api/meta")
def api_meta() -> dict[str, Any]:
    return {
        "backends": [{"id": key, "label": BACKENDS[key]} for key in BACKENDS],
        "default_backend": DEFAULT_BACKEND,
        "default_device": DEFAULT_DEVICE,
        "speakers": SPEAKERS,
        "edge_voices": EDGE_VOICES,
        "voices": BACKEND_VOICES,
        "backend_languages": BACKEND_LANGUAGES,
        "coqui_models": [{"id": key, "label": label} for key, label in COQUI_MODELS.items()],
        "languages": LANGUAGES,
    }


@app.get("/api/settings")
def api_get_settings() -> dict[str, Any]:
    with settings_lock:
        return _dump_model(runtime_settings)


@app.put("/api/settings")
def api_put_settings(settings: RuntimeSettings) -> dict[str, Any]:
    global runtime_settings
    settings.backend = _validate_backend(settings.backend)
    settings.device = _validate_device(settings.device)
    with settings_lock:
        runtime_settings = settings
        _apply_runtime_settings(runtime_settings)
        return _dump_model(runtime_settings)


@app.get("/api/status")
def api_status(backend: str = DEFAULT_BACKEND) -> dict[str, Any]:
    name = _validate_backend(backend)
    state = _get_backend_state(name)
    ready = engine.is_loaded(backend=name)
    if ready and state["status"] != "ready":
        _set_backend_state(name, "ready", "Model ready")
        state = _get_backend_state(name)
    return {
        "model_ready": ready,
        "status": state["status"],
        "message": state["message"],
    }


@app.post("/api/load")
def api_load(payload: LoadRequest) -> dict[str, str]:
    backend = _validate_backend(payload.backend)
    device = _validate_device(payload.device)
    if engine.is_loaded(backend=backend):
        _set_backend_state(backend, "ready", "Model ready")
        return {"status": "ready"}
    state = _get_backend_state(backend)
    if state["status"] == "loading":
        return {"status": "loading"}
    threading.Thread(target=_load_backend_bg, args=(backend, device), daemon=True).start()
    return {"status": "loading"}


@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...),
    name: str = Form(""),
    description: str = Form(""),
    metadata: str = Form(""),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    meta: dict[str, Any] = {}
    if metadata.strip():
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                meta = parsed
        except ValueError:
            meta = {"raw": metadata}
    tmp_path = OUTPUT_DIR / f"upload_{uuid.uuid4().hex}_{Path(file.filename).name}"
    try:
        with tmp_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        document = process_document(
            str(tmp_path),
            display_name=name.strip(),
            description=description.strip(),
            meta=meta,
        )
        document_id = uuid.uuid4().hex
        store.save_document(document_id, document)
        return {
            "document_id": document_id,
            "text": render_document(document),
            "parser": document.parser,
            "blocks": [{**block.to_dict(), "tts": tts_text(block)} for block in document.blocks],
            "display_name": document.display_name,
            "description": document.description,
            "meta": document.meta or {},
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        await file.close()


@app.get("/api/documents/{document_id}/variant")
def api_document_variant(document_id: str, mode: str = "document", language: str = "Portuguese") -> dict[str, str]:
    if mode not in {"document", "tts"}:
        raise HTTPException(status_code=400, detail="Unsupported document mode")
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    text = render_document(document, mode=mode)
    if mode == "tts":
        from text_normalizer import normalize
        text = normalize(text, language=language)
    return {"text": text, "mode": mode}


@app.post("/api/documents/{document_id}/translate")
def api_translate_document(document_id: str, payload: TranslateRequest) -> dict[str, Any]:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        translated = translate_document(
            document,
            payload.target_language,
            get_llm_client().translate,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    store.save_document(document_id, translated)
    return {
        "text": render_document(translated),
        "blocks": [block.to_dict() for block in translated.blocks],
    }


@app.get("/api/documents")
def api_documents(limit: int = 100) -> dict[str, Any]:
    return {"documents": store.list_documents(max(1, min(limit, 200)))}


@app.get("/api/documents/{document_id}")
def api_document(document_id: str) -> dict[str, Any]:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document_id": document_id, "text": render_document(document), "parser": document.parser,
            "blocks": [{**block.to_dict(), "tts": tts_text(block)} for block in document.blocks],
            "display_name": document.display_name, "description": document.description,
            "meta": document.meta or {}}


@app.put("/api/documents/{document_id}")
def api_update_document(document_id: str, payload: DocumentUpdateRequest) -> dict[str, Any]:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    updated = store.update_document_metadata(
        document_id,
        display_name=payload.display_name.strip(),
        description=payload.description.strip(),
        meta=payload.meta,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Could not update document")
    return api_document(document_id)


@app.delete("/api/documents/{document_id}")
def api_delete_document(document_id: str) -> dict[str, bool]:
    if store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    store.delete_document(document_id)
    return {"ok": True}


@app.put("/api/documents/{document_id}/blocks")
def api_update_document_blocks(document_id: str, payload: BlocksUpdateRequest) -> dict[str, Any]:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    for block in payload.blocks:
        if block.type not in BLOCK_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported block type '{block.type}'")
        if not block.text.strip():
            raise HTTPException(status_code=400, detail="Blocks must have text")
    rebuilt = ProcessedDocument(
        source_name=document.source_name,
        parser=document.parser,
        blocks=[DocumentBlock(**block.model_dump()) for block in payload.blocks],
        display_name=document.display_name,
        description=document.description,
        meta=document.meta,
    )
    store.save_document(document_id, rebuilt)
    return api_document(document_id)


@app.post("/api/listening")
def api_record_listening(payload: ListeningRequest) -> dict[str, bool]:
    store.record_listening(payload.model_dump())
    return {"ok": True}


@app.get("/api/listening")
def api_list_listening(limit: int = 60) -> dict[str, Any]:
    return {"history": store.list_listening(max(1, min(limit, 200)))}


@app.delete("/api/listening")
def api_clear_listening() -> dict[str, bool]:
    store.clear_listening()
    return {"ok": True}


@app.post("/api/normalize")
def api_normalize(payload: NormalizeRequest) -> dict[str, str]:
    try:
        from text_normalizer import normalize

        return {"text": normalize(payload.text, language=payload.language)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/tts/say")
def api_tts_say(payload: SayRequest):
    """Synchronous short-text synthesis for the document player (returns WAV bytes)."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    with settings_lock:
        settings = runtime_settings
    backend = _validate_backend(payload.backend or settings.backend)
    device = _validate_device(payload.device or settings.device)
    language = payload.language or settings.language
    speaker = payload.speaker or settings.speaker
    normalize = settings.normalize_text if payload.normalize_text is None else payload.normalize_text
    output_path = OUTPUT_DIR / f"say_{uuid.uuid4().hex}.wav"
    try:
        with say_lock:
            engine.generate(
                text=text,
                language=language,
                speaker=speaker,
                output_path=str(output_path),
                backend=backend,
                device=device,
                normalize_text=normalize,
                speed=payload.speed,
            )
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Synthesis produced no audio")
    return FileResponse(
        output_path,
        media_type="audio/wav",
        background=BackgroundTask(output_path.unlink),
    )


@app.post("/api/generate")
def api_generate(payload: GenerateRequest) -> dict[str, Any]:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    backend = _validate_backend(payload.backend)
    device = _validate_device(payload.device)
    task_id = uuid.uuid4().hex
    job = {
        "id": task_id,
        "status": "queued",
        "message": "Queued",
        "progress": 0,
        "backend": backend,
        "device": device,
        "language": payload.language,
        "speaker": payload.speaker,
        "normalize_text": payload.normalize_text,
        "document_id": payload.document_id,
        "input_chars": len(text),
        "input_words": len(text.split()),
        "current_chunk": 0,
        "total_chunks": 0,
        "file_path": None,
        "error": None,
        "cancel_requested": False,
    }
    with jobs_lock:
        jobs[task_id] = job
    store.save_job(job)
    threading.Thread(
        target=_bg_generate,
        args=(
            task_id,
            text,
            payload.language,
            payload.speaker,
            backend,
            device,
            payload.normalize_text,
            payload.speed,
            payload.review_before_tts,
        ),
        daemon=True,
    ).start()
    return {"task_id": task_id, "job": _public_job(job)}


@app.post("/api/diagram")
def api_diagram(payload: DiagramRequest) -> dict[str, str]:
    mode = payload.scope.strip().lower()
    if mode == "selection":
        text = payload.selected_text.strip()
    elif mode == "full":
        text = payload.text.strip()
    else:
        text = payload.selected_text.strip() or payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided for diagram generation")
    mermaid = build_mermaid_flowchart(
        text=text,
        title=payload.title.strip()[:120] or "Text Flow",
        max_nodes=payload.max_nodes,
    )
    return {"mermaid": mermaid}


@app.get("/api/task/{task_id}")
def api_task(task_id: str) -> dict[str, Any]:
    job = _get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    return _public_job(job)


@app.get("/api/jobs")
def api_jobs(limit: int = 50) -> dict[str, list[dict[str, Any]]]:
    limit = max(1, min(limit, 200))
    return {"jobs": [_public_job(job) for job in store.list_jobs(limit)]}


@app.post("/api/jobs/{task_id}/cancel")
def api_cancel_job(task_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(task_id)
        if not job:
            raise HTTPException(status_code=404, detail="Task not found")
        job["cancel_requested"] = True
        if job["status"] == "queued":
            job["status"] = "cancelled"
            job["message"] = "Cancelled"
    return _public_job(_get_job(task_id) or {})


@app.delete("/api/jobs/{task_id}")
def api_delete_job(task_id: str) -> dict[str, bool]:
    with jobs_lock:
        job = jobs.pop(task_id, None) or store.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    file_path = job.get("file_path")
    if file_path:
        for path in (Path(file_path), Path(file_path).with_suffix(".mp3")):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
    store.delete_job(task_id)
    return {"deleted": True}


@app.get("/api/audio/{task_id}")
def api_audio(task_id: str, fmt: str = "wav") -> FileResponse:
    job = _get_job(task_id)
    if not job or job.get("status") != "done" or not job.get("file_path"):
        raise HTTPException(status_code=404, detail="Audio not ready")

    wav_path = Path(job["file_path"])
    fmt = (fmt or "wav").strip().lower()
    if fmt == "wav":
        return FileResponse(
            str(wav_path),
            media_type="audio/wav",
            filename=f"abil-{task_id}.wav",
        )
    if fmt == "mp3":
        mp3_path = wav_path.with_suffix(".mp3")
        # Convert once and cache; regenerate if the wav is newer.
        if not mp3_path.exists() or mp3_path.stat().st_mtime < wav_path.stat().st_mtime:
            if not shutil.which("ffmpeg"):
                raise HTTPException(status_code=500, detail="ffmpeg is required to export MP3")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
                     "-qscale:a", "2", str(mp3_path)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                )
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
                raise HTTPException(status_code=500, detail=f"MP3 conversion failed: {stderr.strip() or exc}") from exc
        return FileResponse(
            str(mp3_path),
            media_type="audio/mpeg",
            filename=f"abil-{task_id}.mp3",
        )
    raise HTTPException(status_code=400, detail=f"Unsupported format '{fmt}'")


# ---------------------------------------------------------------------------
# LLM endpoints
# ---------------------------------------------------------------------------

@app.get("/api/llm/models")
def api_llm_models() -> dict[str, Any]:
    return {"models": [m.to_dict() for m in list_text_models()]}


@app.get("/api/llm/config")
def api_get_llm_config() -> dict[str, Any]:
    with llm_config_lock:
        return _dump_model(llm_config)


@app.put("/api/llm/config")
def api_put_llm_config(payload: LLMConfig) -> dict[str, Any]:
    global llm_config
    with llm_config_lock:
        llm_config = payload
    update_llm_client(
        api_key=payload.api_key,
        base_url=payload.base_url,
        model=payload.model,
    )
    return _dump_model(llm_config)


@app.post("/api/llm/test")
def api_llm_test() -> dict[str, Any]:
    try:
        client = get_llm_client()
        ok = client.test_connection()
        return {"success": ok, "message": "Conexao OK" if ok else "Falha na conexao"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


@app.post("/api/llm/review")
def api_llm_review(payload: LLMTextRequest) -> dict[str, str]:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    try:
        client = get_llm_client()
        result = client.review_text(payload.text)
        return {"text": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/llm/summarize")
def api_llm_summarize(payload: LLMTextRequest) -> dict[str, str]:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    try:
        client = get_llm_client()
        result = client.summarize(payload.text)
        return {"text": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/llm/explain")
def api_llm_explain(payload: LLMTextRequest) -> dict[str, str]:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    try:
        client = get_llm_client()
        result = client.explain(payload.text)
        return {"text": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/llm/translate")
def api_llm_translate(payload: TranslateRequest) -> dict[str, str]:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    try:
        client = get_llm_client()
        return {"text": client.translate(payload.text, payload.target_language)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/llm/chat")
def api_llm_chat(payload: ChatRequest) -> StreamingResponse:
    if not payload.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    def _event_stream():
        try:
            client = get_llm_client()
            for chunk in client.chat_stream(
                messages=payload.messages,
                document_context=payload.document_context or None,
            ):
                # SSE format
                data = json.dumps({"content": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as exc:
            error_data = json.dumps({"error": str(exc)})
            yield f"data: {error_data}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/audio")
def api_chat_audio(payload: ChatRequest) -> dict[str, Any]:
    """Generate a complete LLM response and queue it for TTS."""
    if not payload.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    try:
        client = get_llm_client()
        full_response = "".join(
            client.chat_stream(
                messages=payload.messages,
                document_context=payload.document_context or None,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM error: {exc}") from exc

    if not full_response.strip():
        raise HTTPException(status_code=500, detail="LLM returned empty response")

    with settings_lock:
        s = runtime_settings

    task_id = uuid.uuid4().hex
    job: dict[str, Any] = {
        "id": task_id,
        "status": "queued",
        "message": "Queued (chat audio)",
        "progress": 0,
        "backend": s.backend,
        "device": s.device,
        "language": s.language,
        "speaker": s.speaker,
        "normalize_text": s.normalize_text,
        "input_chars": len(full_response),
        "input_words": len(full_response.split()),
        "current_chunk": 0,
        "total_chunks": 0,
        "file_path": None,
        "error": None,
        "cancel_requested": False,
        "llm_text": full_response,
    }
    with jobs_lock:
        jobs[task_id] = job
    store.save_job(job)

    threading.Thread(
        target=_bg_generate,
        args=(task_id, full_response, s.language, s.speaker, s.backend, s.device, s.normalize_text),
        daemon=True,
    ).start()
    return {"task_id": task_id, "job": _public_job(job), "llm_text": full_response}


# ---------------------------------------------------------------------------
# Static / SPA routes
# ---------------------------------------------------------------------------

@app.get("/favicon.ico")
def favicon() -> FileResponse:
    icon = STATIC_DIR / "abil.png"
    if not icon.exists():
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(icon, media_type="image/png")


@app.get("/{path:path}", response_model=None)
def serve_vue(path: str) -> FileResponse | JSONResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    requested = FRONTEND_DIST / path
    if path and requested.exists() and requested.is_file():
        return FileResponse(requested)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {
            "message": "Abil TTS API is running. Build the Vue app with `cd frontend && npm run build` to serve the UI.",
        }
    )

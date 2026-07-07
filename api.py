from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from document_reader import read_document
from llm_client import MAAS_BASE_URL, get_llm_client, update_llm_client
from model_registry import list_text_models
from text_diagram import build_mermaid_flowchart
from tts_engine import (
    BACKENDS,
    DEFAULT_BACKEND,
    DEFAULT_DEVICE,
    EDGE_VOICES,
    LANGUAGES,
    SPEAKERS,
    TTSEngine,
)


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "outputs"
STATIC_DIR = PROJECT_DIR / "static"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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


class LoadRequest(BaseModel):
    backend: str = DEFAULT_BACKEND
    device: str = DEFAULT_DEVICE


class NormalizeRequest(BaseModel):
    text: str = ""
    language: str = "English"


class GenerateRequest(BaseModel):
    text: str
    backend: str = DEFAULT_BACKEND
    device: str = DEFAULT_DEVICE
    language: str = "English"
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


class RuntimeSettings(BaseModel):
    backend: str = DEFAULT_BACKEND
    device: str = DEFAULT_DEVICE
    speaker: str = "Ryan"
    language: str = "English"
    normalize_text: bool = True
    diagram_scope: str = "auto"
    diagram_title: str = "Text Flow"
    qwen_model_id: str = Field(default_factory=lambda: os.getenv("QWEN_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"))
    piper_model: str = Field(default_factory=lambda: os.getenv("PIPER_MODEL", ""))
    piper_config: str = Field(default_factory=lambda: os.getenv("PIPER_CONFIG", ""))
    piper_args: str = Field(default_factory=lambda: os.getenv("PIPER_ARGS", ""))
    coqui_model: str = Field(default_factory=lambda: os.getenv("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC"))
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


settings_lock = threading.Lock()
runtime_settings = RuntimeSettings()

llm_config_lock = threading.Lock()
llm_config = LLMConfig()

backend_state_lock = threading.Lock()
backend_state: dict[str, dict[str, str]] = {}

jobs_lock = threading.Lock()
jobs: dict[str, dict[str, Any]] = {}


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
        job = jobs.get(task_id)
        if job:
            job.update(fields)


def _get_job(task_id: str) -> dict[str, Any] | None:
    with jobs_lock:
        job = jobs.get(task_id)
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
async def api_upload(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    tmp_path = OUTPUT_DIR / f"upload_{uuid.uuid4().hex}_{Path(file.filename).name}"
    try:
        with tmp_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        text = read_document(str(tmp_path))
        return {"text": text}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        await file.close()


@app.post("/api/normalize")
def api_normalize(payload: NormalizeRequest) -> dict[str, str]:
    try:
        from text_normalizer import normalize

        return {"text": normalize(payload.text, language=payload.language)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    with jobs_lock:
        items = list(jobs.values())[-limit:]
    items.reverse()
    return {"jobs": [_public_job(job) for job in items]}


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
        job = jobs.pop(task_id, None)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    file_path = job.get("file_path")
    if file_path and Path(file_path).exists():
        try:
            Path(file_path).unlink()
        except OSError:
            pass
    return {"deleted": True}


@app.get("/api/audio/{task_id}")
def api_audio(task_id: str) -> FileResponse:
    job = _get_job(task_id)
    if not job or job.get("status") != "done" or not job.get("file_path"):
        raise HTTPException(status_code=404, detail="Audio not ready")
    return FileResponse(
        job["file_path"],
        media_type="audio/wav",
        filename=f"abil-{task_id}.wav",
    )


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

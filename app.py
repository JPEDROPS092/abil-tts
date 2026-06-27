"""
Qween TTS – Flask web server.
Run: python app.py
Then open http://localhost:5050
"""
import os
import threading
import uuid

from flask import Flask, jsonify, render_template, request, send_file

from document_reader import read_document
from text_diagram import build_mermaid_flowchart
from tts_engine import BACKENDS, DEFAULT_BACKEND, DEFAULT_DEVICE, EDGE_VOICES, LANGUAGES, SPEAKERS, TTSEngine

app = Flask(__name__)
engine = TTSEngine.get_instance()

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# task registry  {task_id: {status, message, progress, file}}
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()
_loading_backends: set[tuple[str, str]] = set()
_loading_lock = threading.Lock()


# ── Background worker ─────────────────────────────────────────────────────────

def _bg_generate(task_id: str, text: str, language: str, speaker: str, backend: str, device: str):
    out = os.path.join(OUTPUT_DIR, f"{task_id}.wav")

    def cb(msg: str, pct: int | None = None):
        with _tasks_lock:
            _tasks[task_id]["message"] = msg
            if pct is not None:
                _tasks[task_id]["progress"] = pct

    try:
        engine.generate(
            text=text,
            language=language,
            speaker=speaker,
            output_path=out,
            backend=backend,
            device=device,
            progress_cb=cb,
        )
        with _tasks_lock:
            _tasks[task_id].update(status="done", file=out, progress=100,
                                   message="Done.")
    except Exception as exc:
        with _tasks_lock:
            _tasks[task_id].update(status="error", message=str(exc))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        speakers=SPEAKERS,
        edge_voices=EDGE_VOICES,
        languages=LANGUAGES,
        backends=engine.list_backends(),
        default_backend=DEFAULT_BACKEND,
        default_device=DEFAULT_DEVICE,
    )


@app.route("/api/status")
def api_status():
    backend = (request.args.get("backend") or DEFAULT_BACKEND).strip().lower()
    device = (request.args.get("device") or DEFAULT_DEVICE).strip()
    ready = engine.is_loaded(backend=backend)
    if not ready:
        key = (backend, device)
        with _loading_lock:
            if key not in _loading_backends:
                _loading_backends.add(key)

                def _load():
                    try:
                        engine.load_model(backend=backend, device=device)
                    finally:
                        with _loading_lock:
                            _loading_backends.discard(key)

                threading.Thread(target=_load, daemon=True).start()
    return jsonify({"model_ready": ready})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file provided"}), 400

    tmp = os.path.join(OUTPUT_DIR, f"upload_{uuid.uuid4().hex}_{f.filename}")
    f.save(tmp)
    try:
        text = read_document(tmp)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    return jsonify({"text": text})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    backend = (data.get("backend") or DEFAULT_BACKEND).strip().lower()
    if backend not in BACKENDS:
        return jsonify({"error": f"Unsupported backend '{backend}'"}), 400
    device = (data.get("device") or DEFAULT_DEVICE).strip()

    task_id = uuid.uuid4().hex
    with _tasks_lock:
        _tasks[task_id] = {
            "status": "processing",
            "message": "Starting…",
            "progress": 0,
            "file": None,
        }

    threading.Thread(
        target=_bg_generate,
        args=(
            task_id,
            text,
            data.get("language", "English"),
            data.get("speaker", "Ryan"),
            backend,
            device,
        ),
        daemon=True,
    ).start()

    return jsonify({"task_id": task_id})


@app.route("/api/diagram", methods=["POST"])
def api_diagram():
    data = request.get_json(force=True) or {}
    source_text = (data.get("text") or "").strip()
    selected_text = (data.get("selected_text") or "").strip()
    mode = (data.get("scope") or "auto").strip().lower()
    if mode == "selection":
        text = selected_text
    elif mode == "full":
        text = source_text
    else:
        text = selected_text or source_text

    if not text:
        return jsonify({"error": "No text provided for diagram generation"}), 400

    title = (data.get("title") or "Text Flow").strip()[:120]
    max_nodes = int(data.get("max_nodes") or 12)
    max_nodes = min(max(max_nodes, 3), 24)
    mermaid = build_mermaid_flowchart(text=text, title=title, max_nodes=max_nodes)
    return jsonify({"mermaid": mermaid})


@app.route("/api/task/<task_id>")
def api_task(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 404
    # Don't expose internal file path to client
    return jsonify({k: v for k, v in task.items() if k != "file"})


@app.route("/api/audio/<task_id>")
def api_audio(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if task is None or task.get("status") != "done":
        return jsonify({"error": "Audio not ready"}), 404
    return send_file(task["file"], mimetype="audio/wav",
                     as_attachment=False,
                     download_name="speech.wav")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(
        target=engine.load_model,
        kwargs={"backend": DEFAULT_BACKEND, "device": DEFAULT_DEVICE},
        daemon=True,
    ).start()
    app.run(host="0.0.0.0", port=5050, debug=False, use_reloader=False)

# Abil TTS

<p align="center">
  <img src="static/abil.png" alt="Abil TTS mascot" width="220" />
</p>

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-web-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Tkinter](https://img.shields.io/badge/tkinter-desktop-2C2D72?style=for-the-badge&logo=windowsterminal&logoColor=white)](https://docs.python.org/3/library/tkinter.html)
[![License](https://img.shields.io/badge/license-MIT-0A0A0A?style=for-the-badge)](LICENSE)

Text-to-speech (TTS) app with multiple backends (Qwen3-TTS, Piper, Coqui), with both a Flask web UI and a Tkinter desktop UI. It can read documents and generate WAV audio from text.


![alt text](image.png)

## Features

- Web UI with file upload and progress tracking.
- Mermaid diagram generation from full text or selected text snippets.
- Exportable diagram source as `.mmd`.
- Desktop UI with editor, word count, and playback.
- Multiple languages and preset speakers (backend dependent).
- Reads .txt, .md, .docx, and .pdf.
- Background generation with WAV download.

## Structure

- [app.py](app.py): Flask server and API.
- [gui.py](gui.py): Tkinter desktop app.
- [tts_engine.py](tts_engine.py): multi-backend engine, chunking, and WAV writing.
- [text_processor.py](text_processor.py): shared text segmentation for synthesis and diagrams.
- [text_diagram.py](text_diagram.py): Mermaid flowchart generator.
- [document_reader.py](document_reader.py): document text extraction.
- [templates/index.html](templates/index.html): web UI.
- [test_tts.py](test_tts.py): quick model test.
- [requirements.txt](requirements.txt): Python dependencies.

## Requirements

- Python 3.10+ (3.11 recommended for Coqui).
- CUDA GPU for best performance (optional).
- GPU drivers installed (CUDA recommended).

## Installation

Create and activate a Python environment, then install dependencies:

```bash
pip install -r requirements.txt
```

Note: For best GPU support, you may want to reinstall PyTorch with a CUDA wheel that matches your driver/toolkit version after running the install below.

## GPU setup (recommended)

If you have CUDA drivers installed, install a CUDA-enabled PyTorch build after the base requirements:

```bash
pip install -r requirements.txt
pip install --upgrade --index-url https://download.pytorch.org/whl/cu124 torch==2.11.0
```

If you prefer conda:

```bash
conda create -n abil python=3.11
conda activate abil
conda install -c pytorch -c nvidia pytorch pytorch-cuda=12.4
pip install -r requirements.txt
```

## Run

### Web (Flask)

```bash
python app.py
```

Open http://localhost:5050 in your browser.

### Desktop (Tkinter)

```bash
python gui.py
```

### Quick model test

```bash
python test_tts.py
```

The file `output.wav` will be created in the current directory.

## Supported formats

- `.txt`
- `.md` / `.markdown`
- `.docx`
- `.pdf`

## Notes

- Web-generated audio files are stored in `outputs/`.
- The web UI loads the model in the background and reports readiness.
- On CPU, loading can be slower. Adjust the device in the UI if needed.

## Sample audio (inline player)

<audio controls>
	<source src="output.wav" type="audio/wav" />
	Your browser does not support the audio element.
</audio>

<audio controls>
	<source src="outputs/b8782662fc6943328b834853701f208a.wav" type="audio/wav" />
	Your browser does not support the audio element.
</audio>

## Backend configuration

### Qwen3-TTS

Default backend. Uses `qwen-tts` and `torch` for GPU execution.

### Edge-TTS (recommended for low VRAM / 4GB GPU setups)

Lightweight backend with low memory usage. Ideal when Qwen does not fit GPU memory.

Requirements:

```bash
pip install edge-tts
sudo apt install ffmpeg
```

Set backend:

```bash
export TTS_BACKEND=edge
```

Note: Edge-TTS generation requires internet access.

Voice selection:

- Web UI: when backend is `edge`, the Speaker dropdown switches to Edge voices.
- Desktop UI: when backend is `edge`, the Speaker dropdown also switches to Edge voices.
- If no explicit Edge voice is selected, the app falls back to a default voice by language.

### Piper

Set the model path before running:

```bash
export PIPER_MODEL=/path/to/model.onnx
export PIPER_CONFIG=/path/to/model.onnx.json
```

Optional extra CLI args:

```bash
export PIPER_ARGS="--use_cuda"
```

### Coqui TTS

Set the model name (or use the default):

```bash
export COQUI_MODEL=tts_models/en/ljspeech/tacotron2-DDC
```

### Backend and device selection

```bash
export TTS_BACKEND=qwen   # qwen | edge | piper | coqui
export TTS_DEVICE=cuda:0  # cuda:0 | cuda:1 | cpu
```

`TTS_BACKEND` can also be set to `edge`.

## Mermaid diagrams from text

The web UI can convert the whole text or only selected text into a Mermaid flowchart.

1. Write/paste text in the editor.
2. Optionally select a part of the text.
3. Click **Generate Diagram**.
4. Download the generated `.mmd` file.

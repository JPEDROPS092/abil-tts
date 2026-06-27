#!/usr/bin/env python3
"""
Prepare and validate local TTS model assets.

Typical use:
    python scripts/ensure_models.py --piper
    python scripts/ensure_models.py --piper --preload piper,edge
    python scripts/ensure_models.py --piper --preload all --device cpu
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
PIPER_DIR = PROJECT_DIR / "models" / "piper"

PIPER_VOICES = {
    "pt_BR-faber-medium": {
        "repo_path": "pt/pt_BR/faber/medium/pt_BR-faber-medium",
        "model": PIPER_DIR / "pt_BR-faber-medium.onnx",
        "config": PIPER_DIR / "pt_BR-faber-medium.onnx.json",
    },
    "en_US-lessac-medium": {
        "repo_path": "en/en_US/lessac/medium/en_US-lessac-medium",
        "model": PIPER_DIR / "en_US-lessac-medium.onnx",
        "config": PIPER_DIR / "en_US-lessac-medium.onnx.json",
    },
}


def log(message: str) -> None:
    print(f"[ensure_models] {message}", flush=True)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        log(f"ok: {destination.relative_to(PROJECT_DIR)}")
        return

    tmp = destination.with_suffix(destination.suffix + ".tmp")
    log(f"downloading: {url}")
    try:
        with urllib.request.urlopen(url) as response, tmp.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        tmp.replace(destination)
    finally:
        if tmp.exists():
            tmp.unlink()
    log(f"saved: {destination.relative_to(PROJECT_DIR)}")


def ensure_piper_voice(voice: str) -> tuple[Path, Path]:
    if voice not in PIPER_VOICES:
        options = ", ".join(sorted(PIPER_VOICES))
        raise SystemExit(f"Unknown Piper voice '{voice}'. Available: {options}")

    item = PIPER_VOICES[voice]
    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    repo_path = item["repo_path"]
    model_path = item["model"]
    config_path = item["config"]

    download(f"{base_url}/{repo_path}.onnx", model_path)
    download(f"{base_url}/{repo_path}.onnx.json", config_path)
    return model_path, config_path


def check_command(name: str, required_for: str | None = None) -> bool:
    path = shutil.which(name)
    if path:
        log(f"ok: {name} -> {path}")
        return True
    suffix = f" ({required_for})" if required_for else ""
    log(f"missing: {name}{suffix}")
    return False


def check_python_module(name: str, package_hint: str) -> bool:
    code = f"import {name}; print({name!r})"
    result = subprocess.run(
        [sys.executable, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        log(f"ok: python module {name}")
        return True
    log(f"missing: python module {name}; install {package_hint}")
    return False


def check_cuda_stack() -> bool:
    ok = True
    result = subprocess.run(
        ["nvidia-smi"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        log("ok: nvidia-smi can communicate with the driver")
    else:
        log("missing: nvidia-smi cannot communicate with the NVIDIA driver")
        ok = False

    torch_code = (
        "import torch; "
        "print(torch.cuda.is_available()); "
        "print(torch.cuda.device_count())"
    )
    result = subprocess.run(
        [sys.executable, "-c", torch_code],
        text=True,
        capture_output=True,
    )
    lines = result.stdout.strip().splitlines()
    if result.returncode == 0 and lines[:1] == ["True"]:
        log(f"ok: PyTorch CUDA device_count={lines[1] if len(lines) > 1 else '?'}")
    else:
        log("missing: PyTorch cannot see CUDA")
        ok = False

    ort_code = (
        "import onnxruntime as ort; "
        "print('CUDAExecutionProvider' in ort.get_available_providers())"
    )
    result = subprocess.run(
        [sys.executable, "-c", ort_code],
        text=True,
        capture_output=True,
    )
    if result.returncode == 0 and result.stdout.strip() == "True":
        log("ok: ONNX Runtime CUDAExecutionProvider is available")
    else:
        log("missing: ONNX Runtime CUDAExecutionProvider is not available")
        ok = False
    return ok


def preload_backend(backend: str, device: str, env: dict[str, str]) -> None:
    code = (
        "from tts_engine import TTSEngine; "
        "engine = TTSEngine.get_instance(); "
        f"engine.load_model(backend={backend!r}, device={device!r}); "
        f"print('loaded:{backend}')"
    )
    log(f"preloading {backend} on {device}")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_DIR,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        if result.stdout.strip():
            print(result.stdout.rstrip())
        if result.stderr.strip():
            print(result.stderr.rstrip(), file=sys.stderr)
        raise SystemExit(f"Failed to preload backend: {backend}")
    log(f"ok: {backend} loaded")


def parse_preload(value: str) -> list[str]:
    if not value:
        return []
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    if "all" in items:
        return ["edge", "piper", "qwen", "coqui"]
    valid = {"edge", "piper", "qwen", "coqui"}
    unknown = [item for item in items if item not in valid]
    if unknown:
        raise SystemExit(f"Unknown backend(s): {', '.join(unknown)}")
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--piper",
        action="store_true",
        help="Download the default Piper voice model if it is missing.",
    )
    parser.add_argument(
        "--piper-voice",
        default="pt_BR-faber-medium",
        choices=sorted(PIPER_VOICES),
        help="Piper voice to prepare.",
    )
    parser.add_argument(
        "--preload",
        default="",
        help="Comma-separated backends to load for validation: edge,piper,qwen,coqui or all.",
    )
    parser.add_argument(
        "--device",
        default=os.getenv("TTS_DEVICE", "cpu"),
        help="Device passed to model loaders, e.g. cpu or cuda:0.",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Shortcut for --device cuda:0.",
    )
    args = parser.parse_args()
    if args.gpu:
        args.device = "cuda:0"

    env = os.environ.copy()
    if args.piper:
        model_path, config_path = ensure_piper_voice(args.piper_voice)
        env["PIPER_MODEL"] = str(model_path)
        env["PIPER_CONFIG"] = str(config_path)
        log(f"PIPER_MODEL={model_path}")
        log(f"PIPER_CONFIG={config_path}")

    check_command("ffmpeg", "Edge-TTS WAV conversion")
    check_command("sox", "some audio libraries")
    check_python_module("torch", "torch")
    check_python_module("soundfile", "soundfile")
    if args.device.startswith("cuda") and not check_cuda_stack():
        raise SystemExit("CUDA was requested, but the GPU stack is not ready.")

    preload = parse_preload(args.preload)
    if "piper" in preload and not env.get("PIPER_MODEL"):
        model_path, config_path = ensure_piper_voice(args.piper_voice)
        env["PIPER_MODEL"] = str(model_path)
        env["PIPER_CONFIG"] = str(config_path)

    for backend in preload:
        preload_backend(backend, args.device, env)

    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

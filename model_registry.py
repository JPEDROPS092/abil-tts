"""
Model registry — all available models on the MaaS subscription plan.
Each entry describes the model's capabilities and provider brand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class ModelInfo:
    id: str
    brand: str
    capabilities: List[str]
    supports_vision: bool = False
    supports_streaming: bool = True
    is_image_gen: bool = False

    @property
    def display_name(self) -> str:
        caps = ", ".join(self.capabilities)
        return f"[{self.brand}] {self.id}  ({caps})"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "brand": self.brand,
            "display_name": self.display_name,
            "capabilities": self.capabilities,
            "supports_vision": self.supports_vision,
            "supports_streaming": self.supports_streaming,
            "is_image_gen": self.is_image_gen,
        }


# ---------------------------------------------------------------------------
# Text / Reasoning / Vision models
# ---------------------------------------------------------------------------
TEXT_MODELS: List[ModelInfo] = [
    # Qwen
    ModelInfo("qwen3.7-plus",  "Qwen", ["Reasoning", "Text Generation", "Visual Understanding"], supports_vision=True),
    ModelInfo("qwen3.7-max",   "Qwen", ["Reasoning", "Text Generation"]),
    ModelInfo("qwen3.6-plus",  "Qwen", ["Reasoning", "Visual Understanding", "Text Generation"], supports_vision=True),
    ModelInfo("qwen3.6-flash", "Qwen", ["Text Generation", "Visual Understanding", "Reasoning"], supports_vision=True),
    # DeepSeek
    ModelInfo("deepseek-v4-pro",   "DeepSeek", ["Text Generation", "Reasoning"]),
    ModelInfo("deepseek-v4-flash", "DeepSeek", ["Text Generation", "Reasoning"]),
    ModelInfo("deepseek-v3.2",     "DeepSeek", ["Reasoning", "Text Generation"]),
    # MiniMax
    ModelInfo("MiniMax-M2.5", "MiniMax", ["Reasoning", "Text Generation"]),
    # Moonshot AI
    ModelInfo("kimi-k2.7-code", "Moonshot AI", ["Text Generation", "Visual Understanding", "Reasoning"], supports_vision=True),
    ModelInfo("kimi-k2.6",      "Moonshot AI", ["Text Generation", "Reasoning", "Visual Understanding"], supports_vision=True),
    ModelInfo("kimi-k2.5",      "Moonshot AI", ["Text Generation", "Reasoning", "Visual Understanding"], supports_vision=True),
    # Zhipu AI
    ModelInfo("glm-5.2", "Zhipu AI", ["Text Generation", "Reasoning"]),
    ModelInfo("glm-5.1", "Zhipu AI", ["Text Generation", "Reasoning"]),
    ModelInfo("glm-5",   "Zhipu AI", ["Text Generation", "Reasoning"]),
]

# ---------------------------------------------------------------------------
# Image generation models
# ---------------------------------------------------------------------------
IMAGE_MODELS: List[ModelInfo] = [
    ModelInfo("qwen-image-2.0",     "Qwen", ["Image Generation"], is_image_gen=True),
    ModelInfo("qwen-image-2.0-pro", "Qwen", ["Image Generation"], is_image_gen=True),
    ModelInfo("wan2.7-image",       "Wan",  ["Image Generation"], is_image_gen=True),
    ModelInfo("wan2.7-image-pro",   "Wan",  ["Image Generation"], is_image_gen=True),
]

ALL_MODELS: List[ModelInfo] = TEXT_MODELS + IMAGE_MODELS

# Convenience look-up dict
MODEL_MAP = {m.id: m for m in ALL_MODELS}


def get_model(model_id: str) -> ModelInfo:
    if model_id not in MODEL_MAP:
        raise ValueError(f"Unknown model '{model_id}'. Available: {list(MODEL_MAP)}")
    return MODEL_MAP[model_id]


def list_text_models() -> List[ModelInfo]:
    return TEXT_MODELS


def list_image_models() -> List[ModelInfo]:
    return IMAGE_MODELS

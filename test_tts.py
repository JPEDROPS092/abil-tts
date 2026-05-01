import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    device_map="cuda:0",
    dtype=torch.bfloat16,
)

wavs, sr = model.generate_custom_voice(
    text="16S rRNA sequencing has been used extensively in microbiome research to identify the composition of bacteria and archaea within a wide variety of microbiomes from the human gut to the Amazon rainforest.In this guide, we will explore the principles and applications of 16S rRNA sequencing, including sample preparation, DNA extraction, library preparation, sequencing, and data analysis. We will also discuss the limitations and potential pitfalls of 16S rRNA sequencing and provide tips for optimizing your experiments.",
    language="English",
    speaker="Ryan",
)

sf.write("output.wav", wavs[0], sr)
print("OK: output.wav gerado")

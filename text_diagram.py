"""
Build Mermaid diagrams from plain text segments.
"""
import re

from text_processor import TextProcessor


def _short_label(text: str, max_words: int = 10, max_chars: int = 70) -> str:
    words = TextProcessor.normalize(text).split()
    label = " ".join(words[:max_words]).strip()
    if len(label) > max_chars:
        label = label[: max_chars - 3].rstrip() + "..."
    return label or "(empty)"


def _escape_mermaid(label: str) -> str:
    clean = label.replace('"', "'")
    clean = re.sub(r"[\r\n]+", " ", clean)
    return clean


def build_mermaid_flowchart(text: str, title: str = "Text Flow", max_nodes: int = 12) -> str:
    parts = TextProcessor.split_for_diagram(text, max_nodes=max_nodes)
    if not parts:
        parts = ["No content"]

    lines = [
        "---",
        f'title: "{_escape_mermaid(title)}"',
        "---",
        "flowchart TD",
    ]

    for idx, part in enumerate(parts, start=1):
        node_id = f"N{idx}"
        label = _escape_mermaid(_short_label(part))
        lines.append(f'    {node_id}["{idx}. {label}"]')

    for idx in range(1, len(parts)):
        lines.append(f"    N{idx} --> N{idx + 1}")

    return "\n".join(lines)

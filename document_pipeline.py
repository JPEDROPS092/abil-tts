"""Structured document processing for document, translation, and TTS views."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Callable

from document_reader import read_document_structured


_REFERENCE_RE = re.compile(r"^(?:references|referências|bibliography|bibliografia)\b", re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_FENCE_RE = re.compile(r"^\s*```")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)+\s*\|?\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_LATEX_BLOCK_RE = re.compile(
    r"\$\$.+?\$\$|\\\(.+?\\\)|\\\[.+?\\\]"
    r"|\\begin\{(?:equation|align|gather|eqnarray|multline)\*?\}",
    re.DOTALL,
)
_LATEX_COMMANDS = (
    "frac", "dfrac", "tfrac", "sqrt", "sum", "prod", "int", "oint", "lim", "log", "ln", "exp",
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi",
    "omega", "Gamma", "Delta", "Theta", "Lambda", "Sigma", "Phi", "Psi", "Omega",
    "infty", "partial", "nabla", "cdot", "cdots", "times", "div", "pm", "mp", "leq", "geq",
    "neq", "approx", "equiv", "sim", "propto", "rightarrow", "leftarrow", "Rightarrow",
    "Leftarrow", "leftrightarrow", "mapsto", "in", "notin", "subset", "cup", "cap", "forall",
    "exists", "mathbb", "mathcal", "mathbf", "mathrm", "mathit", "text", "textrm", "begin",
    "end", "left", "right", "hat", "bar", "vec", "dot", "tilde", "overline", "underline",
    "binom", "cases", "matrix", "pmatrix", "bmatrix", "operatorname",
)
_LATEX_COMMAND_RE = re.compile(r"\\" + r"(?:" + "|".join(_LATEX_COMMANDS) + r")\b")
_HAS_INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)[^$\n]+?(?<!\$)\$(?!\$)")
_MATH_HINT_RE = re.compile(r"(?:[=∑∏∫√∇∞±≈≤≥≠]|[\w)]\^[({\w]|[_{]\s*[\w)]|[A-Za-z]_[A-Za-z0-9{])")
_SUPERSCRIPT_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ]|\^")


@dataclass
class DocumentBlock:
    type: str
    text: str
    level: int = 0
    exclude: bool = False

    def to_dict(self) -> dict[str, str | int | bool]:
        return asdict(self)


@dataclass
class ProcessedDocument:
    source_name: str
    parser: str
    blocks: list[DocumentBlock]
    display_name: str = ""
    description: str = ""
    meta: dict | None = None

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "parser": self.parser,
            "blocks": [block.to_dict() for block in self.blocks],
            "display_name": self.display_name,
            "description": self.description,
            "meta": self.meta or {},
        }


def _split_blocks(text: str) -> list[str]:
    """Split on blank lines, keeping fenced code and markdown headings atomic."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if not in_fence and _FENCE_RE.match(line):
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            in_fence = True
            current.append(line)
            if line.strip().endswith("```") and len(line.strip()) > 3:
                in_fence = False
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if in_fence:
            current.append(line)
            if line.strip().endswith("```"):
                in_fence = False
                blocks.append("\n".join(current).strip())
                current = []
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            blocks.append(line.strip())
            continue
        if not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _classify_block(value: str) -> tuple[str, int]:
    if value.startswith("```"):
        return "code", 0

    heading = _HEADING_RE.match(value)
    if heading and "\n" not in value:
        return "heading", len(heading.group(1))

    if _REFERENCE_RE.match(value):
        return "reference", 0

    if _LATEX_BLOCK_RE.search(value):
        return "equation", 0
    latex_commands = len(_LATEX_COMMAND_RE.findall(value))
    prose_words = len(re.findall(r"\b[A-Za-zÀ-ÿ]{3,}\b", value))
    is_prose_sentence = (
        value.rstrip().endswith((".", "!", "?"))
        and prose_words >= 5
        and bool(_HAS_INLINE_MATH_RE.search(value))
    )
    if latex_commands >= 1 and not is_prose_sentence:
        return "equation", 0

    lines = [line for line in value.split("\n") if line.strip()]
    table_rows = [line for line in lines if _TABLE_ROW_RE.match(line)]
    if table_rows and (len(table_rows) >= 2 or value.lower().startswith("tabela:")):
        return "table", 0
    if len(lines) == 1 and (value.lower().startswith("tabela:") or "|" in value):
        return "table", 0

    list_items = [line for line in lines if _LIST_ITEM_RE.match(line)]
    if list_items and len(list_items) >= max(2, len(lines) // 2):
        return "list", 0

    if _MATH_HINT_RE.search(value) and len(value) < 400 and not is_prose_sentence:
        return "equation", 0

    if len(value) < 140 and "\n" not in value and not value.endswith((".", "!", "?", ":", ";")):
        return "heading", 0

    return "paragraph", 0


def _classify_blocks(text: str) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    for value in _split_blocks(text):
        kind, level = _classify_block(value)
        blocks.append(DocumentBlock(type=kind, text=value, level=level))
    return blocks


def _docling_markdown(path: str) -> str | None:
    """Use Docling only when installed; its heavy runtime remains optional."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return None
    try:
        result = DocumentConverter().convert(path)
        return result.document.export_to_markdown()
    except Exception:
        return None


def process_document(
    path: str,
    display_name: str = "",
    description: str = "",
    meta: dict | None = None,
) -> ProcessedDocument:
    source_path = Path(path)
    content = None
    parser = "builtin"
    if source_path.suffix.lower() == ".pdf":
        content = _docling_markdown(str(source_path))
        if content:
            parser = "docling"
    if content is None:
        content = read_document_structured(str(source_path))
    return ProcessedDocument(
        source_name=source_path.name,
        parser=parser,
        blocks=_classify_blocks(content),
        display_name=display_name,
        description=description,
        meta=meta,
    )


def tts_text(block: DocumentBlock) -> str:
    """Plain, speakable text for a typed block (markup removed)."""
    if block.type == "heading":
        return _HEADING_RE.sub(r"\2", block.text)
    if block.type == "table":
        rows: list[str] = []
        for line in block.text.split("\n"):
            if _TABLE_SEP_RE.match(line):
                continue
            if _TABLE_ROW_RE.match(line):
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                rows.append("; ".join(cell for cell in cells if cell))
            else:
                rows.append(line.removeprefix("Tabela:").strip())
        return ". ".join(rows)
    if block.type == "list":
        return "\n".join(_LIST_ITEM_RE.sub("", line) for line in block.text.split("\n"))
    if block.type == "equation":
        return re.sub(r"\$\$|\\\(|\\\)|\\\[|\\\]|\$", "", block.text)
    if block.type == "code":
        return "\n".join(
            line for line in block.text.split("\n") if not _FENCE_RE.match(line)
        )
    return block.text


def render_document(document: ProcessedDocument, mode: str = "document") -> str:
    rendered: list[str] = []
    for block in document.blocks:
        if mode == "tts" and block.type in {"code", "reference"}:
            continue
        if mode == "tts":
            text = tts_text(block)
            if block.type == "table":
                text = "Tabela. " + text
            rendered.append(text)
        else:
            rendered.append(block.text)
    return "\n\n".join(rendered).strip()


def translate_document(
    document: ProcessedDocument,
    target_language: str,
    translate: Callable[[str, str], str],
) -> ProcessedDocument:
    """Translate natural-language blocks without sending equations/code to an LLM."""
    translated: list[DocumentBlock] = []
    for block in document.blocks:
        if block.type in {"equation", "code"}:
            translated.append(block)
            continue
        translated.append(DocumentBlock(
            type=block.type,
            text=translate(tts_text(block), target_language),
            level=block.level,
            exclude=block.exclude,
        ))
    return ProcessedDocument(
        source_name=document.source_name,
        parser=document.parser,
        blocks=translated,
        display_name=document.display_name,
        description=document.description,
        meta=document.meta,
    )

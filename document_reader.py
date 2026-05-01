"""
Document reader – extracts plain text from .txt, .md, .docx, .pdf files.
"""
import os
import re


# ── Markdown ──────────────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', '', text)          # fenced code blocks
    text = re.sub(r'`[^`\n]+`', '', text)               # inline code
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)   # headers
    text = re.sub(r'\*{1,3}([^*\n]+?)\*{1,3}', r'\1', text)     # bold/italic
    text = re.sub(r'_{1,3}([^_\n]+?)_{1,3}', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^\)]*\)', '', text)   # images
    text = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', text)        # links
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)        # blockquotes
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)  # hr
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)    # ul
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)   # ol
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Readers ───────────────────────────────────────────────────────────────────

def read_txt(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read().strip()


def read_markdown(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return _strip_markdown(f.read())


def read_docx(path: str) -> str:
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError:
        raise ImportError("python-docx not installed. Run: pip install python-docx")

    doc = Document(path)
    parts: list[str] = []

    for block in doc.element.body:
        tag = block.tag.split('}')[-1]
        if tag == 'p':
            txt = ''.join(n.text or '' for n in block.iter() if n.tag == qn('w:t'))
            if txt.strip():
                parts.append(txt.strip())
        elif tag == 'tbl':
            for row in block.iter():
                if row.tag.split('}')[-1] == 'tr':
                    cells = []
                    for cell in row.iter():
                        if cell.tag.split('}')[-1] == 'tc':
                            t = ''.join(n.text or '' for n in cell.iter() if n.tag == qn('w:t'))
                            if t.strip():
                                cells.append(t.strip())
                    if cells:
                        parts.append(', '.join(cells))

    return '\n'.join(parts)


def read_pdf(path: str) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")

    doc = fitz.open(path)
    pages = [page.get_text() for page in doc]
    doc.close()
    text = '\n'.join(pages)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Public API ────────────────────────────────────────────────────────────────

READERS: dict[str, callable] = {
    '.txt':      read_txt,
    '.md':       read_markdown,
    '.markdown': read_markdown,
    '.docx':     read_docx,
    '.pdf':      read_pdf,
}


def read_document(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext not in READERS:
        supported = ', '.join(READERS)
        raise ValueError(f"Unsupported format '{ext}'. Supported: {supported}")
    return READERS[ext](path)

"""
Text normalization for TTS.

Goals:
- Reflow text extracted from PDFs/docs (mended hyphenation, joined lines).
- Expand numbers, currencies, times, dates and common abbreviations into
  speakable forms in Portuguese (pt-BR) and English (en).
- Keep things simple, dependency-light (uses num2words if available).

Public API: ``normalize(text, language="English")`` returning a normalized string.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from num2words import num2words as _n2w
    _HAS_N2W = True
except ImportError:  # pragma: no cover
    _HAS_N2W = False


# ── Language helpers ─────────────────────────────────────────────────────────

_PT_NAMES = {"portuguese", "português", "portugues", "pt", "pt-br", "pt_br"}
_EN_NAMES = {"english", "en", "en-us", "en_us", "en-gb"}


def _lang_key(language: str | None) -> str:
    """Map a UI language label to a num2words / internal language key."""
    if not language:
        return "en"
    norm = language.strip().lower()
    if norm in _PT_NAMES:
        return "pt_BR"
    if norm in _EN_NAMES:
        return "en"
    # Best-effort mapping for the other supported Qwen languages
    return {
        "chinese": "en",      # num2words has no Chinese; fall back to digits-as-words English isn't great either
        "japanese": "en",
        "korean": "en",
        "german": "de",
        "french": "fr",
        "russian": "ru",
        "spanish": "es",
        "italian": "it",
    }.get(norm, "en")


# ── Reflow ────────────────────────────────────────────────────────────────────

# A line break inside a paragraph (single \n surrounded by text) is treated as a
# soft wrap and replaced with a space. Two or more line breaks keep the paragraph
# split.
_SOFT_WRAP_RE = re.compile(r"(?<!\n)\n(?!\n)")
# Hyphenated word split across line boundaries: "amor-\npróprio" -> "amor-próprio"
# (we keep the hyphen because it might be a real compound word)
_HYPHEN_LINEBREAK_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
# Multiple consecutive spaces collapse to one
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def reflow(text: str) -> str:
    """Rebuild paragraphs from text that has been hard-wrapped (PDFs/copy-paste)."""
    if not text:
        return ""
    # Normalize line endings
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Fix word-final hyphen + line break (keep the hyphen so compound words survive)
    t = _HYPHEN_LINEBREAK_RE.sub(r"\1-\2", t)
    # Collapse single linebreaks inside paragraphs to a space
    t = _SOFT_WRAP_RE.sub(" ", t)
    # Trim spaces around line breaks
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    # Collapse repeated spaces
    t = _MULTI_SPACE_RE.sub(" ", t)
    return t.strip()


# ── Abbreviations ────────────────────────────────────────────────────────────

_ABBREV_PT = {
    r"\bDr\.": "Doutor",
    r"\bDra\.": "Doutora",
    r"\bSr\.": "Senhor",
    r"\bSra\.": "Senhora",
    r"\bSrta\.": "Senhorita",
    r"\bProf\.": "Professor",
    r"\bProfa\.": "Professora",
    r"\bEng\.": "Engenheiro",
    r"\bav\.": "avenida",
    r"\bAv\.": "Avenida",
    r"\bR\.": "Rua",
    r"\bp\.": "página",
    r"\bpp\.": "páginas",
    r"\betc\.": "etcétera",
    r"\bex\.": "exemplo",
    r"\bnº\b": "número",
    r"\bn°\b": "número",
    r"\bnro\.": "número",
    r"\bSec\.": "Secretaria",
    r"\bDept\.": "Departamento",
}

_ABBREV_EN = {
    r"\bDr\.": "Doctor",
    r"\bMr\.": "Mister",
    r"\bMrs\.": "Misses",
    r"\bMs\.": "Miss",
    r"\bProf\.": "Professor",
    r"\bSt\.": "Saint",
    r"\bAve\.": "Avenue",
    r"\bRd\.": "Road",
    r"\bSt\b\.?": "Street",
    r"\betc\.": "et cetera",
    r"\be\.g\.": "for example",
    r"\bi\.e\.": "that is",
    r"\bvs\.": "versus",
    r"\bNo\.": "Number",
    r"\bU\.S\.A\.?": "U S A",
    r"\bU\.K\.?": "U K",
}


def _apply_abbrev(text: str, language_key: str) -> str:
    table = _ABBREV_PT if language_key.startswith("pt") else _ABBREV_EN
    for pat, repl in table.items():
        text = re.sub(pat, repl, text)
    return text


# ── Symbol replacement ───────────────────────────────────────────────────────

_SYMBOLS_PT = [
    (r"&", " e "),
    (r"@", " arroba "),
    (r"%", " por cento"),
    (r"\+", " mais "),
    (r"=", " igual a "),
    (r"/", " barra "),
    (r"§", " parágrafo "),
    (r"°", " graus"),
]

_SYMBOLS_EN = [
    (r"&", " and "),
    (r"@", " at "),
    (r"%", " percent"),
    (r"\+", " plus "),
    (r"=", " equals "),
    (r"/", " slash "),
    (r"§", " section "),
    (r"°", " degrees"),
]


def _apply_symbols(text: str, language_key: str) -> str:
    table = _SYMBOLS_PT if language_key.startswith("pt") else _SYMBOLS_EN
    for pat, repl in table:
        text = re.sub(pat, repl, text)
    return text


# ── Numbers / currencies / times / dates ─────────────────────────────────────

def _n2w_safe(value, language_key: str, **kwargs) -> str:
    if not _HAS_N2W:
        return str(value)
    try:
        return _n2w(value, lang=language_key, **kwargs)
    except (NotImplementedError, TypeError):
        # Fall back to English when the requested language isn't supported
        try:
            return _n2w(value, lang="en", **kwargs)
        except Exception:
            return str(value)


# Currencies
# Matches: R$ 1.500,75 | $1,500.75 | €1500,75 | £100
_CURRENCY_RE = re.compile(
    r"(?P<sym>R\$|\$|US\$|€|£)\s?(?P<num>[\d.,]+)",
    re.UNICODE,
)

# A bare number (integer, decimal, with thousand separators)
# We support both 1,234.56 (en) and 1.234,56 (pt) by trying both interpretations
_NUMBER_RE = re.compile(r"\b\d[\d.,]*\b")

# Time: 10:30 or 10h30 or 10:30:15
_TIME_RE = re.compile(r"\b(\d{1,2})[:h](\d{2})(?::(\d{2}))?\b")

# Date dd/mm/yyyy or yyyy-mm-dd
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")


def _parse_number(raw: str, language_key: str) -> float | int | None:
    """Parse a digits+sep string into a python number, honouring locale conventions."""
    if not raw:
        return None
    s = raw
    if language_key.startswith("pt"):
        # pt: thousands "." decimal ","
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(".", "")
    else:
        # en: thousands "," decimal "."
        if "." in s:
            s = s.replace(",", "")
        else:
            s = s.replace(",", "")
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return None


_CURRENCY_NAMES = {
    "R$": "BRL",
    "US$": "USD",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
}


def _expand_currency(text: str, language_key: str) -> str:
    def repl(m: re.Match) -> str:
        sym = m.group("sym")
        raw = m.group("num")
        n = _parse_number(raw, language_key)
        if n is None:
            return m.group(0)
        cur = _CURRENCY_NAMES.get(sym, "USD")
        try:
            return _n2w_safe(n, language_key, to="currency", currency=cur)
        except Exception:
            return f"{n} {cur}"
    return _CURRENCY_RE.sub(repl, text)


def _expand_time(text: str, language_key: str) -> str:
    is_pt = language_key.startswith("pt")

    def repl(m: re.Match) -> str:
        h = int(m.group(1))
        mi = int(m.group(2))
        s = m.group(3)
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return m.group(0)
        hw = _n2w_safe(h, language_key)
        mw = _n2w_safe(mi, language_key) if mi else None
        if is_pt:
            parts = [hw, "horas" if h != 1 else "hora"]
            if mw:
                parts += ["e", mw, "minutos" if mi != 1 else "minuto"]
        else:
            parts = [hw]
            if mw:
                parts += [mw]
            else:
                parts += ["o'clock"]
        if s:
            sec = int(s)
            sw = _n2w_safe(sec, language_key)
            if is_pt:
                parts += ["e", sw, "segundos" if sec != 1 else "segundo"]
            else:
                parts += ["and", sw, "seconds" if sec != 1 else "second"]
        return " ".join(parts)
    return _TIME_RE.sub(repl, text)


def _expand_date(text: str, language_key: str) -> str:
    is_pt = language_key.startswith("pt")
    months_pt = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                 "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    months_en = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]

    def repl(m: re.Match) -> str:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Heuristic: in pt the format is dd/mm/yyyy, in en mm/dd/yyyy.
        if is_pt:
            day, month, year = a, b, c
        else:
            month, day, year = a, b, c
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return m.group(0)
        year_full = year if year >= 100 else 2000 + year
        if is_pt:
            return f"{_n2w_safe(day, 'pt_BR')} de {months_pt[month-1]} de {_n2w_safe(year_full, 'pt_BR', to='year')}"
        return f"{months_en[month-1]} {_n2w_safe(day, 'en', to='ordinal')}, {_n2w_safe(year_full, 'en', to='year')}"
    return _DATE_RE.sub(repl, text)


def _expand_numbers(text: str, language_key: str) -> str:
    def repl(m: re.Match) -> str:
        raw = m.group(0)
        # Skip pure year-like 4-digit integers that follow common date contexts.
        n = _parse_number(raw, language_key)
        if n is None:
            return raw
        return _n2w_safe(n, language_key)
    return _NUMBER_RE.sub(repl, text)


# ── Final cleanup ────────────────────────────────────────────────────────────

# Remove characters that some TTS pipelines stumble over while keeping basic
# punctuation that influences prosody.
_KEEP_PUNCT = set(".,;:!?…\"'()-—\n")


def _strip_weird(text: str) -> str:
    # Normalize unicode (NFKC keeps accented letters intact)
    text = unicodedata.normalize("NFKC", text)
    # Replace smart quotes with simple ones
    text = (text
            .replace("“", '"').replace("”", '"')
            .replace("‘", "'").replace("’", "'")
            .replace("…", "..."))
    return text


# ── Public API ───────────────────────────────────────────────────────────────

def normalize(text: str, language: str = "English") -> str:
    """Normalize *text* for TTS, tuned for the selected *language*."""
    if not text or not text.strip():
        return text or ""

    lang_key = _lang_key(language)
    t = _strip_weird(text)
    t = reflow(t)
    t = _apply_abbrev(t, lang_key)
    t = _expand_currency(t, lang_key)
    t = _expand_date(t, lang_key)
    t = _expand_time(t, lang_key)
    t = _expand_numbers(t, lang_key)
    t = _apply_symbols(t, lang_key)
    # Final whitespace tidy
    t = _MULTI_SPACE_RE.sub(" ", t)
    t = re.sub(r" *\n *", "\n", t)
    return t.strip()

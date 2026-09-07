"""
Text processor shared by TTS chunking and diagram generation.
"""
import re


class TextProcessor:
    @staticmethod
    def normalize(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        return cleaned

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        src = TextProcessor.normalize(text)
        if not src:
            return []
        return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", src) if s.strip()]

    @staticmethod
    def split_paragraphs(text: str) -> list[str]:
        blocks = re.split(r"\n\s*\n+", (text or "").strip())
        return [TextProcessor.normalize(b) for b in blocks if TextProcessor.normalize(b)]

    @staticmethod
    def _hard_split(fragment: str, max_chars: int) -> list[str]:
        """Guarantee no piece exceeds max_chars, splitting on words then chars.

        Used as a last resort for clauses that have no sentence/comma break
        points (e.g. long formulas or comma-less prose) so the TTS model never
        receives text past its per-language character limit.
        """
        fragment = fragment.strip()
        if len(fragment) <= max_chars:
            return [fragment] if fragment else []

        pieces: list[str] = []
        buf = ""
        for word in fragment.split():
            # A single word longer than the limit must be sliced by characters.
            while len(word) > max_chars:
                if buf:
                    pieces.append(buf)
                    buf = ""
                pieces.append(word[:max_chars])
                word = word[max_chars:]
            if not buf:
                buf = word
            elif len(buf) + 1 + len(word) <= max_chars:
                buf = f"{buf} {word}"
            else:
                pieces.append(buf)
                buf = word
        if buf:
            pieces.append(buf)
        return pieces

    @staticmethod
    def split_for_tts(text: str, max_chars: int = 500) -> list[str]:
        sentences = TextProcessor.split_sentences(text)
        if not sentences:
            return []

        chunks: list[str] = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) + 1 <= max_chars:
                current = (current + " " + sent).strip()
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(sent) <= max_chars:
                current = sent
                continue

            parts = re.split(r"(?<=,)\s+", sent)
            sub = ""
            for p in parts:
                if len(sub) + len(p) + 1 <= max_chars:
                    sub = (sub + " " + p).strip()
                    continue
                if sub:
                    chunks.append(sub)
                    sub = ""
                # A comma-clause may still be longer than the limit; slice it
                # by words/characters so no chunk ever exceeds max_chars.
                if len(p) <= max_chars:
                    sub = p
                else:
                    hard = TextProcessor._hard_split(p, max_chars)
                    chunks.extend(hard[:-1])
                    sub = hard[-1] if hard else ""
            if sub:
                current = sub

        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def split_for_diagram(text: str, max_nodes: int = 12) -> list[str]:
        paras = TextProcessor.split_paragraphs(text)
        if len(paras) >= 3:
            return paras[:max_nodes]
        return TextProcessor.split_sentences(text)[:max_nodes]

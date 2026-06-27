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
                else:
                    if sub:
                        chunks.append(sub)
                    sub = p
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

import re
import unicodedata


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)
    return re.sub(r"[\s、。！？!?.,・ー〜～]", "", text)


def contains_wake(text: str, phrases: list[str]) -> bool:
    value = normalize(text)
    return any(normalize(p) in value for p in phrases)


def strip_wake(text: str, phrases: list[str]) -> str:
    # Match the normalized prefix while preserving the original question's spelling.
    for end in range(1, min(len(text), 40) + 1):
        prefix = normalize(text[:end])
        if any(prefix == normalize(p) for p in phrases):
            return text[end:].lstrip("ー〜～ 、。！？!?.,・\t\n")
    return text.strip()


def speakable(text: str) -> str:
    text = re.sub(r"```.*?```", "コードの詳細は画面で確認できます。", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"(?m)^\s*\|.*$", "", text)
    text = re.sub(r"(?m)^\s*[-*#>]+\s*", "", text)
    text = re.sub(r"[`*_]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def speech_chunks(text: str, limit: int = 110) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", speakable(text))
    chunks, current = [], ""
    for part in parts:
        if current and len(current) + len(part) > limit:
            chunks.append(current)
            current = ""
        while len(part) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(part[:limit])
            part = part[limit:]
        current += part
    if current.strip():
        chunks.append(current.strip())
    return chunks

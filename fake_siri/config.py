from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlparse

from .text import normalize

ROOT = Path(__file__).resolve().parent.parent


def merge(base: dict, overrides: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if key not in base:
            raise ValueError(f"不明な設定: {key}")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ValueError(f"設定 {key} はオブジェクトで指定してください")
            result[key] = merge(base[key], value)
        else:
            result[key] = value
    return result


def validate(config: dict) -> None:
    phrases = config["wake"]["phrases"]
    if not isinstance(phrases, list) or not phrases or any(not isinstance(p, str) or not normalize(p) for p in phrases):
        raise ValueError("呼びかけ語を1つ以上設定してください")
    if not isinstance(config["audio"]["voice_cues"], bool):
        raise ValueError("voice_cuesは true / false で指定してください")
    url = urlparse(config["voicevox"]["url"])
    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("VOICEVOXはこのPCのlocalhost URLを指定してください")
    for section, key, minimum, maximum in [
        ("audio", "silence_seconds", 0.3, 3),
        ("audio", "max_recording_seconds", 3, 120),
        ("audio", "followup_seconds", 0, 60),
        ("audio", "echo_cooldown_seconds", 0, 5),
        ("transcription", "cpu_threads", 1, 32),
        ("transcription", "timeout_seconds", 1, 300),
        ("codex", "timeout_seconds", 5, 300),
        ("voicevox", "speedScale", 0.5, 2),
        ("voicevox", "speaker", 0, 2147483647),
        ("voicevox", "idle_timeout_seconds", 60, 86400),
    ]:
        value = config[section][key]
        if not isinstance(value, (float, int)) or not minimum <= value <= maximum:
            raise ValueError(f"{section}.{key} は {minimum}〜{maximum} で指定してください")
    if config["codex"]["web_search"] not in {"disabled", "cached", "live"}:
        raise ValueError("web_searchは disabled / cached / live のいずれかです")
    if config["transcription"]["backend"] not in {"faster_whisper", "command"}:
        raise ValueError("文字起こしは faster_whisper または command を指定してください")
    if config["transcription"]["backend"] == "command":
        command = config["transcription"]["command"]
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError("文字起こしのcommandは引数の配列で指定してください")
        if not any("{audio}" in x for x in command):
            raise ValueError("commandにWAVパスの差し込み位置 {audio} が必要です")


def load_config() -> dict:
    base = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"
    if local.exists():
        base = merge(base, json.loads(local.read_text(encoding="utf-8")))
    validate(base)
    return base


def save_config(config: dict) -> None:
    validate(config)
    target = ROOT / "config.local.json"
    pending = target.with_suffix(".json.tmp")
    pending.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(target)


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path

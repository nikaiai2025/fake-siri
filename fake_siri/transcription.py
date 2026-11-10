from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .config import ROOT, resolve_path


class Transcriber:
    """Replaceable Japanese STT: local faster-whisper or a user-supplied command."""

    def __init__(self, config: dict, wake_phrases=()):
        self.config = config
        self.wake_hint = wake_phrases[0] if wake_phrases else None
        self.model = None

    def prepare(self) -> None:
        if self.config["backend"] != "faster_whisper" or self.model is not None:
            return
        from faster_whisper import WhisperModel

        path = self.config["model_path"]
        selected = str(resolve_path(path)) if path else self.config["model"]
        self.model = WhisperModel(selected, device="cpu", compute_type="int8",
                                 cpu_threads=int(self.config["cpu_threads"]), local_files_only=True)

    def transcribe(self, pcm: bytes) -> str:
        import numpy as np

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) < 4800 or float(np.sqrt(np.mean(audio ** 2))) < 0.0015:
            return ""
        if self.config["backend"] == "command":
            return self._external(audio)
        self.prepare()
        segments, _ = self.model.transcribe(
            audio, language="ja", beam_size=5, vad_filter=True,
            condition_on_previous_text=False, no_speech_threshold=0.65,
            initial_prompt=self.wake_hint,
        )
        return "".join(s.text for s in segments).strip()

    def _external(self, samples) -> str:
        import soundfile as sf

        target = ROOT / "trash/audio"
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=target, delete=False) as file:
            path = Path(file.name)
        try:
            sf.write(path, samples, 16000, subtype="PCM_16")
            args = [value.replace("{audio}", str(path)) for value in self.config["command"]]
            result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                    timeout=self.config["timeout_seconds"], check=True,
                                    env={**os.environ, "PYTHONUTF8": "1"},
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return result.stdout.strip()
        finally:
            path.unlink(missing_ok=True)

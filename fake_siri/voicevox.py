from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .text import speech_chunks
from .voicevox_server import VoicevoxServer


class Voicevox:
    """Local VOICEVOX HTTP synthesis and playback."""

    def __init__(self, config: dict, on_status=None):
        self.config = config
        self.server = VoicevoxServer(config, self.ready, on_status)

    def request(self, path: str, data: dict | None = None, *, post=False, timeout=30) -> bytes:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else (b"" if post else None)
        request = Request(self.config["url"].rstrip("/") + path, data=body,
                          headers={"Content-Type": "application/json; charset=utf-8"})
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    def ready(self) -> bool:
        try:
            self.request("/version", timeout=1)
            return True
        except (OSError, ValueError):
            return False

    def find_engine(self) -> Path | None:
        return self.server.find_engine()

    def ensure_ready(self) -> None:
        self.server.ensure_ready()

    def conversation(self):
        return self.server.use()

    def warmup(self):
        self.server.warmup()

    def close(self):
        self.server.close()

    def synthesize(self, text: str) -> bytes:
        with self.server.use():
            self.ensure_ready()
            params = urlencode({"speaker": self.config["speaker"], "text": text})
            query = json.loads(self.request("/audio_query?" + params, post=True))
            for key, value in self.config.items():
                if key in query and value is not None:
                    query[key] = value
            return self.request("/synthesis?" + urlencode({"speaker": self.config["speaker"]}), query, timeout=90)

    def speak(self, text: str, cancel, output_device=None) -> None:
        from concurrent.futures import ThreadPoolExecutor

        chunks = speech_chunks(text)
        if not chunks or cancel.is_set():
            return
        # Prepare the next sentence while the current one is being played.
        with self.server.use(), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.synthesize, chunks[0])
            for index in range(len(chunks)):
                wav = future.result()
                if cancel.is_set():
                    break
                if index + 1 < len(chunks):
                    future = pool.submit(self.synthesize, chunks[index + 1])
                self.play_audio(wav, cancel, output_device)

    @staticmethod
    def play_audio(wav: bytes, cancel, output_device=None) -> None:
        import sounddevice as sd
        import soundfile as sf
        if cancel.is_set():
            return
        samples, rate = sf.read(io.BytesIO(wav), dtype="float32", always_2d=True)
        sd.play(samples, rate, device=output_device)
        try:
            while sd.get_stream().active:
                if cancel.wait(0.03):
                    break
        finally:
            sd.stop()

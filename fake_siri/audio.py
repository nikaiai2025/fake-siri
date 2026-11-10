from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque

from .config import resolve_path
from .text import contains_wake

RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2


class SpeechCapture:
    """Bounded recording. Silence alone never becomes a question."""

    def __init__(self, silence=0.9, maximum=25, prefix=b"", minimum_seconds=0):
        self.frames = [prefix] if prefix else []
        self.silence_limit = round(silence * 1000 / FRAME_MS)
        self.maximum = round(maximum * 1000 / FRAME_MS)
        self.minimum = round(minimum_seconds * 1000 / FRAME_MS)
        self.elapsed = 0
        self.speech_frames = 0
        self.silent_frames = 0

    def add(self, frame: bytes, voiced: bool) -> bool:
        self.frames.append(frame)
        self.elapsed += 1
        if voiced:
            self.speech_frames += 1
            self.silent_frames = 0
        else:
            self.silent_frames += 1
        return (
            self.elapsed >= self.maximum
            or (self.speech_frames >= 8 and self.silent_frames >= self.silence_limit and self.elapsed >= self.minimum)
            or (self.speech_frames < 8 and self.elapsed * FRAME_MS >= 6000)
        )

    def audio(self) -> bytes:
        return b"".join(self.frames) if self.speech_frames >= 8 else b""


class WakeDetector:
    def __init__(self, config: dict):
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        path = resolve_path(config["model_path"])
        if not (path / "am/final.mdl").exists():
            raise RuntimeError("呼びかけモデルがありません。setup.cmd を実行してください。")
        self.model = Model(str(path))
        self.recognizer = KaldiRecognizer(self.model, RATE)
        self.phrases = config["phrases"]

    def feed(self, frame: bytes) -> bool:
        final = self.recognizer.AcceptWaveform(frame)
        value = json.loads(self.recognizer.Result() if final else self.recognizer.PartialResult())
        return contains_wake(value.get("text", value.get("partial", "")), self.phrases)

    def reset(self):
        self.recognizer.Reset()


class MicrophoneLoop:
    def __init__(self, config, busy, on_audio, emit, on_cue=None):
        self.config, self.busy, self.on_audio, self.emit = config, busy, on_audio, emit
        self.on_cue = on_cue
        self.enabled = threading.Event()
        self.stop = threading.Event()
        self.manual = threading.Event()
        self.reset_requested = threading.Event()
        self.followup_until = 0.0
        self.audio_queue = queue.Queue(maxsize=150)
        self.detector = None
        self._followup_lock = threading.Lock()

    def prepare(self):
        self.detector = WakeDetector(self.config["wake"])

    def followup(self):
        with self._followup_lock:
            self.followup_until = time.monotonic() + self.config["audio"]["followup_seconds"]
        self.reset_requested.set()

    def standby(self):
        self.manual.clear()
        with self._followup_lock:
            self.followup_until = 0
        self.reset_requested.set()

    def run(self):
        import numpy as np
        import sounddevice as sd
        import webrtcvad

        vad = webrtcvad.Vad(2)
        capture = None
        preroll = deque(maxlen=100)
        was_busy = False
        previous_mode = ""
        level_clock = 0.0

        def callback(indata, frames, timing, status):
            # Audio remains in bounded memory only; no recordings are persisted.
            if self.busy.is_set() or not self.enabled.is_set():
                return
            try:
                self.audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass

        while not self.stop.is_set():
            if not self.enabled.wait(0.1):
                continue
            try:
                with sd.RawInputStream(samplerate=RATE, blocksize=FRAME_SAMPLES, dtype="int16", channels=1,
                                       device=self.config["audio"]["input_device"], callback=callback):
                    while self.enabled.is_set() and not self.stop.is_set():
                        if self.busy.is_set():
                            was_busy = True
                            capture = None
                            preroll.clear()
                            self.stop.wait(0.05)
                            continue
                        if was_busy or self.reset_requested.is_set():
                            was_busy = False
                            previous_mode = ""
                            self.reset_requested.clear()
                            capture = None
                            preroll.clear()
                            self.detector.reset()
                            while not self.audio_queue.empty():
                                try:
                                    self.audio_queue.get_nowait()
                                except queue.Empty:
                                    break
                        now = time.monotonic()
                        followup = now < self.followup_until
                        if capture is None and previous_mode == "followup" and not followup:
                            self.standby()
                            if self.on_cue and self.config["audio"]["voice_cues"]:
                                self.emit("state", "returning")
                                self.on_cue("end")
                            continue
                        mode = "recording" if capture else ("followup" if followup else "waiting")
                        if mode != previous_mode:
                            previous_mode = mode
                            self.emit("state", mode)
                        try:
                            frame = self.audio_queue.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        if len(frame) != FRAME_BYTES:
                            continue
                        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
                        rms = float(np.sqrt(np.mean(samples * samples))) / 32768
                        voiced = vad.is_speech(frame, RATE) and rms > 0.002
                        if now - level_clock > 0.1:
                            self.emit("level", min(1.0, rms * 15))
                            level_clock = now
                        if capture is None:
                            preroll.append(frame)
                            manual = self.manual.is_set()
                            if manual or (followup and voiced) or (not followup and self.detector.feed(frame)):
                                self.manual.clear()
                                prefix = b"".join(preroll)
                                if not followup and self.on_cue and self.config["audio"]["voice_cues"]:
                                    self.emit("state", "acknowledging")
                                    if self.on_cue("start"):
                                        # The user speaks after the cue. Drop the wake
                                        # utterance and speaker echo, not just its text.
                                        prefix = b""
                                        preroll.clear()
                                        while not self.audio_queue.empty():
                                            try:
                                                self.audio_queue.get_nowait()
                                            except queue.Empty:
                                                break
                                if not self.enabled.is_set() or self.stop.is_set() or self.reset_requested.is_set():
                                    continue
                                capture = SpeechCapture(
                                    self.config["audio"]["silence_seconds"],
                                    self.config["audio"]["max_recording_seconds"], prefix,
                                    minimum_seconds=1.4 if not followup else 0,
                                )
                                self.emit("state", "recording")
                                self.detector.reset()
                        elif capture.add(frame, voiced):
                            pcm = capture.audio()
                            capture = None
                            preroll.clear()
                            self.detector.reset()
                            if pcm:
                                self.on_audio(pcm)
                            else:
                                self.standby()
                    capture = None
                    previous_mode = ""
                    self.emit("level", 0)
            except Exception as error:
                self.enabled.clear()
                self.emit("error", f"マイクを開けません: {error}\n設定で入力デバイスを選び直してください。")
                self.emit("state", "paused")

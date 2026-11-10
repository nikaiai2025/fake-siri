from __future__ import annotations

import logging
import threading
import time

from .audio import MicrophoneLoop
from .codex_backend import CodexBackend
from .config import ROOT
from .text import normalize, strip_wake
from .transcription import Transcriber
from .voicevox import Voicevox


class Assistant:
    def __init__(self, config, emit):
        self.config, self.emit = config, emit
        self.busy = threading.Event()
        self.cancel = threading.Event()
        self.closed = threading.Event()
        self.ready = False
        self._job_lock = threading.Lock()
        self.backend = CodexBackend(config["codex"])
        self.voice = Voicevox(config["voicevox"], lambda value: self.emit("voicevox", value))
        self.transcriber = Transcriber(config["transcription"], config["wake"]["phrases"])
        self.cue_audio = {}
        self.mic = MicrophoneLoop(config, self.busy, self.submit_audio, emit, self._play_cue)
        self.worker = None

    def start(self):
        threading.Thread(target=self._initialize, daemon=True, name="prepare").start()

    def _initialize(self):
        try:
            self.emit("state", "preparing")
            self.emit("detail", "Codexのログインを確認しています")
            plan = self.backend.connect()
            if self.config["audio"]["voice_cues"]:
                self.emit("detail", "開始・終了の合図を読み込んでいます")
                self.cue_audio = {
                    name: (ROOT / "assets/cues" / (name + ".wav")).read_bytes()
                    for name in ("start", "end")
                }
            self.emit("detail", "日本語の音声モデルを読み込んでいます")
            self.transcriber.prepare()
            self.mic.prepare()
            if self.closed.is_set():
                return
            self.ready = True
            self.emit("ready", plan)
            self.mic.enabled.set()
            threading.Thread(target=self.mic.run, daemon=True, name="microphone").start()
        except Exception as error:
            logging.exception("Initialization failed")
            self.emit("error", str(error))
            self.emit("state", "error")

    def submit_audio(self, pcm):
        self._submit(pcm=pcm)

    def _play_cue(self, kind):
        wav = self.cue_audio.get(kind)
        if not wav:
            return False
        with self._job_lock:
            if self.busy.is_set() or self.closed.is_set() or not self.mic.enabled.is_set():
                return False
            self.cancel.clear()
            self.busy.set()
        try:
            self.voice.play_audio(wav, self.cancel, self.config["audio"]["output_device"])
            self.cancel.wait(0.1)
        except Exception:
            logging.exception("Voice cue failed")
        finally:
            self.busy.clear()
        return True

    def submit_text(self, text):
        if text.strip():
            self._submit(text=text.strip())

    def _submit(self, text=None, pcm=None):
        with self._job_lock:
            if not self.ready or self.busy.is_set() or self.closed.is_set():
                return False
            self.cancel.clear()
            self.busy.set()
            self.worker = threading.Thread(target=self._respond, args=(text, pcm), daemon=True, name="conversation")
            self.worker.start()
            return True

    def _respond(self, text, pcm):
        successful = False
        try:
            if pcm is not None:
                self.emit("state", "transcribing")
                text = self.transcriber.transcribe(pcm)
                text = strip_wake(text, self.config["wake"]["phrases"])
            if self.cancel.is_set():
                return
            if not text:
                self.emit("detail", "続けて質問してください")
                successful = True
                return
            self.emit("user", text)
            if normalize(text) in {"おしまい", "終了", "待機して", "会話終了"}:
                self.mic.standby()
                self.emit("detail", f"また「{self.config['wake']['phrases'][0]}」と呼んでください")
                return
            self.emit("state", "thinking")
            started = time.monotonic()
            with self.voice.conversation():
                self.voice.warmup()
                answer = self.backend.ask(text, self.cancel)
                if self.cancel.is_set():
                    return
                self.emit("answer", answer)
                self.emit("timing", f"回答生成 {time.monotonic() - started:.1f}秒")
                self.emit("state", "speaking")
                self.voice.speak(answer, self.cancel, self.config["audio"]["output_device"])
            successful = not self.cancel.is_set()
        except Exception as error:
            logging.exception("Conversation failed")
            self.emit("error", str(error))
            self.backend.reset()
        finally:
            self.cancel.wait(self.config["audio"]["echo_cooldown_seconds"])
            if successful and self.mic.enabled.is_set():
                self.mic.followup()
            else:
                self.mic.standby()
            self.busy.clear()
            if not self.mic.enabled.is_set():
                self.emit("state", "paused")

    def pause(self):
        self.mic.enabled.clear()
        self.interrupt()
        self.emit("state", "paused")

    def resume(self):
        if self.ready:
            self.mic.standby()
            self.mic.enabled.set()

    def listen_now(self):
        if self.ready and not self.busy.is_set():
            self.mic.enabled.set()
            self.mic.manual.set()

    def interrupt(self):
        self.cancel.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        self.mic.standby()
        threading.Thread(target=self.backend.interrupt, daemon=True).start()

    def reset_conversation(self):
        if not self.busy.is_set():
            self.backend.reset()
            self.mic.standby()
            self.emit("detail", "新しい会話に切り替えました")

    def close(self):
        self.closed.set()
        self.mic.stop.set()
        self.mic.enabled.clear()
        self.interrupt()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=3)
        try:
            self.voice.close()
        finally:
            self.backend.close()

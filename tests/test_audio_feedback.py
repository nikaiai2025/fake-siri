import threading
import time
import unittest
from unittest.mock import Mock, patch

from fake_siri.assistant import Assistant
from fake_siri.audio import MicrophoneLoop
from fake_siri.config import load_config


class AudioFeedbackTests(unittest.TestCase):
    def test_assistant_startup_does_not_start_voicevox(self):
        assistant = Assistant(load_config(), Mock())
        assistant.backend = Mock()
        assistant.voice = Mock()
        assistant.transcriber = Mock()
        assistant.mic.prepare = Mock()
        with patch("fake_siri.assistant.threading.Thread"):
            assistant._initialize()
        self.assertTrue(assistant.ready)
        assistant.voice.ensure_ready.assert_not_called()
        assistant.voice.warmup.assert_not_called()
        assistant.voice.synthesize.assert_not_called()

    def test_cached_cue_mutes_capture_without_codex_call(self):
        assistant = Assistant(load_config(), Mock())
        assistant.voice = Mock()
        assistant.backend = Mock()
        assistant.cue_audio = {"start": b"cached-wav"}
        assistant.mic.enabled.set()
        assistant.voice.play_audio.side_effect = lambda *args: self.assertTrue(assistant.busy.is_set())
        self.assertTrue(assistant._play_cue("start"))
        self.assertFalse(assistant.busy.is_set())
        assistant.voice.play_audio.assert_called_once()
        assistant.voice.synthesize.assert_not_called()
        assistant.backend.ask.assert_not_called()

    def test_failed_cue_releases_capture(self):
        assistant = Assistant(load_config(), Mock())
        assistant.voice = Mock()
        assistant.cue_audio = {"end": b"cached-wav"}
        assistant.mic.enabled.set()
        assistant.voice.play_audio.side_effect = RuntimeError("output unavailable")
        with self.assertLogs(level="ERROR"):
            assistant._play_cue("end")
        self.assertFalse(assistant.busy.is_set())

    def test_followup_timeout_announces_once_and_returns_to_waiting(self):
        states = []
        cue = Mock()
        config = load_config()
        config["audio"]["voice_cues"] = True

        def emit(kind, value):
            if kind == "state":
                states.append(value)
                if value == "waiting":
                    mic.stop.set()

        mic = MicrophoneLoop(config, threading.Event(), Mock(), emit, cue)
        mic.detector = Mock()
        mic.enabled.set()
        with patch("sounddevice.RawInputStream") as stream:
            stream.return_value.__enter__.side_effect = lambda: setattr(mic, "followup_until", time.monotonic() + 0.15)
            worker = threading.Thread(target=mic.run, daemon=True)
            worker.start()
            worker.join(timeout=3)
            try:
                self.assertFalse(worker.is_alive())
                self.assertEqual(states, ["followup", "returning", "waiting"])
                cue.assert_called_once_with("end")
                mic.on_audio.assert_not_called()
            finally:
                mic.stop.set()
                worker.join(timeout=1)

import threading
import unittest
from unittest.mock import Mock

from fake_siri.audio import FRAME_BYTES, SpeechCapture
from fake_siri.codex_backend import require_included_quota, require_subscription
from fake_siri.config import load_config, merge, validate
from fake_siri.text import contains_wake, normalize, speech_chunks, strip_wake


class CoreTests(unittest.TestCase):
    def test_japanese_wake_and_inline_question(self):
        self.assertTrue(contains_wake("チャッピー", ["チャッピー"]))
        self.assertTrue(contains_wake("ちゃっぴー", ["チャッピー"]))
        self.assertFalse(contains_wake("今日は晴れです", ["チャッピー"]))
        self.assertEqual(strip_wake("チャッピー、富士山の高さは？", ["チャッピー"]), "富士山の高さは？")
        self.assertEqual(strip_wake("チャッピー", ["チャッピー"]), "")

    def test_silence_never_becomes_a_request(self):
        capture = SpeechCapture()
        for _ in range(201):
            ended = capture.add(bytes(FRAME_BYTES), False)
        self.assertTrue(ended)
        self.assertEqual(capture.audio(), b"")

    def test_wake_spellings_and_question_preservation(self):
        phrases = ["ニセモノ", "偽物", "偽者"]
        for spelling in ["ニセモノ", "にせもの", "ﾆｾﾓﾉ", "偽物", "偽 者"]:
            with self.subTest(spelling=spelling):
                self.assertTrue(contains_wake(spelling, phrases))
                self.assertEqual(strip_wake(spelling + "、偽物の見分け方は？", phrases), "偽物の見分け方は？")
                self.assertEqual(strip_wake(spelling, phrases), "")
        self.assertTrue(contains_wake("これは偽物です", phrases))
        self.assertFalse(contains_wake("似たものを探して", phrases))
        self.assertFalse(contains_wake("偽装の意味は", phrases))
        self.assertFalse(contains_wake("偽物", ["ニセモノ"]))  # Kanji needs registration.

    def test_vad_preserves_prefix_and_waits_for_silence(self):
        capture = SpeechCapture(silence=0.3, prefix=b"pre")
        for _ in range(12):
            self.assertFalse(capture.add(bytes(FRAME_BYTES), True))
        for _ in range(9):
            self.assertFalse(capture.add(bytes(FRAME_BYTES), False))
        self.assertTrue(capture.add(bytes(FRAME_BYTES), False))
        self.assertTrue(capture.audio().startswith(b"pre"))

    def test_api_auth_cannot_generate(self):
        for account in [None, {"type": "apiKey"}, {"type": "amazonBedrock"}]:
            with self.assertRaises(RuntimeError):
                require_subscription({"account": account})
        require_subscription({"account": {"type": "chatgpt", "planType": "plus"}})

    def test_partial_override_preserves_other_settings(self):
        original = load_config()
        updated = merge(original, {"voicevox": {"speedScale": 1.3}})
        self.assertEqual(updated["voicevox"]["speaker"], original["voicevox"]["speaker"])
        self.assertEqual(updated["voicevox"]["speedScale"], 1.3)
        self.assertNotEqual(original["voicevox"]["speedScale"], 1.3)

    def test_exhausted_subscription_does_not_use_paid_credits(self):
        status = {"ordinaryUsageAllowed": True, "rateLimits": {
            "primary": {"usedPercent": 100}, "credits": {"hasCredits": True, "balance": "100"}}}
        with self.assertRaises(RuntimeError):
            require_included_quota(status)
        status["rateLimits"]["primary"]["usedPercent"] = 50
        require_included_quota(status)

    def test_unknown_quota_does_not_send(self):
        with self.assertRaises(RuntimeError):
            require_included_quota({})

    def test_cloud_tts_is_rejected(self):
        config = load_config()
        config["voicevox"]["url"] = "https://example.com"
        with self.assertRaises(ValueError):
            validate(config)

    def test_speech_chunks_do_not_drop_content(self):
        text = "最初の文章です。" + "長い説明" * 40 + "。最後の条件です。"
        chunks = speech_chunks(text)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(c) <= 110 for c in chunks))

    def test_end_phrase_does_not_call_codex(self):
        from fake_siri.assistant import Assistant
        assistant = Assistant(load_config(), Mock())
        assistant.backend = Mock()
        assistant._respond("おしまい。", None)
        assistant.backend.ask.assert_not_called()

    def test_cancelled_input_is_not_sent(self):
        from fake_siri.assistant import Assistant
        assistant = Assistant(load_config(), Mock())
        assistant.backend = Mock()
        assistant.cancel.set()
        assistant._respond("この入力は取り消しました", None)
        assistant.backend.ask.assert_not_called()

    def test_transcription_failure_does_not_leave_busy(self):
        from fake_siri.assistant import Assistant
        assistant = Assistant(load_config(), Mock())
        assistant.transcriber = Mock()
        assistant.transcriber.transcribe.side_effect = RuntimeError("test failure")
        assistant.backend = Mock()
        assistant.busy.set()
        with self.assertLogs(level="ERROR"):
            assistant._respond(None, b"audio")
        self.assertFalse(assistant.busy.is_set())
        assistant.backend.ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()

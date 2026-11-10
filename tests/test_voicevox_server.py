import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fake_siri.config import load_config
from fake_siri.voicevox_server import VoicevoxServer


class VoicevoxServerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root_patch = patch("fake_siri.voicevox_server.ROOT", Path(self.folder.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.timer_patch = patch("fake_siri.voicevox_server.threading.Timer")
        self.timer_patch.start()
        self.addCleanup(self.timer_patch.stop)
        self.time = 0.0
        self.probe = Mock(return_value=False)
        self.server = VoicevoxServer(load_config()["voicevox"], self.probe, clock=lambda: self.time)
        self.process = Mock(pid=12345)
        self.process.poll.return_value = None

    def launch_owned(self):
        self.probe.side_effect = [False, True]
        with patch.object(self.server, "find_engine", return_value=Path("C:/VOICEVOX/run.exe")), \
             patch("fake_siri.voicevox_server.subprocess.Popen", return_value=self.process) as launch:
            self.server.ensure_ready()
            command = launch.call_args.args[0]
            self.assertIn("--port", command)
        self.probe.side_effect = None
        self.probe.return_value = True

    def test_standby_does_not_launch_or_probe_engine(self):
        self.probe.assert_not_called()
        self.assertIsNone(self.server._process)
        self.server.close()

    def test_existing_server_is_not_stopped(self):
        self.probe.return_value = True
        with patch("fake_siri.voicevox_server.subprocess.Popen") as launch, \
             patch("fake_siri.voicevox_server.subprocess.run") as stop:
            self.server.ensure_ready()
            self.server.close()
            launch.assert_not_called()
            stop.assert_not_called()

    def test_owned_engine_stops_after_thirty_idle_minutes(self):
        self.launch_owned()
        deadline = self.server._deadline
        self.assertEqual(deadline, 1800)
        with patch("fake_siri.voicevox_server.subprocess.run") as stop:
            self.time = 1799
            self.server._expire(deadline)
            stop.assert_not_called()
            self.time = 1800
            self.server._expire(deadline)
            self.assertIsNone(self.server._process)
            self.process.wait.assert_called_once()
            stop.assert_called_once()
            self.assertIn("12345", stop.call_args.args[0])

    def test_conversation_prevents_shutdown_and_resets_idle_deadline(self):
        self.launch_owned()
        original_deadline = self.server._deadline
        with patch("fake_siri.voicevox_server.subprocess.run") as stop:
            self.time = 1790
            with self.server.use():
                self.time = 2000
                self.server._expire(original_deadline)
                stop.assert_not_called()
            new_deadline = self.server._deadline
            self.assertEqual(new_deadline, 3800)
            self.server._expire(original_deadline)
            stop.assert_not_called()
            self.time = 3800
            self.server._expire(new_deadline)
            stop.assert_called_once()

    def test_close_stops_owned_engine_and_cancels_timer(self):
        self.launch_owned()
        timer = self.server._timer
        with patch("fake_siri.voicevox_server.subprocess.run") as stop:
            self.server.close()
            timer.cancel.assert_called()
            stop.assert_called_once()
            self.assertIsNone(self.server._process)

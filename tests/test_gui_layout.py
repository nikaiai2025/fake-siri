"""Check our own Tk widget layout without microphone or Codex connections."""
import unittest
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


class GuiLayoutTest(unittest.TestCase):
    def setUp(self):
        from fake_siri.config import load_config
        from fake_siri.gui import App
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        self.directory = Path(self.context.enter_context(tempfile.TemporaryDirectory()))
        (self.directory / "trash").mkdir()
        self.context.enter_context(patch("fake_siri.gui.ROOT", self.directory))
        backend = self.context.enter_context(patch("fake_siri.gui.Assistant"))
        self.context.enter_context(patch.object(App, "_tray"))
        self.assistant = backend.return_value
        self.assistant.ready = False
        self.assistant.busy.is_set.return_value = False
        self.assistant.mic.enabled.is_set.return_value = False
        self.app = App(load_config())

    def tearDown(self):
        self.app.closing = True
        for task in self.app.root.tk.call("after", "info"):
            self.app.root.after_cancel(task)
        self.app.root.destroy()

    def test_minimum_window_has_no_clipped_controls(self):
        app = self.app
        app.root.geometry("760x620")
        app.root.update()
        for button in (app.toggle_button, app.listen_button, app.stop_button, app.new_button, app.send_button):
            parent = button.master
            self.assertGreater(button.winfo_width(), 20)
            self.assertLessEqual(button.winfo_x() + button.winfo_width(), parent.winfo_width())
        self.assertGreater(app.history.winfo_height(), 70)
        self.assertGreater(app.input.winfo_width(), 100)

    def test_second_launch_reopens_without_restarting_assistant(self):
        app = self.app
        app.root.update()
        app.root.withdraw()
        request = self.directory / "trash/show.request"
        request.touch()
        app.emit("state", "waiting")
        app._poll()
        app.root.update()
        self.assertEqual(app.root.state(), "normal")
        self.assertTrue(app.root.winfo_viewable())
        self.assertEqual(app.root.title(), "チャッピー — 待ち受け中")
        self.assertFalse(request.exists())
        self.assertIs(app.assistant, self.assistant)
        self.assistant.start.assert_called_once()

    def test_wake_editor_adds_variants_and_removes_selection(self):
        from fake_siri.wake_settings import WakePhraseEditor
        editor = WakePhraseEditor(self.app.root, ["ニセモノ"], background="white", foreground="black", muted="gray")
        editor.entry.insert(0, "にせもの、偽物、偽者")
        editor.add()
        self.assertEqual(editor.values(), ["ニセモノ", "偽物", "偽者"])
        editor.words.selection_set(1)
        editor.remove()
        self.assertEqual(editor.values(), ["ニセモノ", "偽者"])

    def test_settings_dialog_fits_screen(self):
        import tkinter as tk
        with patch("sounddevice.query_devices", return_value=[]):
            self.app.settings()
        self.app.root.update()
        dialog = next(child for child in self.app.root.winfo_children() if isinstance(child, tk.Toplevel))
        self.assertLess(dialog.winfo_height() + 50, dialog.winfo_screenheight())
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()

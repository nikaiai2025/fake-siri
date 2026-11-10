"""Exercise Windows single-instance behavior without starting audio services."""
import msvcrt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fake_siri.__main__ import main


class StartupTests(unittest.TestCase):
    def test_second_launch_requests_show_while_first_holds_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "trash").mkdir()
            with (root / "trash/instance.lock").open("a+b") as first:
                first.write(b"0")
                first.flush()
                first.seek(0)
                msvcrt.locking(first.fileno(), msvcrt.LK_NBLCK, 1)
                with patch("fake_siri.__main__.ROOT", root), \
                     patch("fake_siri.__main__.setup_logging"), \
                     patch("fake_siri.__main__.load_config", return_value={}), \
                     patch("fake_siri.gui.App") as app, \
                     patch("sys.argv", ["fake_siri"]):
                    main()
                    app.assert_not_called()
                self.assertTrue((root / "trash/show.request").is_file())

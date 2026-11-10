"""Own only the engine process we launched; keep it warm between conversations."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from .config import ROOT, resolve_path

log = logging.getLogger("fake_siri.lifecycle")


class VoicevoxServer:
    def __init__(self, config, probe, on_status=None, *, clock=time.monotonic):
        self.config, self.probe = config, probe
        self.on_status = on_status or (lambda value: None)
        self.clock = clock
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._process = None
        self._timer = None
        self._deadline = None
        self._users = 0
        self._warming = None

    def find_engine(self) -> Path | None:
        explicit = self.config.get("engine_path")
        if explicit:
            path = resolve_path(os.path.expandvars(explicit))
            return path if path.is_file() else None
        candidates = []
        if local := os.environ.get("LOCALAPPDATA"):
            local = Path(local)
            candidates += sorted((local / "Microsoft/WinGet/Packages").glob("*VOICEVOX*/VOICEVOX/vv-engine/run.exe"))
            candidates += [local / "Programs/VOICEVOX/vv-engine/run.exe"]
        if program_files := os.environ.get("ProgramFiles"):
            candidates += [Path(program_files) / "VOICEVOX/vv-engine/run.exe"]
        return next((path for path in candidates if path.is_file()), None)

    @contextmanager
    def use(self):
        with self._lock:
            if self._closed.is_set():
                raise RuntimeError("VOICEVOXの接続は終了しています")
            self._users += 1
            self._cancel_timer()
        try:
            yield
        finally:
            with self._lock:
                self._users -= 1
                self._schedule_idle()

    def warmup(self):
        with self._lock:
            if self._closed.is_set() or (self._warming and self._warming.is_alive()):
                return

            def prepare():
                try:
                    self.ensure_ready()
                except Exception:
                    if not self._closed.is_set():
                        log.exception("VOICEVOX warmup failed; synthesis will report availability")
                        self.on_status("起動を確認できません")

            self._warming = threading.Thread(target=prepare, daemon=True, name="voicevox-start")
            self._warming.start()

    def ensure_ready(self):
        with self._lock:
            if self._closed.is_set():
                raise RuntimeError("VOICEVOXの接続は終了しています")
            if self._process is not None and self._process.poll() is not None:
                self._process = None
            if self.probe():
                self.on_status("起動中" if self._process is not None else "外部サーバーに接続（自動停止の対象外）")
                self._schedule_idle()
                return
            engine = self.find_engine() if self.config["auto_start"] else None
            if engine is None:
                raise RuntimeError("VOICEVOXが見つかりません。engine_pathを設定するか、設定した接続先でVOICEVOXを起動してください。")
            self.on_status("起動しています")
            if self._process is None:
                address = urlparse(self.config["url"])
                host = "127.0.0.1" if address.hostname == "localhost" else address.hostname
                command = [str(engine), "--host", host, "--port", str(address.port or 80)]
                log_path = ROOT / "trash/voicevox-engine.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("ab") as output:
                    self._process = subprocess.Popen(
                        command, cwd=str(engine.parent), stdin=subprocess.DEVNULL,
                        stdout=output, stderr=output,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                log.info("voicevox=starting pid=%s", self._process.pid)
            try:
                for _ in range(120):
                    if self._closed.is_set():
                        raise RuntimeError("VOICEVOXの起動を取り消しました")
                    if self._process.poll() is not None:
                        raise RuntimeError("VOICEVOXが起動中に終了しました。trash/voicevox-engine.logを確認してください。")
                    if self.probe():
                        self.on_status("起動中")
                        self._schedule_idle()
                        return
                    self._closed.wait(0.25)
                raise RuntimeError("VOICEVOXの起動を確認できません。trash/voicevox-engine.logを確認してください。")
            except Exception:
                self._stop_owned()
                raise

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
        self._timer, self._deadline = None, None

    def _schedule_idle(self):
        self._cancel_timer()
        if self._closed.is_set() or self._users or self._process is None or self._process.poll() is not None:
            return
        seconds = self.config["idle_timeout_seconds"]
        self._deadline = self.clock() + seconds
        self._timer = threading.Timer(seconds, self._expire, args=(self._deadline,))
        self._timer.daemon = True
        self._timer.start()
        self.on_status(f"会話終了から{seconds / 60:g}分で休止")

    def _expire(self, deadline):
        with self._lock:
            if self._closed.is_set() or self._users or deadline != self._deadline:
                return
            remaining = deadline - self.clock()
            if remaining > 0:
                self._timer = threading.Timer(remaining, self._expire, args=(deadline,))
                self._timer.daemon = True
                self._timer.start()
                return
            self._cancel_timer()
            try:
                self._stop_owned()
            except Exception:
                log.exception("VOICEVOX idle shutdown failed")
                self.on_status("停止できませんでした")

    def _stop_owned(self):
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            if os.name == "nt":
                # Use the live Popen owner, never a port lookup or persisted PID.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                process.terminate()
            process.wait(timeout=5)
        self._process = None
        log.info("voicevox=stopped pid=%s", process.pid)
        self.on_status("休止中（次の質問で起動）")

    def close(self):
        self._closed.set()
        with self._lock:
            self._cancel_timer()
            self._stop_owned()

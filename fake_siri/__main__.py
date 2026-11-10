from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from .config import ROOT, load_config, resolve_path


def setup_logging():
    (ROOT / "trash").mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(ROOT / "trash/app.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("fake_siri.lifecycle").setLevel(logging.INFO)


def doctor(config):
    import sounddevice as sd
    from openai_codex import __version__
    from .codex_backend import CodexBackend
    from .voicevox import Voicevox

    report = {"Codex SDK": __version__, "呼びかけ語": config["wake"]["phrases"]}
    report["呼びかけモデル"] = (resolve_path(config["wake"]["model_path"]) / "am/final.mdl").exists()
    path = config["transcription"]["model_path"]
    report["文字起こしモデル"] = bool(path and (resolve_path(path) / "model.bin").exists())
    voice = Voicevox(config["voicevox"])
    report["VOICEVOX実行ファイル"] = str(voice.find_engine() or "未検出")
    backend = CodexBackend(config["codex"])
    errors = []
    try:
        voice.ensure_ready()
        speakers = json.loads(voice.request("/speakers"))
        selected = next(((speaker["name"], style["name"]) for speaker in speakers
                         for style in speaker["styles"] if style["id"] == config["voicevox"]["speaker"]), None)
        if selected is None:
            raise RuntimeError("指定した声IDがVOICEVOXにありません。voicevox.speakerを確認してください。")
        report["VOICEVOX接続・音声"] = f"VOICEVOX:{selected[0]}（{selected[1]}）"
    except Exception as error:
        report["VOICEVOX接続・音声"] = str(error)
        errors.append("VOICEVOX")
    finally:
        voice.close()
    try:
        report["Codex認証"] = "ChatGPT / " + backend.connect()
    except Exception as error:
        report["Codex認証"] = str(error)
        errors.append("Codex")
    finally:
        backend.close()
    for key, value in report.items():
        print(f"{key}: {value}")
    print(sd.query_devices())
    if not report["呼びかけモデル"] or (config["transcription"]["backend"] == "faster_whisper" and not report["文字起こしモデル"]):
        errors.append("音声モデル（setup.cmdを実行してください）")
    if errors:
        raise RuntimeError("導入確認に失敗: " + "、".join(errors))


def main():
    parser = argparse.ArgumentParser(description="チャッピー: ローカル音声処理＋Codexサブスク")
    parser.add_argument("--doctor", action="store_true", help="接続とモデルを確認（AIへの質問なし）")
    parser.add_argument("--stop", action="store_true", help="常駐アプリを終了する")
    parser.add_argument("--ask", help="テキストで質問する")
    parser.add_argument("--silent", action="store_true", help="--askの回答を読み上げない")
    parser.add_argument("--transcribe", type=Path, help="WAVをローカルで文字起こしする")
    args = parser.parse_args()
    setup_logging()
    if args.stop:
        (ROOT / "trash/stop.request").touch()
        print("fake-siriに終了を要求しました。")
        return
    config = load_config()
    if args.doctor:
        doctor(config)
        return
    if args.transcribe:
        from .transcription import Transcriber
        from .wavefile import read_pcm
        print(Transcriber(config["transcription"], config["wake"]["phrases"]).transcribe(read_pcm(args.transcribe)))
        return
    if args.ask:
        from .codex_backend import CodexBackend
        from .voicevox import Voicevox
        backend = CodexBackend(config["codex"])
        voice = Voicevox(config["voicevox"])
        try:
            response = backend.ask(args.ask, threading.Event())
            print(response)
            if not args.silent:
                voice.speak(response, threading.Event(), config["audio"]["output_device"])
        finally:
            try:
                voice.close()
            finally:
                backend.close()
        return

    # A file lock is released by Windows even after a crash. No stale PID cleanup.
    import msvcrt
    with (ROOT / "trash/instance.lock").open("a+b") as lock:
        # Windows byte-range locks also prevent reading the locked byte.
        # Acquire first, without reading; locking beyond EOF is supported.
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            # Opening the app again should reveal it, including when hidden in
            # the notification area. Keep the existing microphone and thread.
            (ROOT / "trash/show.request").touch()
            return
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("fake-siri.Chappy")
        from .gui import App
        App(config).run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.exception("Application failed")
        if sys.stderr is not None:
            print(str(error), file=sys.stderr)
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("fake-siri 起動エラー", str(error))
            root.destroy()
        raise SystemExit(1)

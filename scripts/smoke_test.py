"""Synthetic Japanese end-to-end check. --ask consumes one Codex subscription turn."""
import argparse
import atexit
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fake_siri.audio import FRAME_BYTES, WakeDetector
from fake_siri.codex_backend import CodexBackend
from fake_siri.config import load_config
from fake_siri.text import strip_wake
from fake_siri.transcription import Transcriber
from fake_siri.voicevox import Voicevox
from fake_siri.wavefile import read_pcm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask", action="store_true")
    args = parser.parse_args()
    config = load_config()
    folder = ROOT / "trash/smoke"
    folder.mkdir(parents=True, exist_ok=True)
    voice = Voicevox(config["voicevox"])
    atexit.register(voice.close)
    voice.ensure_ready()
    source = config["wake"]["phrases"][0] + "、富士山の高さを一文で教えて。"
    (folder / "question.wav").write_bytes(voice.synthesize(source))
    pcm = read_pcm(folder / "question.wav")
    detector = WakeDetector(config["wake"])
    woke = False
    heard = ""
    for i in range(0, len(pcm), FRAME_BYTES):
        if detector.feed(pcm[i:i + FRAME_BYTES]):
            woke = True
        heard = detector.recognizer.PartialResult()
    final = detector.recognizer.FinalResult()
    started = time.monotonic()
    text = Transcriber(config["transcription"], config["wake"]["phrases"]).transcribe(pcm)
    result = {"wake_detected": woke, "vosk_partial": heard, "vosk_final": final,
              "transcript": text, "question": strip_wake(text, config["wake"]["phrases"]),
              "transcription_seconds": round(time.monotonic() - started, 2)}
    if not woke:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise RuntimeError("合成音声で呼びかけを検知できませんでした")
    if "富士山" not in result["question"] or "高" not in result["question"]:
        raise RuntimeError("質問の内容を正しく認識できませんでした: " + result["question"])
    if args.ask:
        backend = CodexBackend(config["codex"])
        try:
            started = time.monotonic()
            answer = backend.ask(result["question"], threading.Event())
            result["codex_seconds"] = round(time.monotonic() - started, 2)
            result["answer"] = answer
            (folder / "answer.wav").write_bytes(voice.synthesize(answer))
            import soundfile as sf
            samples, rate = sf.read(folder / "answer.wav")
            result["answer_audio_seconds"] = round(len(samples) / rate, 2)
        finally:
            backend.close()
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

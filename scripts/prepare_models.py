"""Download local speech models; never connects to a paid inference API."""
from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fake_siri.config import load_config, resolve_path, save_config

VOSK_MODEL = "vosk-model-small-ja-0.22"
SMALL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"


def prepare_wake(destination):
    if (destination / "am/final.mdl").is_file():
        return
    # Do not overwrite an incomplete or user-supplied model directory.
    if destination.exists():
        raise RuntimeError(f"呼びかけモデルが不完全です: {destination}。別の空きパスを指定してください。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_root = ROOT / "trash/downloads"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as temporary:
        staging = Path(temporary)
        archive = staging / "model.zip"
        print("日本語の呼びかけ検知モデルを取得しています（約48MB）…", flush=True)
        urllib.request.urlretrieve(f"https://alphacephei.com/vosk/models/{VOSK_MODEL}.zip", archive)
        with zipfile.ZipFile(archive) as zipped:
            for entry in zipped.infolist():
                if not (staging / entry.filename).resolve().is_relative_to(staging.resolve()):
                    raise RuntimeError("モデルのアーカイブに不正なパスがあります")
            zipped.extractall(staging)
        extracted = staging / VOSK_MODEL
        if not (extracted / "am/final.mdl").is_file():
            raise RuntimeError("取得した呼びかけモデルが不完全です")
        shutil.move(str(extracted), str(destination))


def prepare_transcription(config):
    settings = config["transcription"]
    if settings["backend"] != "faster_whisper":
        return
    if settings["model_path"]:
        selected = resolve_path(settings["model_path"])
        if not (selected / "model.bin").is_file():
            raise RuntimeError("transcription.model_pathが見つかりません。パスを直すか空文字にして再取得してください。")
        return
    from huggingface_hub import snapshot_download
    repo = "Systran/faster-whisper-" + settings["model"]
    revision = SMALL_REVISION if settings["model"] == "small" else "main"
    cache = ROOT / "trash/huggingface"
    print("文字起こしモデルを準備しています（初回はダウンロード）…", flush=True)
    path = Path(snapshot_download(repo, revision=revision, cache_dir=str(cache)))
    settings["model_path"] = path.relative_to(ROOT).as_posix()
    save_config(config)


def main():
    config = load_config()
    prepare_wake(resolve_path(config["wake"]["model_path"]))
    print("呼びかけ検知モデル: 準備完了", flush=True)
    prepare_transcription(config)
    print("文字起こしモデル: 準備完了", flush=True)


if __name__ == "__main__":
    main()

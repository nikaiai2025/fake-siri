from pathlib import Path


def read_pcm(path: Path) -> bytes:
    import numpy as np
    import soundfile as sf
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != 16000:
        # File-input diagnostics only. Microphone capture already uses 16 kHz.
        mono = np.interp(np.arange(round(len(mono) * 16000 / rate)) * rate / 16000,
                         np.arange(len(mono)), mono)
    return (np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes()

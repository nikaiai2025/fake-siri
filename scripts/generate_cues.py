"""Generate the bundled soft two-note system chimes; no speech engine needed."""
import math
import struct
import wave
from pathlib import Path

RATE = 24000
DURATION = 0.44


def chime(frequencies, peak):
    samples = [0.0] * round(RATE * DURATION)
    for offset, frequency in zip((0.0, 0.11), frequencies):
        for i in range(round(offset * RATE), len(samples)):
            t = i / RATE - offset
            attack = min(1.0, t / 0.004)
            release = min(1.0, (DURATION - i / RATE) / 0.025)
            tone = math.sin(2 * math.pi * frequency * t) * math.exp(-t / 0.075)
            tone += 0.22 * math.sin(2 * math.pi * frequency * 2.01 * t) * math.exp(-t / 0.045)
            samples[i] += attack * release * tone
    scale = peak / max(abs(value) for value in samples)
    return struct.pack("<" + "h" * len(samples), *(round(value * scale * 32767) for value in samples))


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent.parent / "assets/cues"
    folder.mkdir(parents=True, exist_ok=True)
    for name, notes, peak in (("start", (523.25, 783.99), 0.32), ("end", (783.99, 523.25), 0.26)):
        with wave.open(str(folder / (name + ".wav")), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(chime(notes, peak))
        print(f"{name}: {DURATION:.2f}s")

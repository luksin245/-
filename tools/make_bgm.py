"""저작권 걱정 없는 배경음악을 직접 합성해서 assets/bgm/ 에 mp3로 저장한다.

사용법: python tools/make_bgm.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reels_auto.paths import bgm_dir, ffmpeg_path  # noqa: E402

SR = 44100
rng = np.random.default_rng(7)


def midi_hz(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def epiano(freq: float, dur: float, vel: float = 1.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * freq * t)
            + 0.35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / 0.4)
            + 0.12 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t / 0.2))
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    return vel * tone * trem * env(n, 0.008, dur * 0.45)


def pluck(freq: float, dur: float, vel: float = 1.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = sum(np.sin(2 * np.pi * k * freq * t) / k ** 1.4 * np.exp(-t * k / 0.35) for k in range(1, 6))
    return vel * tone * env(n, 0.003, 0.5)


def bass(freq: float, dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(4 * np.pi * freq * t)) * env(n, 0.01, dur * 0.8)


def kick() -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 50 + 70 * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)


def hat() -> np.ndarray:
    n = int(0.06 * SR)
    noise = rng.standard_normal(n)
    noise = np.diff(noise, prepend=0)  # 고역만 남기기
    return noise * np.exp(-np.arange(n) / SR / 0.015)


def snare() -> np.ndarray:
    n = int(0.2 * SR)
    t = np.arange(n) / SR
    return (0.6 * rng.standard_normal(n) + 0.4 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t / 0.06)


def place(buf: np.ndarray, sig: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += gain * sig[: j - i]


def reverb(x: np.ndarray, seconds: float = 1.6, mix: float = 0.22) -> np.ndarray:
    n = int(seconds * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR / (seconds / 5))
    ir /= np.sqrt(np.sum(ir ** 2))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return (1 - mix) * x + mix * wet


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # 1차 IIR, 곡이 짧아서 충분히 빠름
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def song(bpm: float, chords: list[list[int]], bars: int, style: str) -> np.ndarray:
    beat = 60 / bpm
    bar = beat * 4
    total = bars * bar
    keys = np.zeros(int(total * SR) + SR)
    low = np.zeros_like(keys)
    drums = np.zeros_like(keys)
    for b in range(bars):
        chord = chords[b % len(chords)]
        t0 = b * bar
        if style == "pluck":
            for s in range(8):
                note = chord[1:][s % (len(chord) - 1)] + (12 if s % 4 == 3 else 0)
                place(keys, pluck(midi_hz(note), beat * 1.5, 0.55), t0 + s * beat / 2)
        else:
            for k, note in enumerate(chord[1:]):
                place(keys, epiano(midi_hz(note), bar * 1.1, 0.4), t0 + k * 0.012)
            if style == "piano":
                for s, note in enumerate([chord[1], chord[2], chord[3], chord[2]]):
                    place(keys, epiano(midi_hz(note + 12), beat * 1.5, 0.22), t0 + s * beat)
        place(low, bass(midi_hz(chord[0]), bar * 0.95), t0)
        if style != "piano":
            for s in range(4):
                if s in (0, 2):
                    place(drums, kick(), t0 + s * beat, 0.9)
                else:
                    place(drums, snare(), t0 + s * beat, 0.22)
            for s in range(8):
                place(drums, hat(), t0 + s * beat / 2 + (0.02 if s % 2 else 0), 0.12)
    keys = reverb(keys, 1.8, 0.28)
    mix = keys + 0.55 * lowpass(low, 400) + drums
    mix = mix[: int(total * SR)]
    # 좌우 살짝 벌리기
    d = int(0.012 * SR)
    left = mix
    right = np.concatenate([np.zeros(d), mix[:-d]]) * 0.9 + mix * 0.1
    st = np.stack([left, right], axis=1)
    st /= np.max(np.abs(st)) + 1e-9
    fade = int(0.02 * SR)
    st[:fade] *= np.linspace(0, 1, fade)[:, None]
    st[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return (st * 0.8).astype(np.float32)


def save(name: str, audio: np.ndarray) -> None:
    out = bgm_dir() / f"{name}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_path(), "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "pipe:0",
           "-c:a", "libmp3lame", "-b:a", "160k", str(out)]
    subprocess.run(cmd, input=audio.tobytes(), check=True)
    print("saved", out)


# 코드: [베이스, 화음음...] (MIDI 번호)
CALM = [[41, 57, 60, 64, 67], [40, 55, 59, 62, 67], [38, 57, 60, 62, 65], [36, 55, 59, 60, 64]]  # Fmaj7 Em7 Dm7 Cmaj7
BRIGHT = [[36, 60, 64, 67, 72], [43, 59, 62, 67, 71], [45, 60, 64, 69, 72], [41, 60, 65, 69, 72]]  # C G Am F
SOFT = [[45, 60, 64, 67, 69], [41, 60, 64, 65, 69], [36, 60, 64, 67, 72], [43, 59, 62, 67, 71]]  # Am7 Fmaj7 C G

if __name__ == "__main__":
    save("01_calm_lofi", song(84, CALM, 16, "lofi"))
    save("02_bright_pop", song(104, BRIGHT, 20, "pluck"))
    save("03_soft_piano", song(72, SOFT, 12, "piano"))

"""말하지 않는 구간을 찾아 잘라낼 구간(점프컷)을 정한다."""
from __future__ import annotations

import numpy as np

FPS = 30


def detect_speech(audio: np.ndarray, sr: int, *, min_silence: float = 0.25, pad: float = 0.08,
                  min_speech: float = 0.1, frame: float = 0.02) -> list[tuple[float, float]]:
    """말하는 구간 [(시작, 끝), ...]을 원본 기준 초 단위로 돌려준다.

    레퍼런스처럼 말 사이의 쉬는 구간을 없애되, 앞뒤로 pad만큼 여유를 남긴다.
    """
    hop = int(frame * sr)
    n = len(audio) // hop
    if n == 0:
        return []
    frames = audio[: n * hop].reshape(n, hop)
    db = 20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9)
    floor = np.percentile(db, 10)
    peak = np.percentile(db, 95)
    threshold = max(floor + 0.3 * (peak - floor), floor + 6)
    voiced = db > threshold

    runs: list[list[float]] = []
    start = None
    for i, v in enumerate(voiced):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append([start * frame, i * frame])
            start = None
    if start is not None:
        runs.append([start * frame, n * frame])

    merged: list[list[float]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < min_silence:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    merged = [r for r in merged if r[1] - r[0] >= min_speech]

    total = len(audio) / sr
    padded: list[list[float]] = []
    for s, e in merged:
        s, e = max(0.0, s - pad), min(total, e + pad)
        if padded and s <= padded[-1][1]:
            padded[-1][1] = e
        else:
            padded.append([s, e])
    return snap_to_frames([(s, e) for s, e in padded])


def snap_to_frames(segments: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """영상 프레임 경계에 맞춰서 소리와 화면이 어긋나지 않게 한다."""
    out = []
    for s, e in segments:
        s2, e2 = round(s * FPS) / FPS, round(e * FPS) / FPS
        if e2 > s2:
            out.append((s2, e2))
    return out


def cut_audio(audio: np.ndarray, sr: int, segments: list[tuple[float, float]]) -> np.ndarray:
    parts = [audio[int(round(s * sr)): int(round(e * sr))] for s, e in segments]
    return np.concatenate(parts) if parts else audio[:0]


def total_length(segments: list[tuple[float, float]]) -> float:
    return sum(e - s for s, e in segments)

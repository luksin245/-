"""Whisper로 음성을 글자로 바꾼다. 인터넷 없이 PC 안에서 돈다 (그래픽카드 없어도 됨)."""
from __future__ import annotations

import os
from typing import Callable

import numpy as np

from .paths import whisper_model
from .project import Word

_model = None

# 숫자 순위를 "오위" 대신 "5위"로 적도록 유도하는 힌트 문장
PROMPT = "TOP 5 정리해 보자. 5위는? 4위는? 3위는? 2위는? 마지막 1위는?"


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(whisper_model(), device="cpu", compute_type="int8",
                              cpu_threads=max(1, (os.cpu_count() or 2) - 1))
    return _model


def transcribe(audio16k: np.ndarray, on_progress: Callable[[float], None] | None = None) -> list[Word]:
    duration = len(audio16k) / 16000
    segments, _ = _get_model().transcribe(
        audio16k, language="ko", word_timestamps=True, beam_size=5,
        vad_filter=False, condition_on_previous_text=False, initial_prompt=PROMPT,
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(round(w.start, 3), round(w.end, 3), text))
        if on_progress and duration:
            on_progress(min(1.0, seg.end / duration))
    return words

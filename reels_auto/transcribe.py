"""Whisper로 음성을 글자로 바꾼다. 인터넷 없이 PC 안에서 돈다 (그래픽카드 없어도 됨)."""
from __future__ import annotations

import os
from typing import Callable

import numpy as np

from .paths import app_dir, whisper_model
from .project import Word

_model = None

# 순위를 "오위" 대신 "5위"로, 순서를 "첫 번째"처럼 적도록 유도하는 힌트 문장
PROMPT = "3위는? 2위는? 마지막 1위는? 첫 번째, 두 번째, 세 번째. S티어, A티어."


def glossary() -> str:
    """assets/words.txt 의 전문 용어 (음성 인식 힌트)."""
    path = app_dir() / "assets" / "words.txt"
    if not path.exists():
        return ""
    words = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    return ", ".join(words)


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
        vad_filter=False, condition_on_previous_text=False,
        # 용어 사전은 여기 한 번만 넣는다 (hotwords로도 넣으면 모델 입력 한도 448토큰을 넘어서 멈춘다)
        initial_prompt=(glossary() + ". " + PROMPT).lstrip(". "),
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


def transcribe_text(audio16k: np.ndarray) -> str:
    """짧은 조각 하나만 따로 받아 적기 (NG 확인용). 앞뒤 문맥 없이 적어서, 같은 말을 두 번 해도 둘 다 나온다."""
    if len(audio16k) < 1600:
        return ""
    segments, _ = _get_model().transcribe(audio16k, language="ko", beam_size=5, vad_filter=False,
                                          condition_on_previous_text=False, initial_prompt=glossary() or None)
    return " ".join(seg.text.strip() for seg in segments).strip()

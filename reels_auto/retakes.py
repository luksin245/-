"""NG(다시 말한 부분) 자동 제거.

원본을 쉬는 구간으로 자른 조각들 중에서
- 바로 뒤 조각이 같은 말로 다시 시작하면(말하다 멈추고 처음부터 다시) 앞 조각을 버리고 마지막 것만 남긴다.
- "다시 할게요", "잠깐만" 같은 NG 말이 들어간 조각과 "음", "어" 뿐인 조각도 버린다.
숫자만 다른 말("4위는요?" → "3위는요?")은 반복이 아니므로 남긴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .project import Word

FILLERS = {"음", "어", "아", "그", "저", "으음", "음음", "어어", "에", "흠"}
NG_PHRASES = ("다시할게", "다시갈게", "다시하겠", "다시할께", "잠깐만", "죄송합니다", "틀렸다", "아잠깐", "컷")
LOOKAHEAD = 2  # 몇 조각 뒤까지 다시 말한 걸 찾을지
MAX_GAP = 8.0  # 다시 말한 조각이 이 시간(초) 안에 나와야 NG로 본다


@dataclass
class Removed:
    start: float  # 원본 기준
    end: float
    text: str
    reason: str


def _norm(text: str) -> str:
    return re.sub(r"[^\w]", "", text)


def _digits(text: str) -> str:
    return "".join(re.findall(r"\d", text))


def _is_restart(a: str, b: str) -> bool:
    """a를 말하다가 멈추고 b에서 처음부터 다시 말했는지."""
    if len(a) < 4 or len(b) < len(a) * 0.8:
        return False
    if _digits(a) != _digits(b[: len(a) + 2])[: len(_digits(a))]:
        return False  # "4위는요" / "3위는요" 처럼 숫자가 다르면 다른 말
    head = b[: len(a)]
    return SequenceMatcher(None, a, head).ratio() >= 0.75


def remove_retakes(segments: list[tuple[float, float]], words: list[Word]
                   ) -> tuple[list[tuple[float, float]], list[Word], list[Removed]]:
    """(남길 조각들, 시간을 다시 맞춘 단어들, 버린 조각 목록).

    words 는 잘린 영상(조각들을 이어 붙인) 기준 시간이다.
    """
    offsets, t = [], 0.0
    for s, e in segments:
        offsets.append(t)
        t += e - s
    by_seg: list[list[Word]] = [[] for _ in segments]
    for w in words:
        mid = (w.start + w.end) / 2
        k = max(0, min(len(segments) - 1, sum(1 for o in offsets if o <= mid) - 1))
        by_seg[k].append(w)
    texts = [" ".join(w.text.strip() for w in ws) for ws in by_seg]
    norms = [_norm(x) for x in texts]

    drop: dict[int, str] = {}
    for i, a in enumerate(norms):
        seg_len = segments[i][1] - segments[i][0]
        if not a and seg_len < 1.0:
            drop[i] = "말소리 없음"
            continue
        tokens = [_norm(w.text) for w in by_seg[i] if _norm(w.text)]
        if tokens and all(tok in FILLERS for tok in tokens):
            drop[i] = "군말"
            continue
        if any(ng in a for ng in NG_PHRASES):
            drop[i] = "NG 말"
            continue
        for j in range(i + 1, min(len(segments), i + 1 + LOOKAHEAD)):
            if offsets[j] - (offsets[i] + seg_len) > MAX_GAP:
                break
            if _is_restart(a, norms[j]):
                drop[i] = "다시 말함"
                break

    kept_segments: list[tuple[float, float]] = []
    new_words: list[Word] = []
    removed: list[Removed] = []
    t_new = 0.0
    for i, (s, e) in enumerate(segments):
        if i in drop:
            removed.append(Removed(s, e, texts[i], drop[i]))
            continue
        shift = t_new - offsets[i]
        for w in by_seg[i]:
            new_words.append(Word(round(w.start + shift, 3), round(w.end + shift, 3), w.text))
        kept_segments.append((s, e))
        t_new += e - s
    return kept_segments, new_words, removed

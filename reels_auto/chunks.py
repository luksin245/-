"""NG 조각을 직접 넣고 빼기.

조각(Chunk)을 켜고 끄면 남길 구간·단어·자막이 바뀌고, 목록·스티커·퀴즈·티어 시점도 그만큼 밀리거나 당겨진다.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import replace

from . import analyze, cutter
from .project import Project, Word


def _offsets(segments: list[tuple[float, float]]) -> list[float]:
    out, t = [], 0.0
    for s, e in segments:
        out.append(t)
        t += e - s
    return out


def cut_to_src(t: float, segments: list[tuple[float, float]]) -> float:
    """최종 영상 시간 → 원본 시간."""
    offs = _offsets(segments)
    i = max(0, bisect_right(offs, t) - 1)
    s, e = segments[i]
    return min(e, s + t - offs[i])


def src_to_cut(t: float, segments: list[tuple[float, float]]) -> float:
    """원본 시간 → 최종 영상 시간. 빠진 곳이면 다음 남은 조각의 시작으로."""
    offs = _offsets(segments)
    for (s, e), o in zip(segments, offs):
        if t < s:
            return o
        if t <= e:
            return o + t - s
    return offs[-1] + segments[-1][1] - segments[-1][0] if segments else 0.0


def words_for(segments: list[tuple[float, float]], src_words: list[Word]) -> list[Word]:
    """원본 기준 단어 중 남긴 조각에 든 것만 최종 영상 시간으로."""
    offs = _offsets(segments)
    out = []
    for w in src_words:
        mid = (w.start + w.end) / 2
        for (s, e), o in zip(segments, offs):
            if s - 0.05 <= mid <= e + 0.05:
                a, b = max(w.start, s), min(w.end, e)
                out.append(replace(w, start=round(o + a - s, 3), end=round(o + max(b, a) - s, 3)))
                break
    return out


def apply_chunks(p: Project) -> None:
    """p.chunks 의 keep 에 맞춰 구간·단어·자막을 다시 만들고, 나머지 시점들을 옮긴다."""
    new_segments = [(c.start, c.end) for c in p.chunks if c.keep]
    if not new_segments:
        raise ValueError("남길 조각이 하나도 없어요. 적어도 하나는 켜 주세요.")
    old_segments = p.segments

    def move(t: float) -> float:
        return round(src_to_cut(cut_to_src(t, old_segments), new_segments), 3)

    p.segments = new_segments
    p.duration = round(cutter.total_length(new_segments), 3)
    p.words = words_for(new_segments, p.src_words)
    p.captions = analyze.make_captions(p.words, p.duration)
    for it in p.items:
        if it.time is not None:
            it.time = move(it.time)
    for x in p.stickers:
        x.start, x.end = move(x.start), move(x.end)
    for q in p.quiz:
        q.start, q.reveal, q.end = move(q.start), move(q.reveal), move(q.end)
    for t in p.tiers:
        t.time = move(t.time)
    p.ng_removed = [f"{c.start:.1f}초 · {c.reason or '직접 뺌'} · {c.text}" for c in p.chunks if not c.keep and c.text]

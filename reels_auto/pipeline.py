"""원본 영상 → 분석(컷, 음성 인식, 자동 추천) → 편집 정보(Project)."""
from __future__ import annotations

from typing import Callable

from dataclasses import replace

from . import analyze, cutter
from .chunks import cut_to_src
from .media import load_audio
from .paths import bgm_dir
from .project import Project, Word
from .hooks import classify as classify_hook
from .quiz import detect_quiz
from .retakes import remove_retakes, suspicious_segments
from .tier import detect_tiers
from .stickers import auto_stickers

Progress = Callable[[str, float], None]


def default_bgm() -> str | None:
    files = sorted(bgm_dir().glob("*.mp3")) if bgm_dir().exists() else []
    return str(files[0]) if files else None


def analyze_video(source: str, on_progress: Progress | None = None, words: list[Word] | None = None,
                  remove_ng: bool = True) -> Project:
    """words를 주면 음성 인식을 건너뛴다 (테스트용). remove_ng면 다시 말한 부분(NG)을 자동으로 뺀다."""
    report = on_progress or (lambda msg, frac: None)
    report("소리 읽는 중", 0.0)
    audio = load_audio(source)
    report("쉬는 구간 찾는 중", 0.05)
    segments = cutter.detect_speech(audio, 16000)
    duration = round(cutter.total_length(segments), 3)

    transcribe_clip = None
    if words is None:
        from .transcribe import transcribe, transcribe_text

        transcribe_clip = transcribe_text

        report("음성 인식 준비 중 (처음엔 조금 걸려요)", 0.1)
        cut = cutter.cut_audio(audio, 16000, segments)
        words = transcribe(cut, lambda f: report("음성 인식 중", 0.1 + 0.85 * f))

    overrides: dict[int, str] = {}
    if remove_ng and transcribe_clip is not None:
        for i in suspicious_segments(segments, words):
            s, e = segments[i]
            overrides[i] = transcribe_clip(audio[int(s * 16000): int(e * 16000)])
    kept, kept_words, removed, chunks, src_words = remove_retakes(segments, words, overrides)
    ng_removed: list[str] = []
    if remove_ng:
        segments, words = kept, kept_words
        duration = round(cutter.total_length(segments), 3)
        ng_removed = [f"{r.start:.1f}초 · {r.reason} · {r.text}" for r in removed if r.text]
    else:  # NG를 빼지 않아도 조각 목록은 남겨서 나중에 직접 고를 수 있게
        for c in chunks:
            c.keep, c.reason = True, ""
        src_words = [replace(w, start=round(cut_to_src(w.start, segments), 3), end=round(cut_to_src(w.end, segments), 3))
                     for w in words]

    report("얼굴 위치 찾는 중", 0.97)
    from .face import detect_face_box

    face_box = detect_face_box(source, segments)
    style, count, items = analyze.detect_list(words)
    quiz_items = detect_quiz(words, duration) if style == "none" else []
    if quiz_items:
        style, count = "quiz", 0
    tier_items = detect_tiers(words) if style == "none" else []
    if tier_items:
        style, count = "tier", 0
    captions = analyze.make_captions(words, duration)
    # 목록이 있는 영상은 목록 패널과 겹치므로 스티커를 기본으로 끈다
    picked = auto_stickers(captions, duration) if style == "none" else []
    report("완료", 1.0)
    return Project(
        source=source,
        segments=segments,
        duration=duration,
        words=words,
        captions=captions,
        title=analyze.suggest_title(words, style, count),
        list_style=style,
        list_count=count,
        items=items,
        bgm=default_bgm(),
        face_box=face_box,
        stickers=picked,
        quiz=quiz_items,
        tiers=tier_items,
        hook_type=classify_hook(words, style),
        ng_removed=ng_removed,
        chunks=chunks,
        src_words=src_words,
    )

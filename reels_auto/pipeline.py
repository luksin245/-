"""원본 영상 → 분석(컷, 음성 인식, 자동 추천) → 편집 정보(Project)."""
from __future__ import annotations

from typing import Callable

from . import analyze, cutter
from .media import load_audio
from .paths import bgm_dir
from .project import Project, Word
from .hooks import classify as classify_hook
from .quiz import detect_quiz
from .tier import detect_tiers
from .stickers import auto_stickers

Progress = Callable[[str, float], None]


def default_bgm() -> str | None:
    files = sorted(bgm_dir().glob("*.mp3")) if bgm_dir().exists() else []
    return str(files[0]) if files else None


def analyze_video(source: str, on_progress: Progress | None = None, words: list[Word] | None = None) -> Project:
    """words를 주면 음성 인식을 건너뛴다 (테스트용)."""
    report = on_progress or (lambda msg, frac: None)
    report("소리 읽는 중", 0.0)
    audio = load_audio(source)
    report("쉬는 구간 찾는 중", 0.05)
    segments = cutter.detect_speech(audio, 16000)
    duration = round(cutter.total_length(segments), 3)

    if words is None:
        from .transcribe import transcribe

        report("음성 인식 준비 중 (처음엔 조금 걸려요)", 0.1)
        cut = cutter.cut_audio(audio, 16000, segments)
        words = transcribe(cut, lambda f: report("음성 인식 중", 0.1 + 0.85 * f))

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
    )

"""마지막으로 고른 설정 기억하기 (제목 글꼴, 음악, 얼굴 보정, 확대, 목소리 다듬기, NG 자동 제거).

프로그램 폴더의 settings.json 에 저장한다. 쓸 수 없는 폴더면 사용자 폴더(~/.reels_auto)에 저장한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .paths import app_dir
from .project import Project

DEFAULTS = {
    "title_font": "나눔명조",
    "bgm": None,  # 음악 파일 경로 (없으면 첫 번째 기본 음악)
    "no_bgm": False,
    "bgm_volume": 0.18,
    "retouch": "약하게",
    "slim": "약하게",
    "punch_zoom": True,
    "voice_clean": True,
    "remove_ng": True,
}


def _paths() -> list[Path]:
    return [app_dir() / "settings.json", Path.home() / ".reels_auto" / "settings.json"]


def load() -> dict:
    for path in _paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
        except (OSError, ValueError):
            continue
    return dict(DEFAULTS)


def save(prefs: dict) -> None:
    data = json.dumps({k: prefs.get(k, v) for k, v in DEFAULTS.items()}, ensure_ascii=False, indent=2)
    for path in _paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding="utf-8")
            return
        except OSError:
            continue


def apply(p: Project, prefs: dict) -> Project:
    """새로 분석한 편집 정보에 기억해 둔 설정을 입힌다."""
    p.title_font = prefs["title_font"]
    if prefs["no_bgm"]:
        p.bgm = None
    elif prefs["bgm"] and Path(prefs["bgm"]).exists():
        p.bgm = prefs["bgm"]
    p.bgm_volume = float(prefs["bgm_volume"])
    p.retouch, p.slim = prefs["retouch"], prefs["slim"]
    p.punch_zoom, p.voice_clean = bool(prefs["punch_zoom"]), bool(prefs["voice_clean"])
    return p

"""프로그램 폴더, FFmpeg, 폰트, BGM, Whisper 모델 위치를 찾는다."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    """exe로 묶였으면 exe 옆 폴더, 소스로 실행하면 저장소 루트."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def ffmpeg_path() -> str:
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    bundled = app_dir() / "bin" / exe
    if bundled.exists():
        return str(bundled)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError("FFmpeg를 찾을 수 없습니다. bin 폴더에 ffmpeg.exe를 넣어주세요.")


def fonts_dir() -> Path:
    return app_dir() / "assets" / "fonts"


def bgm_dir() -> Path:
    return app_dir() / "assets" / "bgm"


def whisper_model() -> str:
    """번들된 모델 폴더가 있으면 그 경로, 없으면 모델 이름(처음 한 번 인터넷에서 받음)."""
    local = app_dir() / "models" / "whisper-small"
    if (local / "model.bin").exists():
        return str(local)
    return "small"

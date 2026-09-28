"""FFmpeg 실행과 오디오 읽기."""
from __future__ import annotations

import subprocess
import sys
from typing import Callable

import numpy as np

from .paths import ffmpeg_path

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # Windows에서 검은 콘솔 창 숨기기


def load_audio(path: str, sr: int = 16000) -> np.ndarray:
    """영상의 오디오를 모노 float32 배열로 읽는다."""
    cmd = [ffmpeg_path(), "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError("오디오를 읽지 못했습니다:\n" + proc.stderr.decode("utf-8", "replace")[-800:])
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise RuntimeError("영상에 소리가 없습니다. 목소리가 녹음된 원본 영상을 넣어주세요.")
    return audio


def run_ffmpeg(args: list[str], cwd: str | None = None, total_seconds: float | None = None,
               on_progress: Callable[[float], None] | None = None) -> None:
    """FFmpeg를 실행하고 진행률(0~1)을 알려준다."""
    cmd = [ffmpeg_path(), "-nostdin", "-hide_banner", "-v", "error", "-progress", "pipe:1", "-nostats", *args]
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_NO_WINDOW, text=True, encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        if on_progress and total_seconds and line.startswith("out_time_us="):
            try:
                on_progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / total_seconds))
            except ValueError:
                pass
    err = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError("영상 만들기에 실패했습니다:\n" + err[-1500:])

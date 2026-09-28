"""편집 정보를 받아 FFmpeg로 최종 릴스(1080x1920 mp4)를 만든다."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .ass import build_ass
from .cutter import FPS
from .media import run_ffmpeg
from .paths import fonts_dir
from .project import Project


def _keep_expr(segments: list[tuple[float, float]]) -> str:
    return "+".join(f"gte(t,{s:.4f})*lt(t,{e:.4f})" for s, e in segments)


def build_filter(p: Project) -> str:
    keep = _keep_expr(p.segments)
    d = p.duration
    parts = [
        f"[0:v]fps={FPS},select='{keep}',setpts=N/{FPS}/TB,"
        # 픽셀이 정사각형이 아닌 영상(SAR≠1)도 실제 보이는 비율대로 맞춘다
        f"scale='trunc(iw*sar/2)*2':ih,setsar=1,"
        f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
        f"subtitles=f=subs.ass:fontsdir=fonts,format=yuv420p[vout]",
        f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"aselect='{keep}',asetpts=N/SR/TB,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[voice]",
    ]
    if p.bgm:
        fade_out = max(0.0, d - 1.5)
        parts += [
            "[voice]asplit=2[v1][sc]",
            f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={p.bgm_volume:.3f},"
            f"atrim=0:{d:.3f},afade=t=in:d=0.5,afade=t=out:st={fade_out:.3f}:d=1.5[bg]",
            # 목소리가 나올 때 BGM을 살짝 줄임
            "[bg][sc]sidechaincompress=threshold=0.03:ratio=4:attack=30:release=400[bgd]",
            "[v1][bgd]amix=inputs=2:duration=first:normalize=0[aout]",
        ]
    else:
        parts.append("[voice]anull[aout]")
    return ";\n".join(parts)


def render(p: Project, output: str, on_progress: Callable[[float], None] | None = None) -> None:
    if not p.segments:
        raise RuntimeError("남길 구간이 없습니다. 목소리가 들리는 영상인지 확인해주세요.")
    with tempfile.TemporaryDirectory(prefix="reels_") as tmp:
        work = Path(tmp)
        # subtitles 필터는 Windows 경로(C:\...)를 다루기 까다로워서, 작업 폴더 안의 상대 경로만 쓴다
        (work / "subs.ass").write_text(build_ass(p), encoding="utf-8")
        shutil.copytree(fonts_dir(), work / "fonts")
        (work / "graph.txt").write_text(build_filter(p), encoding="utf-8")

        args = ["-y", "-i", str(Path(p.source).resolve())]
        if p.bgm:
            args += ["-stream_loop", "-1", "-i", str(Path(p.bgm).resolve())]
        args += [
            "-/filter_complex", "graph.txt", "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-t", f"{p.duration:.3f}",
            "-movflags", "+faststart", str(Path(output).resolve()),
        ]
        run_ffmpeg(args, cwd=str(work), total_seconds=p.duration, on_progress=on_progress)

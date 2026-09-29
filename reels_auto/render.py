"""편집 정보를 받아 FFmpeg로 최종 릴스(1080x1920 mp4)를 만든다."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable

from . import face, quiz, stickers, zoom
from .ass import build_ass
from .cutter import FPS
from .media import run_ffmpeg
from .paths import bgm_dir, fonts_dir
from .project import Project


def _keep_expr(segments: list[tuple[float, float]]) -> str:
    return "+".join(f"gte(t,{s:.4f})*lt(t,{e:.4f})" for s, e in segments)


def build_filter(p: Project, face_graph: str, sticker_graph: str) -> str:
    keep = _keep_expr(p.segments)
    d = p.duration
    parts = [
        # 픽셀이 정사각형이 아닌 영상(SAR≠1)도 실제 보이는 비율대로 세로 화면에 맞춘다
        f"[0:v]fps={FPS},select='{keep}',setpts=N/{FPS}/TB,{face.FIT}[vfit]",
        face_graph,
        zoom.build_graph(p.segments, p.face_box, "vface", "vzoom") if p.punch_zoom else "[vface]null[vzoom]",
        sticker_graph,
        "[vstk]subtitles=f=subs.ass:fontsdir=fonts,format=yuv420p[vout]",
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
    if p.bgm and not Path(p.bgm).exists():
        # 다른 PC에서 저장한 편집 정보면 같은 이름의 BGM을 이 프로그램 폴더에서 찾고, 없으면 BGM 없이 만든다
        local = bgm_dir() / Path(p.bgm).name
        p.bgm = str(local) if local.exists() else None
    with tempfile.TemporaryDirectory(prefix="reels_") as tmp:
        work = Path(tmp)
        # subtitles 필터는 Windows 경로(C:\...)를 다루기 까다로워서, 작업 폴더 안의 상대 경로만 쓴다
        (work / "subs.ass").write_text(build_ass(p), encoding="utf-8")
        shutil.copytree(fonts_dir(), work / "fonts", ignore=shutil.ignore_patterns("*.txt"))

        args = ["-y", "-i", str(Path(p.source).resolve())]
        if p.bgm:
            args += ["-stream_loop", "-1", "-i", str(Path(p.bgm).resolve())]
        first_extra = 2 if p.bgm else 1
        face_graph, images = face.build_graph(str(work), p.retouch, p.slim, p.face_box, first_extra)
        pictures = stickers.sticker_overlays(p.stickers)
        if p.list_style == "quiz":
            pictures += quiz.overlays(p.quiz)
        sticker_graph, sticker_files = stickers.build_graph(pictures, "vzoom", "vstk", first_extra + len(images))
        for img in [*images, *sticker_files]:
            args += ["-i", img]
        (work / "graph.txt").write_text(build_filter(p, face_graph, sticker_graph), encoding="utf-8")

        args += [
            "-/filter_complex", "graph.txt", "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-t", f"{p.duration:.3f}",
            "-movflags", "+faststart", str(Path(output).resolve()),
        ]
        run_ffmpeg(args, cwd=str(work), total_seconds=p.duration, on_progress=on_progress)

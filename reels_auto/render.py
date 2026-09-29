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


# 목소리 다듬기: 낮은 웅웅거림(에어컨·책상 울림) 자르고, 배경 잡음 줄이기
VOICE_CLEAN = "highpass=f=80,afftdn=nr=12:nf=-40:tn=1,"


def _preview_start(p: Project, at: float) -> tuple[int, int]:
    """미리보기용: at 이 든 조각 번호, 그 조각이 최종 영상에서 시작하는 프레임."""
    t = 0.0
    for i, (s, e) in enumerate(p.segments):
        if at < t + e - s or i == len(p.segments) - 1:
            return i, round(t * FPS)
        t += e - s
    return 0, 0


def build_filter(p: Project, face_graph: str, sticker_graph: str, preview_at: float | None = None) -> str:
    keep = _keep_expr(p.segments)
    d = p.duration
    first, frame0 = 0, 0
    if preview_at is not None:  # 미리보기는 그 조각부터만 읽는다 (앞부분을 다 처리하지 않게)
        first, frame0 = _preview_start(p, preview_at)
        keep = _keep_expr(p.segments[first:])
    parts = [
        # 픽셀이 정사각형이 아닌 영상(SAR≠1)도 실제 보이는 비율대로 세로 화면에 맞춘다
        f"[0:v]fps={FPS},select='{keep}',setpts=(N+{frame0})/{FPS}/TB,{face.FIT}[vfit]",
        face_graph,
        zoom.build_graph(p.segments, p.face_box, "vface", "vzoom", frame0) if p.punch_zoom else "[vface]null[vzoom]",
        sticker_graph,
        "[vstk]subtitles=f=subs.ass:fontsdir=fonts,format=yuv420p[vout]",
    ]
    if preview_at is not None:  # 미리보기: 그 시점 한 장만 (소리 없이)
        parts[-1] = parts[-1].replace("[vout]", f",trim=start={preview_at:.3f},scale=450:800[vout]")
        return ";\n".join(parts)
    parts.append(
        f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"aselect='{keep}',asetpts=N/SR/TB,{VOICE_CLEAN if p.voice_clean else ''}"
        f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[voice]")
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


def render_preview(p: Project, at: float, output_png: str) -> None:
    """at초 화면 한 장을 제목·목록·자막·스티커까지 넣어 PNG로 저장 (영상 만들기 전 확인용)."""
    at = max(0.0, min(at, p.duration - 0.05))
    render(p, output_png, preview_at=at)


def render(p: Project, output: str, on_progress: Callable[[float], None] | None = None,
           preview_at: float | None = None) -> None:
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

        args = ["-y"]
        if preview_at is not None:  # 그 조각 조금 앞으로 바로 건너뛰고, 원본 시간은 그대로 둔다
            first, _ = _preview_start(p, preview_at)
            args += ["-ss", f"{max(0.0, p.segments[first][0] - 1.0):.3f}", "-copyts"]
        args += ["-i", str(Path(p.source).resolve())]
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
        (work / "graph.txt").write_text(build_filter(p, face_graph, sticker_graph, preview_at), encoding="utf-8")

        if preview_at is not None:
            args += ["-/filter_complex", "graph.txt", "-map", "[vout]", "-frames:v", "1", str(Path(output).resolve())]
            run_ffmpeg(args, cwd=str(work), total_seconds=None, on_progress=None)
            return
        args += [
            "-/filter_complex", "graph.txt", "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-t", f"{p.duration:.3f}",
            "-movflags", "+faststart", str(Path(output).resolve()),
        ]
        run_ffmpeg(args, cwd=str(work), total_seconds=p.duration, on_progress=on_progress)

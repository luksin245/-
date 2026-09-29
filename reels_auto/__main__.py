"""인자 없이 실행하면 프로그램 창을 열고, 영상 경로를 주면 창 없이 바로 만든다.

python -m reels_auto                      # 창 열기
python -m reels_auto 원본.mp4             # 자동 분석 + 추천값 그대로 렌더링
python -m reels_auto 원본.mp4 --dump p.json --no-render   # 분석 결과만 저장
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def progress_fn(msg: str, frac: float) -> None:
    print(f"[{frac * 100:5.1f}%] {msg}", flush=True)


def cli(argv: list[str]) -> int:
    from .ass import TITLE_FONTS
    from .pipeline import analyze_video
    from .project import Project, Word
    from .render import render

    ap = argparse.ArgumentParser(prog="reels_auto")
    ap.add_argument("video", nargs="+", help="원본 영상 (--batch-dir 을 쓰면 여러 개)")
    ap.add_argument("--batch-dir", help="여러 영상을 한 번에 만들어 이 폴더에 저장")
    ap.add_argument("--preview", type=float, help="이 시점(초) 화면 한 장만 PNG로 저장 (-o 에 .png)")
    ap.add_argument("--no-voice-clean", action="store_true", help="목소리 잡음 줄이기 끄기")
    ap.add_argument("-o", "--output")
    ap.add_argument("--project", help="저장해 둔 편집 정보(json)로 렌더링")
    ap.add_argument("--words-json", help="음성 인식 대신 쓸 단어 목록(json, 테스트용)")
    ap.add_argument("--dump", help="분석 결과를 json으로 저장")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-bgm", action="store_true")
    ap.add_argument("--bgm")
    ap.add_argument("--retouch", choices=["끄기", "약하게", "보통", "강하게"])
    ap.add_argument("--slim", choices=["끄기", "약하게", "보통", "강하게"])
    ap.add_argument("--no-stickers", action="store_true")
    ap.add_argument("--no-zoom", action="store_true", help="컷마다 확대 효과 끄기")
    ap.add_argument("--title-font", choices=list(TITLE_FONTS), help="제목 글꼴")
    ap.add_argument("--keep-ng", action="store_true", help="다시 말한 부분(NG)을 빼지 않음")
    a = ap.parse_args(argv)
    if a.batch_dir:
        from . import prefs as prefs_mod
        from .batch import run_batch

        pr = prefs_mod.load()
        pr["remove_ng"] = not a.keep_ng
        for src, out, err in run_batch(a.video, a.batch_dir, pr, progress_fn):
            print(f"{src} → {out or '실패: ' + str(err)}")
        return 0
    if len(a.video) > 1:
        ap.error("영상을 여러 개 넣으려면 --batch-dir 을 같이 써주세요")
    a.video = a.video[0]

    progress = progress_fn

    if a.project:
        p = Project.from_json(Path(a.project).read_text(encoding="utf-8"))
    else:
        words = None
        if a.words_json:
            words = [Word(**w) for w in json.loads(Path(a.words_json).read_text(encoding="utf-8"))]
        p = analyze_video(a.video, progress, words=words, remove_ng=not a.keep_ng)
    if a.no_bgm:
        p.bgm = None
    elif a.bgm:
        p.bgm = a.bgm
    if a.retouch:
        p.retouch = a.retouch
    if a.slim:
        p.slim = a.slim
    if a.no_stickers:
        p.stickers = []
    if a.no_zoom:
        p.punch_zoom = False
    if a.no_voice_clean:
        p.voice_clean = False
    if a.title_font:
        p.title_font = a.title_font
    if a.dump:
        Path(a.dump).write_text(p.to_json(), encoding="utf-8")
    print(f"길이 {p.duration:.1f}초 · 컷 {len(p.segments)}개 · 자막 {len(p.captions)}줄 · 제목: {p.title}")
    print(f"도입부 유형: {p.hook_type}")
    for ng in p.ng_removed:
        print(f"  NG 제거: {ng}")
    print(f"얼굴 위치: {p.face_box} · 피부 보정: {p.retouch} · 얼굴형: {p.slim}")
    print(f"목록: {p.list_style} {p.list_count}개 · 스티커: " + ", ".join(f"{x.name}@{x.start}" for x in p.stickers))
    for t in p.tiers:
        print(f"  {t.tier}티어 @{t.time}: {t.text}")
    for q in p.quiz:
        print(f"  퀴즈 {q.start}~{q.end} 정답 {q.answer} @{q.reveal} 그림 {q.image}")
    for it in p.items:
        print(f"  {it.rank}. @{it.time}: {it.text}")
    if a.preview is not None:
        from .render import render_preview

        out = a.output or str(Path(a.video).with_name(Path(a.video).stem + "_미리보기.png"))
        render_preview(p, a.preview, out)
        print("미리보기 저장:", out)
    elif not a.no_render:
        out = a.output or str(Path(a.video).with_name(Path(a.video).stem + "_릴스.mp4"))
        render(p, out, lambda f: progress("영상 만드는 중", f))
        print("저장:", out)
    return 0


def main() -> None:
    # 창 모드 exe에서는 콘솔이 없어서 print가 실패하므로 버린다
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    # Windows 기본 콘솔 인코딩(cp1252 등)으로는 한글을 출력하다 멈추므로 UTF-8로 바꾼다
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) > 1:
        sys.exit(cli(sys.argv[1:]))
    from .gui import run

    run()


if __name__ == "__main__":
    main()

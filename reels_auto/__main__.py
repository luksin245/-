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


def cli(argv: list[str]) -> int:
    from .pipeline import analyze_video
    from .project import Project, Word
    from .render import render

    ap = argparse.ArgumentParser(prog="reels_auto")
    ap.add_argument("video")
    ap.add_argument("-o", "--output")
    ap.add_argument("--project", help="저장해 둔 편집 정보(json)로 렌더링")
    ap.add_argument("--words-json", help="음성 인식 대신 쓸 단어 목록(json, 테스트용)")
    ap.add_argument("--dump", help="분석 결과를 json으로 저장")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-bgm", action="store_true")
    ap.add_argument("--bgm")
    ap.add_argument("--retouch", choices=["끄기", "약하게", "보통", "강하게"])
    ap.add_argument("--slim", choices=["끄기", "약하게", "보통", "강하게"])
    a = ap.parse_args(argv)

    def progress(msg: str, frac: float) -> None:
        print(f"[{frac * 100:5.1f}%] {msg}", flush=True)

    if a.project:
        p = Project.from_json(Path(a.project).read_text(encoding="utf-8"))
    else:
        words = None
        if a.words_json:
            words = [Word(**w) for w in json.loads(Path(a.words_json).read_text(encoding="utf-8"))]
        p = analyze_video(a.video, progress, words=words)
    if a.no_bgm:
        p.bgm = None
    elif a.bgm:
        p.bgm = a.bgm
    if a.retouch:
        p.retouch = a.retouch
    if a.slim:
        p.slim = a.slim
    if a.dump:
        Path(a.dump).write_text(p.to_json(), encoding="utf-8")
    print(f"길이 {p.duration:.1f}초 · 컷 {len(p.segments)}개 · 자막 {len(p.captions)}줄 · 제목: {p.title}")
    print(f"얼굴 위치: {p.face_box} · 피부 보정: {p.retouch} · 얼굴형: {p.slim}")
    for it in p.items:
        print(f"  {it.rank}위 @{it.time}: {it.text}")
    if not a.no_render:
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
    if len(sys.argv) > 1:
        sys.exit(cli(sys.argv[1:]))
    from .gui import run

    run()


if __name__ == "__main__":
    main()

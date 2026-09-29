"""여러 원본 영상을 한 번에: 하나씩 자동 분석 → 기억해 둔 설정 입히기 → 영상 만들기."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import prefs as prefs_mod
from .pipeline import analyze_video
from .render import render

Progress = Callable[[str, float], None]


def output_path(source: str, folder: str) -> Path:
    out = Path(folder) / (Path(source).stem + "_릴스.mp4")
    n = 2
    while out.exists():  # 이미 있으면 덮어쓰지 않고 번호를 붙인다
        out = Path(folder) / f"{Path(source).stem}_릴스_{n}.mp4"
        n += 1
    return out


def run_batch(sources: list[str], folder: str, prefs: dict, on_progress: Progress | None = None
              ) -> list[tuple[str, str | None, str | None]]:
    """[(원본, 결과 파일 또는 None, 오류 메시지 또는 None)]. 하나가 실패해도 나머지는 계속 만든다."""
    report = on_progress or (lambda msg, frac: None)
    results = []
    total = len(sources)
    for k, src in enumerate(sources):
        name = Path(src).name
        base = k / total

        def step(msg: str, frac: float, lo: float, hi: float) -> None:
            report(f"[{k + 1}/{total}] {name} · {msg}", base + (lo + (hi - lo) * frac) / total)

        try:
            p = analyze_video(src, lambda m, f: step(m, f, 0.0, 0.6), remove_ng=bool(prefs.get("remove_ng", True)))
            prefs_mod.apply(p, prefs)
            out = output_path(src, folder)
            (out.with_suffix(".json")).write_text(p.to_json(), encoding="utf-8")  # 나중에 고쳐 만들 수 있게 편집 정보도 저장
            render(p, str(out), lambda f: step("영상 만드는 중", f, 0.6, 1.0))
            results.append((src, str(out), None))
        except Exception as e:  # 한 개가 실패해도 다음 영상으로
            results.append((src, None, str(e)))
    report("모두 끝났어요", 1.0)
    return results

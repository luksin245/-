"""퀴즈형 영상에 쓰는 정답 표시(초록 체크 / 빨간 X)와 카드 배경을 그려서 assets/quiz/ 에 저장한다.

사용법: python tools/make_quiz_assets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reels_auto.paths import app_dir  # noqa: E402

SS = 4  # 4배로 크게 그린 뒤 줄여서 가장자리를 매끈하게


def _save(name: str, img: np.ndarray, size: tuple[int, int]) -> None:
    out = app_dir() / "assets" / "quiz"
    out.mkdir(parents=True, exist_ok=True)
    small = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out / f"{name}.png"), small)
    print("saved", out / f"{name}.png")


def mark_o() -> None:
    n = 240 * SS
    img = np.zeros((n, n, 4), np.uint8)
    c = n // 2
    cv2.circle(img, (c, c), int(n * 0.47), (255, 255, 255, 255), -1, cv2.LINE_AA)  # 흰 테두리
    cv2.circle(img, (c, c), int(n * 0.43), (58, 200, 110, 255), -1, cv2.LINE_AA)  # 초록 (BGR)
    pts = np.array([[0.27, 0.52], [0.43, 0.68], [0.74, 0.34]]) * n
    cv2.polylines(img, [pts.astype(np.int32)], False, (255, 255, 255, 255), int(n * 0.085), cv2.LINE_AA)
    for x, y in pts:  # 둥근 끝
        cv2.circle(img, (int(x), int(y)), int(n * 0.0425), (255, 255, 255, 255), -1, cv2.LINE_AA)
    _save("mark_o", img, (240, 240))


def mark_x() -> None:
    n = 240 * SS
    img = np.zeros((n, n, 4), np.uint8)
    a, b = int(n * 0.2), int(n * 0.8)
    for color, width in (((255, 255, 255, 255), 0.17), ((85, 70, 232, 255), 0.12)):  # 흰 테두리 → 빨강
        for p, q in (((a, a), (b, b)), ((a, b), (b, a))):
            cv2.line(img, p, q, color, int(n * width), cv2.LINE_AA)
            for pt in (p, q):
                cv2.circle(img, pt, int(n * width / 2), color, -1, cv2.LINE_AA)
    _save("mark_x", img, (240, 240))


def card() -> None:
    w, h, r = 540 * SS, 300 * SS, 22 * SS
    img = np.zeros((h, w, 4), np.uint8)
    color = (255, 255, 255, 240)
    cv2.rectangle(img, (r, 0), (w - r, h), color, -1)
    cv2.rectangle(img, (0, r), (w, h - r), color, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(img, (cx, cy), r, color, -1, cv2.LINE_AA)
    _save("card", img, (540, 300))


if __name__ == "__main__":
    mark_o()
    mark_x()
    card()

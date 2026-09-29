"""컷마다 화면을 살짝 확대했다 원래대로 번갈아 주기 (점프컷 티 덜 나게).

쉬는 구간을 잘라낸 자리(원본에서 떨어진 두 조각이 붙는 곳)마다 확대/원래 크기를 바꾼다.
너무 짧은 구간은 앞 구간과 같은 크기로 둬서 화면이 정신없이 바뀌지 않게 한다.
확대할 때 얼굴이 화면에서 같은 자리에 머물도록 얼굴을 기준점으로 키운다.
"""
from __future__ import annotations

from .cutter import FPS

ZOOM = 1.12  # 확대 배율
MIN_GAP = 0.2  # 원본에서 이만큼(초) 이상 잘려 나간 곳만 "컷"으로 본다
MIN_BLOCK = 1.2  # 확대/원래 크기 한 번이 이보다 짧으면 바꾸지 않고 이어간다
W, H = 1080, 1920


def zoom_blocks(segments: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """확대할 구간들 (최종 영상 기준 프레임 번호 [시작, 끝))."""
    blocks: list[list[int]] = []  # [시작 프레임, 끝 프레임]
    t = 0.0
    prev_end = None
    for s, e in segments:
        f0, f1 = round(t * FPS), round((t + e - s) * FPS)
        is_cut = prev_end is not None and s - prev_end >= MIN_GAP
        if blocks and (not is_cut or (blocks[-1][1] - blocks[-1][0]) < MIN_BLOCK * FPS):
            blocks[-1][1] = f1
        else:
            blocks.append([f0, f1])
        t += e - s
        prev_end = e
    # 두 번째 덩어리부터 번갈아 확대 (첫 화면은 원래 크기)
    return [(a, b) for i, (a, b) in enumerate(blocks) if i % 2 == 1]


def build_graph(segments: list[tuple[float, float]], face_box: list[int] | None,
                label_in: str, label_out: str, frame0: int = 0) -> str:
    """frame0: 들어오는 첫 프레임이 최종 영상의 몇 번째 프레임인지 (미리보기용)."""
    blocks = zoom_blocks(segments)
    if not blocks:
        return f"[{label_in}]null[{label_out}]"
    on = "+".join(f"between(in+{frame0},{a},{b - 1})" for a, b in blocks)
    z = f"if({on},{ZOOM},1)"
    if face_box:
        fx, fy = face_box[0] + face_box[2] / 2, face_box[1] + face_box[3] / 2
    else:
        fx, fy = W / 2, H * 0.4
    # 얼굴 중심 (fx, fy)가 확대 전후 같은 위치에 오도록
    x = f"{fx:.0f}*(1-1/zoom)"
    y = f"{fy:.0f}*(1-1/zoom)"
    # zoompan 은 시간을 0부터 새로 매기므로 원래 시간으로 되돌린다
    return (f"[{label_in}]zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS},"
            f"setpts=(N+{frame0})/{FPS}/TB,setsar=1[{label_out}]")

"""얼굴 자동 보정: 얼굴 위치를 찾아서 그 부분만 자연스럽게 피부 결을 정돈한다.

고정 카메라 영상이라 얼굴 위치가 거의 안 움직이므로, 몇 장면에서 찾은 얼굴 위치의
중앙값을 영상 전체에 쓴다. 가장자리는 부드럽게 흐려지는 타원 마스크로 섞는다.
"""
from __future__ import annotations

import subprocess

import numpy as np

from .media import _NO_WINDOW
from .paths import ffmpeg_path

OUT_W, OUT_H = 1080, 1920
# 원본을 세로 1080x1920로 맞추는 방법 (render와 똑같이 써야 얼굴 위치가 맞는다)
FIT = ("scale='trunc(iw*sar/2)*2':ih,setsar=1,"
       f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1")

# 보정 강도별 설정: (bilateral 공간 크기, 색 차이 허용, 마스크 최대 불투명도, 밝기, 채도)
LEVELS = {
    "끄기": None,
    "약하게": (5, 0.06, 0.65, 0.012, 1.03),
    "보통": (8, 0.09, 0.8, 0.02, 1.05),
    "강하게": (12, 0.13, 0.9, 0.03, 1.06),
}
DEFAULT_LEVEL = "약하게"


def _grab_gray(source: str, t: float) -> np.ndarray | None:
    cmd = [ffmpeg_path(), "-nostdin", "-v", "error", "-ss", f"{t:.3f}", "-i", source, "-frames:v", "1",
           "-vf", FIT + ",format=gray", "-f", "rawvideo", "pipe:1"]
    out = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW).stdout
    if len(out) != OUT_W * OUT_H:
        return None
    return np.frombuffer(out, np.uint8).reshape(OUT_H, OUT_W)


def detect_face_box(source: str, segments: list[tuple[float, float]], samples: int = 8) -> list[int] | None:
    """출력 화면(1080x1920) 기준 얼굴 상자 [x, y, w, h]. 못 찾으면 None."""
    try:
        import cv2
    except ImportError:
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    total = sum(e - s for s, e in segments)
    if total <= 0:
        return None
    boxes = []
    for k in range(samples):
        # 남길 구간 안에서 고르게 뽑는다
        target, acc = total * (k + 0.5) / samples, 0.0
        t = segments[0][0]
        for s, e in segments:
            if acc + (e - s) >= target:
                t = s + (target - acc)
                break
            acc += e - s
        gray = _grab_gray(source, t)
        if gray is None:
            continue
        small = cv2.resize(gray, (OUT_W // 3, OUT_H // 3))
        faces = cascade.detectMultiScale(small, scaleFactor=1.1, minNeighbors=6, minSize=(50, 50))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            boxes.append([x * 3, y * 3, w * 3, h * 3])
    if len(boxes) < max(2, samples // 3):
        return None
    return [int(v) for v in np.median(np.array(boxes), axis=0)]


def region(box: list[int]) -> tuple[int, int, int, int]:
    """보정할 영역: 얼굴 상자를 넉넉히 키운 것 (움직임과 턱선, 이마까지 포함). 짝수 크기."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2 + h * 0.05
    rw, rh = w * 1.7, h * 2.0
    x0 = int(max(0, cx - rw / 2)) // 2 * 2
    y0 = int(max(0, cy - rh / 2)) // 2 * 2
    x1 = int(min(OUT_W, cx + rw / 2)) // 2 * 2
    y1 = int(min(OUT_H, cy + rh / 2)) // 2 * 2
    return x0, y0, x1 - x0, y1 - y0


def write_mask(path: str, w: int, h: int, opacity: float) -> None:
    """가장자리가 부드러운 타원 마스크를 흑백 PGM으로 저장."""
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    alpha = np.clip((1.0 - d) / 0.35, 0, 1)  # 바깥 35%는 서서히 사라짐
    alpha = alpha * alpha * (3 - 2 * alpha) * opacity
    img = (alpha * 255).astype(np.uint8)
    with open(path, "wb") as f:
        f.write(f"P5\n{w} {h}\n255\n".encode())
        f.write(img.tobytes())


SLIM_LEVELS = {"끄기": 0.0, "약하게": 0.05, "보통": 0.08, "강하게": 0.11}
DEFAULT_SLIM = "약하게"


def _smooth(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def write_slim_maps(xpath: str, ypath: str, box: list[int], strength: float) -> None:
    """얼굴 아래쪽(볼·턱)을 가운데로 살짝 모으는 좌표 변환표(remap용 16비트 PGM)를 만든다.

    출력 화소 (x, y)는 원본의 cx + (x-cx)*(1+s) 위치를 가져온다 → 그 부분이 1/(1+s)배로 좁아진다.
    영역 가장자리에서는 s가 0이 되도록 해서 바깥과 이음새가 생기지 않는다.
    """
    rx, ry, rw, rh = region(box)
    fx, fy, fw, fh = box
    yy, xx = np.mgrid[0:rh, 0:rw].astype(np.float64)
    cx = fx + fw / 2 - rx
    gx, gy = xx + rx, yy + ry  # 화면 좌표
    # 세로 가중치: 눈 아래(얼굴 45%)부터 턱(85%)까지 커지고, 턱 아래로 사라짐
    top, jaw, below = fy + fh * 0.45, fy + fh * 0.85, fy + fh * 1.25
    wy = _smooth((gy - top) / (jaw - top)) * (1 - _smooth((gy - jaw) / (below - jaw)))
    # 가로 가중치: 얼굴 폭 안쪽은 그대로 적용, 얼굴 밖(배경)으로 갈수록 0
    half = fw / 2
    wx = 1 - _smooth((np.abs(gx - (fx + fw / 2)) - half * 0.9) / (half * 0.6))
    s = strength * wy * wx
    src_x = cx + (xx - cx) * (1 + s)
    src_x = np.clip(src_x, 0, rw - 1)
    for path, arr in ((xpath, src_x), (ypath, yy)):
        img = np.round(arr).astype(">u2")
        with open(path, "wb") as f:
            f.write(f"P5\n{rw} {rh}\n65535\n".encode())
            f.write(img.tobytes())


def build_graph(workdir: str, level: str, slim: str, box: list[int] | None, first_input: int) -> tuple[str, list[str]]:
    """[vfit] → [vface] 필터 그래프 조각과, 추가로 넣어야 할 이미지 입력 파일 목록을 돌려준다."""
    import os

    params = LEVELS.get(level)
    strength = SLIM_LEVELS.get(slim, 0.0)
    parts: list[str] = []
    inputs: list[str] = []
    cur = "vfit"
    if params is not None:
        parts.append(f"[{cur}]eq=brightness={params[3]}:saturation={params[4]}[vtone]")
        cur = "vtone"
    if box is not None:
        x, y, w, h = region(box)
        if strength > 0:
            xm, ym = os.path.join(workdir, "slim_x.pgm"), os.path.join(workdir, "slim_y.pgm")
            write_slim_maps(xm, ym, box, strength)
            ix, iy = first_input + len(inputs), first_input + len(inputs) + 1
            inputs += ["slim_x.pgm", "slim_y.pgm"]
            parts.append(f"[{cur}]split=2[vsb][vsf];[vsf]crop={w}:{h}:{x}:{y},format=yuv444p[vsc];"
                         f"[vsc][{ix}:v][{iy}:v]remap=fill=black[vsr];"
                         f"[vsb][vsr]overlay={x}:{y}[vslim]")
            cur = "vslim"
        if params is not None:
            sigma_s, sigma_r, opacity = params[0], params[1], params[2]
            write_mask(os.path.join(workdir, "face_mask.pgm"), w, h, opacity)
            im = first_input + len(inputs)
            inputs.append("face_mask.pgm")
            parts.append(f"[{cur}]split=2[vbb][vbf];"
                         f"[vbf]crop={w}:{h}:{x}:{y},bilateral=sigmaS={sigma_s}:sigmaR={sigma_r},format=yuva420p[vbs];"
                         f"[{im}:v]format=gray[vmask];[vbs][vmask]alphamerge[vba];"
                         f"[vbb][vba]overlay={x}:{y}:format=auto[vsmooth]")
            cur = "vsmooth"
    parts.append(f"[{cur}]null[vface]")
    return ";\n".join(parts), inputs

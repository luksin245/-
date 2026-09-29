"""말하는 내용에 맞는 그림 스티커를 골라서, 그 순간 화면에 톡 튀어나오게 한다.

자막에 키워드(예: "연차" → 달력, "퇴직금" → 돈주머니)가 나오면 그 자막이 시작될 때 스티커를 띄운다.
너무 자주 나오지 않도록 스티커 사이에 간격을 둔다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import app_dir
from .project import Caption, Sticker

SIZE = 300  # 화면(1080x1920)에서 스티커 크기
CENTER = (560, 1300)  # 스티커 중심 위치 (자막 바로 위, 가슴 높이)
MIN_SHOW, MAX_SHOW = 2.0, 3.5  # 한 번 보여주는 시간(초)
GAP = 2.5  # 스티커 사이 최소 빈 시간 (레퍼런스처럼 가끔씩만)
SAME_AGAIN = 8.0  # 같은 스티커를 다시 쓰기 전 최소 간격


def stickers_dir() -> Path:
    return app_dir() / "assets" / "stickers"


def load_table() -> dict[str, list[str]]:
    path = stickers_dir() / "stickers.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def names() -> list[str]:
    return sorted(p.stem for p in stickers_dir().glob("*.png")) if stickers_dir().exists() else []


def match(text: str, table: dict[str, list[str]]) -> str | None:
    """자막에서 가장 긴(구체적인) 키워드를 가진 스티커를 고른다."""
    best, best_len = None, 0
    compact = text.replace(" ", "")
    for name, keywords in table.items():
        for kw in keywords:
            if (kw in text or kw.replace(" ", "") in compact) and len(kw) > best_len:
                best, best_len = name, len(kw)
    return best


def auto_stickers(captions: list[Caption], duration: float) -> list[Sticker]:
    table = load_table()
    out: list[Sticker] = []
    free_at = 0.0
    last_used: dict[str, float] = {}
    for i, c in enumerate(captions):
        if c.start < free_at:
            continue
        name = match(c.text, table)
        if not name or c.start - last_used.get(name, -99) < SAME_AGAIN:
            continue
        # 같은 이야기가 이어지는 동안(최대 MAX_SHOW초) 보여준다
        end = c.start + MIN_SHOW
        for nxt in captions[i + 1:]:
            if nxt.start >= c.start + MAX_SHOW or match(nxt.text, table) not in (None, name):
                break
            end = max(end, min(nxt.end, c.start + MAX_SHOW))
        end = min(end, duration)
        if end - c.start < 1.0:
            continue
        out.append(Sticker(round(c.start, 2), round(end, 2), name))
        last_used[name] = c.start
        free_at = end + GAP
    return out


@dataclass
class Overlay:
    """영상 위에 올릴 그림 한 장."""
    path: str
    start: float
    end: float
    cx: int  # 중심 위치
    cy: int
    width: int
    height: int | None = None  # 주면 그 크기로 꽉 차게 잘라 맞춤(사진용)
    pop: bool = True  # 톡 튀어나오는 효과


def sticker_overlays(stickers: list[Sticker]) -> list[Overlay]:
    return [Overlay(str(stickers_dir() / f"{s.name}.png"), s.start, s.end, CENTER[0], CENTER[1], SIZE)
            for s in stickers]


def build_graph(overlays: list[Overlay], label_in: str, label_out: str, first_input: int) -> tuple[str, list[str]]:
    """[label_in] 위에 그림들을 차례로 올린 그래프 조각과, 추가로 넣을 이미지 파일 목록."""
    parts: list[str] = []
    files: list[str] = []
    cur = label_in
    for k, ov in enumerate(o for o in overlays if Path(o.path).exists() and o.end > o.start):
        a, b = ov.start, ov.end
        idx = first_input + len(files)
        files.append(ov.path)
        if ov.height:
            fit = (f"scale={ov.width}:{ov.height}:force_original_aspect_ratio=increase,"
                   f"crop={ov.width}:{ov.height},setsar=1")
        else:
            fit = f"scale={ov.width}:-2,setsar=1"
        chain = f"[{idx}:v]format=rgba,{fit}"
        if ov.pop:
            # 톡 튀어나오는 효과(0.6배 → 1.1배 → 1배)를 8프레임짜리 짧은 클립으로 만들고, 마지막 프레임을 계속 보여준다
            pop = "if(lt(t,0.12),0.6+0.5*t/0.12,if(lt(t,0.22),1.1-0.1*(t-0.12)/0.1,1))"
            chain += f",loop=loop=7:size=1,setpts=N/30/TB,scale=w='trunc(iw*{pop}/2)*2':h=-2:eval=frame"
        parts.append(f"{chain},setpts=PTS+{a:.3f}/TB[ov{k}]")
        nxt = f"vov{k}"
        parts.append(f"[{cur}][ov{k}]overlay=x='{ov.cx}-overlay_w/2':y='{ov.cy}-overlay_h/2':"
                     f"enable='between(t,{a:.3f},{b:.3f})':eval=frame:eof_action=repeat[{nxt}]")
        cur = nxt
    parts.append(f"[{cur}]null[{label_out}]")
    return ";\n".join(parts), files

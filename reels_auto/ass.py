"""레퍼런스 스타일(제목 / TOP 5 패널 / 자막)을 ASS 자막 파일로 만든다.

화면 크기 1080x1920 기준 좌표. 레퍼런스 영상에서 잰 위치를 그대로 옮겼다.
"""
from __future__ import annotations

from .project import Project

W, H = 1080, 1920

TITLE_FONT = "NanumMyeongjoExtraBold"
SUB_FONT = "Pretendard Medium"
LIST_FONT = "Pretendard SemiBold"

TITLE_TOP_Y = 248
PANEL = (80, 906, 1000, 1456)  # x0, y0, x1, y1
PANEL_RADIUS = 28
ROW_Y = [984 + i * 104 for i in range(5)]  # 1위~5위 줄의 세로 중심
NUM_X, ITEM_X = 110, 178
CAPTION_Y_TOP = 1500
CAPTION_Y_PLAIN = 1500

HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{TITLE_FONT},78,&H00FFFFFF,&H00FFFFFF,&H50000000,&H90000000,0,0,0,0,100,100,0,0,1,1.5,3,2,40,40,0,1
Style: Caption,{SUB_FONT},44,&H00141414,&H00141414,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,9,0,5,40,40,0,1
Style: Panel,Arial,20,&H70FFFFFF,&H70FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Num,{LIST_FONT},58,&H00141414,&H00141414,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: Item,{LIST_FONT},30,&H00141414,&H00141414,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(sec: float) -> str:
    cs = max(0, int(round(sec * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(text: str) -> str:
    return text.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def wrap_title(title: str, max_line: int = 17) -> str:
    """길면 가운데 가까운 띄어쓰기에서 두 줄로 나눈다. 사용자가 줄바꿈을 넣었으면 그대로 쓴다."""
    title = title.strip()
    if "\n" in title or len(title) <= max_line:
        return title
    spaces = [i for i, ch in enumerate(title) if ch == " "]
    if not spaces:
        return title
    mid = len(title) / 2
    cut = min(spaces, key=lambda i: abs(i - mid))
    return title[:cut] + "\n" + title[cut + 1:]


def rounded_rect(w: int, h: int, r: int) -> str:
    k = r * 0.45  # 곡선 조절점
    return (f"m {r} 0 l {w - r} 0 b {w - k} 0 {w} {k} {w} {r} l {w} {h - r} "
            f"b {w} {h - k} {w - k} {h} {w - r} {h} l {r} {h} b {k} {h} 0 {h - k} 0 {h - r} "
            f"l 0 {r} b 0 {k} {k} 0 {r} 0")


def line(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}\n"


def build_ass(p: Project) -> str:
    out = [HEADER]
    end = p.duration
    use_top = p.top_mode and bool(p.items)

    if p.title.strip():
        out.append(line(3, 0, end, "Title", f"{{\\an8\\pos({W // 2},{TITLE_TOP_Y})}}" + esc(wrap_title(p.title))))

    if use_top:
        x0, y0, x1, y1 = PANEL
        out.append(line(0, 0, end, "Panel", f"{{\\an7\\pos({x0},{y0})\\p1}}" + rounded_rect(x1 - x0, y1 - y0, PANEL_RADIUS)))
        for i, y in enumerate(ROW_Y):
            out.append(line(1, 0, end, "Num", f"{{\\pos({NUM_X},{y})}}{i + 1}."))
        for it in p.items:
            text = it.text.strip()
            if it.time is None or not text:
                continue
            y = ROW_Y[it.rank - 1]
            size = 30 if len(text) <= 22 else max(20, int(30 * 22 / len(text)))
            tag = f"{{\\pos({ITEM_X},{y})\\fs{size}}}"
            # 타이핑 효과: 글자가 하나씩 나타남
            step = min(0.06, 0.45 / len(text))
            t = max(0.0, it.time)
            for k in range(1, len(text) + 1):
                t_next = t + step if k < len(text) else end
                if t >= end:
                    break
                out.append(line(1, t, min(t_next, end), "Item", tag + esc(text[:k])))
                t = t_next

    y = CAPTION_Y_TOP if use_top else CAPTION_Y_PLAIN
    for c in p.captions:
        if c.text.strip() and c.end > c.start:
            out.append(line(2, c.start, min(c.end, end), "Caption", f"{{\\an5\\pos({W // 2},{y})}}" + esc(c.text)))
    return "".join(out)

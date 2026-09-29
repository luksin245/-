"""레퍼런스 스타일(제목 / 목록 패널 / 자막)을 ASS 자막 파일로 만든다.

화면 크기 1080x1920 기준 좌표. 레퍼런스 영상에서 잰 위치를 그대로 옮겼다.
"""
from __future__ import annotations

from . import tier as tierlist
from .project import Project

W, H = 1080, 1920

# 제목 글꼴: 화면에 보이는 이름 → (글꼴 이름, 크기). 굵기·모양이 달라 보기 좋은 크기가 조금씩 다르다.
TITLE_FONTS = {
    "프리텐다드": ("Pretendard ExtraBold", 76),
    "수트": ("SUIT ExtraBold", 76),
    "노토 세리프": ("Noto Serif KR Black", 74),
    "고운바탕": ("Gowun Batang", 78),
    "검은고딕": ("Black Han Sans", 78),
    "나눔명조": ("NanumMyeongjoExtraBold", 78),
    "원티드 산스": ("Wanted Sans ExtraBold", 76),
    "나눔스퀘어라운드": ("NanumSquareRound ExtraBold", 76),
    "고딕 A1": ("Gothic A1 ExtraBold", 74),
    "노토 산스": ("Noto Sans KR Black", 74),
    "나눔고딕": ("NanumGothicExtraBold", 76),
    "함렛": ("Hahmlet ExtraBold", 74),
    "송명": ("Song Myung", 80),
    "고운돋움": ("Gowun Dodum", 78),
    "해바라기": ("Sunflower", 80),
    "도현": ("Do Hyeon", 82),
    "주아": ("Jua", 80),
    "베이글": ("Bagel Fat One", 76),
    "가석": ("Gasoek One", 76),
    "오르빗": ("Orbit", 74),
    "디필레이아": ("Diphylleia", 78),
    "나눔손글씨 펜": ("Nanum Pen", 96),
}
DEFAULT_TITLE_FONT = "프리텐다드"
SUB_FONT = "Pretendard Medium"
LIST_FONT = "Pretendard SemiBold"

TITLE_TOP_Y = 248
# 목록 패널: 크기는 항상 같고(레퍼런스 5줄 기준), 줄들을 패널 안 가운데에 모은다.
# (레퍼런스의 3가지 영상도 같은 크기 패널에 3줄이 가운데 정렬돼 있다)
PANEL = (80, 906, 1000, 1456)  # x0, y0, x1, y1
ROWS_CENTER = 1192  # 5줄일 때 첫 줄 984, 마지막 줄 1400의 가운데
PANEL_RADIUS = 28


def panel_layout(count: int) -> tuple[tuple[int, int, int, int], list[int]]:
    """(패널 x0, y0, x1, y1), 각 줄의 세로 중심 목록 (1번이 맨 위)."""
    step = 104 if count <= 5 else int(104 * 4 / (count - 1))  # 6줄 이상이면 간격을 좁혀 패널 안에 맞춘다
    # 레퍼런스 측정값: 5줄이면 가운데 1192, 3줄이면 1168 (줄이 적을수록 살짝 위로)
    center = ROWS_CENTER - max(0, 5 - count) * 12
    top = center - (count - 1) * step / 2
    return PANEL, [int(top + i * step) for i in range(count)]


NUM_X, ITEM_X = 110, 178
ITEM_SIZE = 46  # 목록 글자 크기
ITEM_FIT = 16  # 이 글자 수보다 길면 패널 안에 들어가게 줄인다
CAPTION_Y = 1500

HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{{TITLE_FONT}},{{TITLE_SIZE}},&H00FFFFFF,&H00FFFFFF,&H50000000,&H90000000,0,0,0,0,100,100,0,0,1,1.5,3,2,40,40,0,1
Style: Caption,{SUB_FONT},44,&H00141414,&H00141414,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,9,0,5,40,40,0,1
Style: Panel,Arial,20,&H70FFFFFF,&H70FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Num,{LIST_FONT},58,&H00141414,&H00141414,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: TierLetter,{LIST_FONT},50,&H00202020,&H00202020,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
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
    # 레퍼런스 제목은 첫 줄이 조금 더 길다 ("연차 못 쓰게 하는 사장님들이 / 가장 많이 하는 말 TOP 5")
    target = len(title) * 0.57
    cut = min((i for i in spaces if i <= max_line) or spaces, key=lambda i: abs(i - target))
    return title[:cut] + "\n" + title[cut + 1:]


def rounded_rect(w: int, h: int, r: int) -> str:
    k = r * 0.45  # 곡선 조절점
    return (f"m {r} 0 l {w - r} 0 b {w - k} 0 {w} {k} {w} {r} l {w} {h - r} "
            f"b {w} {h - k} {w - k} {h} {w - r} {h} l {r} {h} b {k} {h} 0 {h - k} 0 {h - r} "
            f"l 0 {r} b 0 {k} {k} 0 {r} 0")


def line(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}\n"


def header(title_font: str = DEFAULT_TITLE_FONT) -> str:
    name, size = TITLE_FONTS.get(title_font, TITLE_FONTS[DEFAULT_TITLE_FONT])
    return HEADER.replace("{TITLE_FONT}", name).replace("{TITLE_SIZE}", str(size))


def build_ass(p: Project) -> str:
    out = [header(p.title_font)]
    end = p.duration
    count = min(max(p.list_count, 0), 7)
    show_list = p.list_style in ("rank", "ordinal") and count >= 2

    if p.title.strip():
        out.append(line(3, 0, end, "Title", f"{{\\an8\\pos({W // 2},{TITLE_TOP_Y})}}" + esc(wrap_title(p.title))))

    if show_list:
        (x0, y0, x1, y1), rows = panel_layout(count)
        out.append(line(0, 0, end, "Panel", f"{{\\an7\\pos({x0},{y0})\\p1}}" + rounded_rect(x1 - x0, y1 - y0, PANEL_RADIUS)))
        for i, y in enumerate(rows):
            out.append(line(1, 0, end, "Num", f"{{\\pos({NUM_X},{y})}}{i + 1}."))
        for it in p.items:
            text = it.text.strip()
            if it.time is None or not text or not 1 <= it.rank <= count:
                continue
            y = rows[it.rank - 1]
            size = ITEM_SIZE if len(text) <= ITEM_FIT else max(30, int(ITEM_SIZE * ITEM_FIT / len(text)))
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

    if p.list_style == "tier":
        out += tier_lines(p, end)

    y = CAPTION_Y
    for c in p.captions:
        if c.text.strip() and c.end > c.start:
            out.append(line(2, c.start, min(c.end, end), "Caption", f"{{\\an5\\pos({W // 2},{y})}}" + esc(c.text)))
    return "".join(out)


def _ass_color(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}&"


def _typing(layer: int, start: float, end: float, tag: str, text: str) -> list[str]:
    out = []
    step = min(0.06, 0.45 / max(1, len(text)))
    t = max(0.0, start)
    for k in range(1, len(text) + 1):
        t_next = t + step if k < len(text) else end
        if t >= end:
            break
        out.append(line(layer, t, min(t_next, end), "Item", tag + esc(text[:k])))
        t = t_next
    return out


def tier_lines(p: Project, end: float) -> list[str]:
    """티어리스트: 왼쪽 색 칸(S/A/B/C) + 오른쪽 반투명 영역에 항목이 옆으로 붙는다."""
    out = []
    top, bottom = tierlist.ROWS["S"][0], tierlist.ROWS["C"][1]
    x0, x1 = tierlist.LABEL_X1, tierlist.AREA_X1
    out.append(line(0, 0, end, "Panel", f"{{\\an7\\pos({x0},{top})\\p1}}m 0 0 l {x1 - x0} 0 {x1 - x0} {bottom - top} 0 {bottom - top}"))
    for name, (y0, y1) in tierlist.ROWS.items():
        w, h = tierlist.LABEL_X1 - tierlist.LABEL_X0, y1 - y0
        color = _ass_color(tierlist.COLORS[name])
        out.append(line(1, 0, end, "Panel", f"{{\\an7\\pos({tierlist.LABEL_X0},{y0})\\1c{color}\\1a&H00&\\p1}}m 0 0 l {w} 0 {w} {h} 0 {h}"))
        out.append(line(2, 0, end, "TierLetter", f"{{\\pos({(tierlist.LABEL_X0 + tierlist.LABEL_X1) // 2},{(y0 + y1) // 2})}}{name}"))
    cursor = {name: tierlist.ITEM_X0 for name in tierlist.TIERS}
    for it in sorted(p.tiers, key=lambda x: x.time):
        text = it.text.strip()
        if it.tier not in tierlist.ROWS or not text:
            continue
        size = 26
        width = tierlist.text_width(text, size)
        x = cursor[it.tier]
        if x + width > tierlist.AREA_X1 - 10:  # 줄이 꽉 차면 글자를 줄여서라도 넣는다
            size = max(18, int(size * (tierlist.AREA_X1 - 10 - x) / width))
            width = tierlist.text_width(text, size)
        y = sum(tierlist.ROWS[it.tier]) // 2
        out += _typing(2, it.time, end, f"{{\\an4\\pos({int(x)},{y})\\fs{size}}}", text)
        cursor[it.tier] = x + width + tierlist.ITEM_GAP
    return out

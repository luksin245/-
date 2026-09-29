"""티어리스트형: "욕설, S티어" 처럼 말하면 S/A/B/C 줄에 항목이 차례로 붙는다.

레퍼런스(9·10. 직장태도 티어)에서 잰 배치: 왼쪽에 색 칸(S 빨강, A 주황, B 노랑, C 초록),
오른쪽 반투명 흰 영역에 항목이 옆으로 이어 붙는다.
"""
from __future__ import annotations

import re

from .project import TierItem, Word

TIERS = ("S", "A", "B", "C")
# (칸 위쪽, 칸 아래쪽) 세로 위치 — 레퍼런스에서 잰 값
ROWS = {"S": (918, 1050), "A": (1052, 1188), "B": (1190, 1316), "C": (1318, 1456)}
LABEL_X0, LABEL_X1 = 96, 238
AREA_X1 = 984
ITEM_X0 = 298
ITEM_GAP = 64
# 색 (R, G, B)
COLORS = {"S": (214, 102, 101), "A": (208, 167, 103), "B": (205, 185, 97), "C": (140, 203, 116)}

KOREAN_LETTER = {"에스": "S", "에이": "A", "비": "B", "씨": "C", "시": "C"}
TIER_IN_WORD = re.compile(r"^(S|A|B|C|에스|에이|비|씨|시)\s*[-~]?\s*(티어|티여|tier)", re.I)
LETTER_ONLY = re.compile(r"^(S|A|B|C|에스|에이|비|씨)[-~]?$", re.I)
SENTENCE_END = re.compile(r"[.?!]$")


def _letter(raw: str) -> str:
    raw = raw.upper() if raw.isascii() else raw
    return KOREAN_LETTER.get(raw, raw)


def _mentions(words: list[Word]) -> list[tuple[int, int, str]]:
    """(표시어 시작 단어, 끝 단어, 등급)."""
    out = []
    i = 0
    while i < len(words):
        t = words[i].text.strip()
        m = TIER_IN_WORD.match(t)
        if m:
            out.append((i, i, _letter(m.group(1))))
        elif LETTER_ONLY.match(t) and i + 1 < len(words) and re.match(r"^(티어|티여|tier)", words[i + 1].text.strip(), re.I):
            out.append((i, i + 1, _letter(LETTER_ONLY.match(t).group(1))))
            i += 1
        i += 1
    return out


def _clean(text: str) -> str:
    return text.strip().strip(".,?!")


def detect_tiers(words: list[Word]) -> list[TierItem]:
    """등급을 3번 이상 말하면 티어리스트형으로 본다."""
    marks = _mentions(words)
    if len(marks) < 3:
        return []
    items: list[TierItem] = []
    prev_end = -1
    for n, (a, b, tier) in enumerate(marks):
        # 등급 바로 앞, 같은 문장 안의 짧은 말을 항목으로 ("회식 불참, C티어")
        before = []
        k = a - 1
        while k > prev_end and len(before) < 3 and not SENTENCE_END.search(words[k].text.strip()):
            before.insert(0, words[k].text.strip())
            k -= 1
        if before:
            text = _clean(" ".join(before))
        else:
            # 등급을 먼저 말한 경우 ("S티어, 욕설.") 바로 뒤의 말
            after = []
            nxt = marks[n + 1][0] if n + 1 < len(marks) else len(words)
            for w in words[b + 1: min(nxt, b + 4)]:
                after.append(w.text.strip())
                if SENTENCE_END.search(after[-1]) or after[-1].endswith(","):
                    break
            text = _clean(" ".join(after))
        items.append(TierItem(tier, round(words[b].end, 2), text[:14]))
        prev_end = b
    return items


def text_width(text: str, size: int) -> float:
    w = 0.0
    for ch in text:
        if ch == " ":
            w += size * 0.3
        elif ord(ch) < 128:
            w += size * 0.6
        else:
            w += size * 0.98
    return w

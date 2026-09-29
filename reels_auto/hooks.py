"""도입부 후킹 멘트 유형 알아보기. 유형 정리는 docs/hook-patterns.md 참고."""
from __future__ import annotations

import re

from .project import Word

TYPES = {
    "top": "TOP N 예고형",
    "ask_expert": "노무사님 질문형",
    "echo": "되묻기 공감형",
    "money": "숫자·돈 계산형",
    "myth": "오해 깨기(비교 반전)형",
    "note_this": "지금 받아 적어형",
    "direct": "바로 본론형",
    "other": "기타",
}


def classify(words: list[Word], list_style: str = "none") -> str:
    """도입부(앞쪽 약 25단어)를 보고 후킹 유형 이름을 돌려준다."""
    head = " ".join(w.text.strip() for w in words[:25])
    first = re.split(r"(?<=[.?!])\s", head, maxsplit=1)[0]
    if re.search(r"(님|선생님)\s*[,]?", first) and "?" in head[:120]:
        return TYPES["ask_expert"]
    if re.search(r"(TOP|탑)\s*\d|1위는", head, re.I) or re.search(r"([0-9]|두|세|네|다섯)\s*가지", first):
        return TYPES["top"]
    if re.search(r"받아\s*적어|해당\s*되면|해당하면", head):
        return TYPES["note_this"]
    if re.search(r"\d+\s*만\s*원", head) and re.search(r"얼마", head):
        return TYPES["money"]
    if re.search(r"(다고|라고|지|냐)\?$", first):
        return TYPES["echo"]
    if list_style in ("quiz", "tier"):
        return TYPES["direct"]
    if re.search(r"착각|오해|아니라", head) or len(re.findall(r"\d+일", head)) >= 2:
        return TYPES["myth"]
    return TYPES["other"]

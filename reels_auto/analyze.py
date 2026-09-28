"""음성 인식 결과로 자막, TOP 5 항목, 제목을 자동으로 만든다."""
from __future__ import annotations

import re

from .project import Caption, RankItem, Word

SENTENCE_END = re.compile(r"[.?!]$")
KOREAN_NUM = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5}
RANK_DIGIT = re.compile(r"(?<![0-9])([1-5])\s*위")
RANK_KOREAN = re.compile(r"^(일|이|삼|사|오)위")


def _clean(text: str) -> str:
    return text.strip().rstrip(".,")


def make_captions(words: list[Word], duration: float, max_chars: int = 12, max_gap: float = 0.35) -> list[Caption]:
    """레퍼런스처럼 짧은 구절(12글자 안팎) 단위로 자막을 나눈다."""
    groups: list[list[Word]] = []
    for w in words:
        text = w.text.strip()
        if not text:
            continue
        if groups:
            cur = groups[-1]
            length = sum(len(x.text.strip().replace(" ", "")) for x in cur) + len(text)
            prev = cur[-1]
            # "돼", "보자" 같은 짧은 끝말이 혼자 한 줄이 되지 않도록 조금 넘쳐도 붙인다
            too_long = length > max_chars and not (len(text) <= 2 and length <= max_chars + 3)
            if too_long or re.search(r"[.?!,]$", prev.text.strip()) or w.start - prev.end > max_gap:
                groups.append([w])
                continue
            cur.append(w)
        else:
            groups.append([w])

    caps: list[Caption] = []
    for i, g in enumerate(groups):
        start = 0.0 if i == 0 else g[0].start
        end = groups[i + 1][0].start if i + 1 < len(groups) else duration
        text = _clean(" ".join(x.text.strip() for x in g))
        if text:
            caps.append(Caption(start, max(end, start + 0.1), text))
    return caps


def retime_captions(texts: list[str], old: list[Caption], duration: float) -> list[Caption]:
    """사용자가 자막 줄을 고쳤을 때 타이밍을 다시 맞춘다."""
    texts = [t.strip() for t in texts if t.strip()]
    if len(texts) == len(old):
        return [Caption(c.start, c.end, t) for c, t in zip(old, texts)]
    total = sum(len(t) for t in texts) or 1
    caps, t0 = [], 0.0
    for t in texts:
        t1 = t0 + duration * len(t) / total
        caps.append(Caption(t0, t1, t))
        t0 = t1
    return caps


def _rank_of(words: list[Word], i: int) -> int | None:
    text = words[i].text.strip()
    m = RANK_DIGIT.search(text)
    if m:
        return int(m.group(1))
    m = RANK_KOREAN.match(text)
    if m:
        return KOREAN_NUM[m.group(1)]
    # "5" "위는" 처럼 나뉘어 인식된 경우
    if i + 1 < len(words) and re.fullmatch(r"[1-5]", text) and words[i + 1].text.strip().startswith("위"):
        return int(text)
    return None


def _sentence_end_after(words: list[Word], i: int, limit: int = 14) -> int:
    for j in range(i, min(len(words), i + limit)):
        if SENTENCE_END.search(words[j].text.strip()):
            return j
        if j + 1 < len(words) and words[j + 1].start - words[j].end > 0.4:
            return j
    return min(len(words) - 1, i + limit)


def detect_ranks(words: list[Word]) -> list[RankItem]:
    """"5위는? … 4위는? … 마지막 1위" 흐름을 찾아서 항목과 등장 시점을 추천한다.

    3개 이상 찾으면 TOP 5 목록을 쓰고, 아니면 빈 목록을 돌려준다.
    """
    marks = [(i, r) for i in range(len(words)) if (r := _rank_of(words, i)) is not None]
    chosen: dict[int, int] = {}
    prev = -1
    for rank in (5, 4, 3, 2, 1):
        for i, r in marks:
            if r == rank and i > prev:
                chosen[rank] = i
                prev = i
                break
    if len(chosen) < 3:
        return []

    items: list[RankItem] = []
    for rank in (5, 4, 3, 2, 1):
        if rank not in chosen:
            items.append(RankItem(rank, None, ""))
            continue
        k = chosen[rank] + 1
        # "4위는" 다음에 "요?" 같은 짧은 말이 따로 인식되면 건너뛴다
        while k < len(words) and len(words[k].text.strip()) <= 2 and words[k].text.strip().endswith("?"):
            k += 1
        if rank == 1:
            # "마지막 1위 맞춰 볼래? 힌트는 …" 이면 힌트 문장이 끝난 뒤에 공개
            window = words[k: k + 15]
            hint = next((k + n for n, w in enumerate(window) if "힌트" in w.text), None)
            if hint is None and k < len(words) and "맞춰" in " ".join(w.text for w in words[k:k + 4]):
                hint = k
            if hint is not None:
                k = _sentence_end_after(words, hint) + 1
        if k >= len(words):
            items.append(RankItem(rank, None, ""))
            continue
        end = _sentence_end_after(words, k, limit=3)
        picked = []
        for w in words[k: end + 1]:
            picked.append(w.text.strip())
            if re.search(r"[,.?!]$", picked[-1]):  # 쉼표에서도 끊는다
                break
        text = _clean(" ".join(picked))[:16]
        items.append(RankItem(rank, round(words[k].start, 2), text))
    return items


def suggest_title(words: list[Word], top_mode: bool) -> str:
    """첫 문장으로 제목을 추천한다. TOP 5 영상이면 뒤에 'TOP 5'를 붙인다."""
    if not words:
        return ""
    end = _sentence_end_after(words, 0, limit=8)
    text = _clean(" ".join(w.text.strip() for w in words[: end + 1])).rstrip("?!")
    text = re.sub(r"\s*(TOP\s*5|탑\s*5|탑\s*파이브).*$", "", text, flags=re.I)
    if len(text) > 22:
        text = text[:22].rsplit(" ", 1)[0]
    return f"{text} TOP 5" if top_mode else text

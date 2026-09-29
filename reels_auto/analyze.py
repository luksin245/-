"""음성 인식 결과로 자막, 목록(TOP N / N가지) 항목, 제목을 자동으로 만든다."""
from __future__ import annotations

import re

from .project import Caption, RankItem, Word

SENTENCE_END = re.compile(r"[.?!]$")
MAX_ITEMS = 7
KOREAN_NUM = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7}
NATIVE_NUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7}
RANK_DIGIT = re.compile(r"(?<![0-9])([1-7])\s*위")
RANK_KOREAN = re.compile(r"^(일|이|삼|사|오|육|칠)위")
# "첫 번째", "두번째", "셋째", "2번째" …
# "1번은", "2번은요?", "3번째", 그리고 "1." 처럼 번호만 말한 경우
ORDINAL = re.compile(r"^(?:(첫|두|세|네|다섯|여섯|일곱)\s*번\s*째|(첫|둘|셋|넷|다섯|여섯|일곱)째|([1-7])\s*번\s*(?:째|은|는|이|으로)|([1-7])\.$)")
ORDINAL_NUM = {"첫": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7}
# 첫 문장에서 개수 찾기: "TOP 3", "탑 5", "3가지", "세 가지"
COUNT_TOP = re.compile(r"(?:TOP|탑)\s*([2-7])", re.I)
COUNT_KINDS = re.compile(r"(?:([2-7])|(두|세|네|다섯|여섯|일곱))\s*가지")


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
            short_tail = len(text) <= 2 or (len(text) <= 4 and re.search(r"[.?!]$", text))
            too_long = length > max_chars and not (short_tail and length <= max_chars + 5)
            prev_text = prev.text.strip()
            sentence_end = re.search(r"[.?!]$", prev_text)
            # 쉼표는 줄이 어느 정도 찼을 때만 끊는다 ("문자, 카카오톡, 녹음" 같은 나열은 한 줄로)
            comma_break = prev_text.endswith(",") and length - len(text) >= 8
            if too_long or sentence_end or comma_break or w.start - prev.end > max_gap:
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
    if i + 1 < len(words) and re.fullmatch(r"[1-7]", text) and words[i + 1].text.strip().startswith("위"):
        return int(text)
    return None


def _ordinal_of(words: list[Word], i: int) -> tuple[int, int] | None:
    """(몇 번째, 표시어가 끝나는 단어 위치). "첫" "번째는" 처럼 나뉜 경우도 찾는다."""
    for span in (1, 2):
        if i + span > len(words):
            break
        text = "".join(w.text.strip() for w in words[i: i + span])
        m = ORDINAL.match(text)
        if m:
            key = m.group(1) or m.group(2)
            return (ORDINAL_NUM[key] if key else int(m.group(3) or m.group(4))), i + span - 1
    return None


def _sentence_end_after(words: list[Word], i: int, limit: int = 14) -> int:
    for j in range(i, min(len(words), i + limit)):
        if SENTENCE_END.search(words[j].text.strip()):
            return j
        if j + 1 < len(words) and words[j + 1].start - words[j].end > 0.4:
            return j
    return min(len(words) - 1, i + limit)


def announced_count(words: list[Word]) -> int | None:
    """첫 부분에서 말한 개수 ("TOP 3", "3가지", "세 가지")."""
    head = " ".join(w.text.strip() for w in words[:25])
    m = COUNT_TOP.search(head)
    if m:
        return int(m.group(1))
    m = COUNT_KINDS.search(head)
    if m:
        return int(m.group(1)) if m.group(1) else NATIVE_NUM[m.group(2)]
    return None


def _item_at(words: list[Word], k: int, slot: int, hint_check: bool) -> RankItem:
    """표시어 바로 다음 말을 항목으로 추천한다."""
    # "4위는" 다음에 "요?" 같은 짧은 말이 따로 인식되면 건너뛴다
    while k < len(words) and len(words[k].text.strip()) <= 2 and words[k].text.strip().endswith("?"):
        k += 1
    if hint_check:
        # "마지막 1위! 맞춰볼래? 힌트는 … 말이야. 우리 회사 너무 작아서 안돼 정답!"
        # 처럼 "정답" 바로 앞에서 답을 말하는 경우: 정답 앞 말 덩어리(쉼 전까지)를 항목으로
        answer_at = next((g for g in range(k, min(len(words), k + 30))
                          if words[g].text.strip().strip("!.?,").startswith("정답")), None)
        if answer_at is not None and answer_at > k:
            picked: list[Word] = []
            j = answer_at - 1
            while j >= k and len(picked) < 6:
                t = words[j].text.strip()
                if picked and (SENTENCE_END.search(t) or re.search(r"(이야|말이야|거야)[.,]?$", t)
                               or picked[0].start - words[j].end > 0.25):
                    break
                picked.insert(0, words[j])
                j -= 1
            if picked:
                text = _clean(" ".join(w.text.strip() for w in picked)).rstrip("?")
                return RankItem(slot, round(picked[0].start, 2), text[:18])
        # "마지막 1위 맞춰 볼래? 힌트는 …" 이면 힌트 문장이 끝난 뒤에 공개
        window = words[k: k + 15]
        hint = next((k + n for n, w in enumerate(window) if "힌트" in w.text), None)
        if hint is None and k < len(words) and "맞춰" in " ".join(w.text for w in words[k:k + 4]):
            hint = k
        if hint is not None:
            k = _sentence_end_after(words, hint) + 1
    if k >= len(words):
        return RankItem(slot, None, "")
    # 앞에 붙은 "아니"(말 바꿈), "맞아/정답"(맞장구)는 뺀다
    while k < len(words) - 1 and words[k].text.strip().strip(",.!?") in ("아니", "아니야", "맞아", "정답", "정답은", "응", "네"):
        k += 1
    end = _sentence_end_after(words, k, limit=3)
    picked = []
    for idx in range(k, end + 1):
        w = words[idx]
        # 다음 순위 질문("3위는요?")이나 "마지막"이 나오면 거기서 끊는다
        if picked and (_rank_of(words, idx) is not None or w.text.strip().startswith("마지막")):
            break
        t = w.text.strip()
        # "근로계약서 작성을 안 하면" → "근로계약서 작성": 두 번째 단어부터 목적격·주격 조사가 붙으면 떼고 끊는다
        if picked and re.search(r"[을를]$", t.rstrip(",.?!")):
            picked.append(t.rstrip(",.?!")[:-1])
            break
        picked.append(t)
        if re.search(r"[,.?!]$", picked[-1]):  # 쉼표에서도 끊는다
            break
    text = _clean(" ".join(picked))
    if len(text) > 18:  # 너무 길면 단어 단위로 자른다
        text = text[:18].rsplit(" ", 1)[0]
    return RankItem(slot, round(words[k].start, 2), text)


def _rank_list(words: list[Word], expected: int | None) -> tuple[int, list[RankItem]] | None:
    """순위형: "3위는? … 2위는? … 1위" 처럼 큰 순위부터 내려오는 흐름."""
    marks = [(i, r) for i in range(len(words)) if (r := _rank_of(words, i)) is not None]
    if not marks:
        return None
    candidates = [expected] if expected else sorted({r for _, r in marks if r >= 2}, reverse=True)
    for top in candidates:
        chosen: dict[int, int] = {}
        prev = -1
        for rank in range(top, 0, -1):
            for i, r in marks:
                if r == rank and i > prev:
                    chosen[rank] = i
                    prev = i
                    break
        if top in chosen and len(chosen) >= max(2, top - 1):
            items = [(_item_at(words, chosen[r] + 1, r, r == 1) if r in chosen else RankItem(r, None, ""))
                     for r in range(top, 0, -1)]
            return top, items
    return None


def _ordinal_list(words: list[Word], expected: int | None) -> tuple[int, list[RankItem]] | None:
    """나열형: "첫 번째 … 두 번째 … 마지막(세 번째)" 처럼 1부터 올라가는 흐름."""
    marks = [(i, *o) for i in range(len(words)) if (o := _ordinal_of(words, i)) is not None]
    chosen: dict[int, int] = {}  # 번호 → 표시어가 끝나는 단어 위치
    prev = -1
    for n in range(1, MAX_ITEMS + 1):
        hit = next(((i, e) for i, num, e in marks if num == n and i > prev), None)
        if hit is None:
            break
        chosen[n] = hit[1]
        prev = hit[1]
    count = expected or len(chosen)
    # "마지막으로 …" 을 마지막 항목으로 쓴다
    if count and count not in chosen and len(chosen) == count - 1:
        last = next((i for i in range(prev + 1, len(words)) if words[i].text.strip().startswith("마지막")), None)
        if last is not None:
            chosen[count] = last
    if count < 2 or len(chosen) < max(2, count - 1):
        return None
    items = [(_item_at(words, chosen[n] + 1, n, False) if n in chosen else RankItem(n, None, ""))
             for n in range(1, count + 1)]
    return count, items


def _ascending_rank_list(words: list[Word], expected: int | None) -> tuple[int, list[RankItem]] | None:
    """"1. … 2. … 3. …"이 "1위, 2위, 3위"로 인식된 경우: 순위가 1부터 올라가면 나열형으로 본다."""
    marks = [(i, r) for i in range(len(words)) if (r := _rank_of(words, i)) is not None]
    chosen: dict[int, int] = {}
    prev = -1
    for n in range(1, MAX_ITEMS + 1):
        hit = next((i for i, r in marks if r == n and i > prev), None)
        if hit is None:
            break
        chosen[n] = hit
        prev = hit
    count = len(chosen)
    if count < 3 or (expected and count < expected):
        return None
    return count, [_item_at(words, chosen[n] + 1, n, False) for n in range(1, count + 1)]


def detect_list(words: list[Word]) -> tuple[str, int, list[RankItem]]:
    """(형식, 개수, 항목들). 형식: "rank"(TOP N, 아래부터) / "ordinal"(N가지, 위부터) / "none"."""
    expected = announced_count(words)
    ascending = _ascending_rank_list(words, expected)
    if ascending:
        # "1위, 2위, 3위" 순서로 말했으면 순위 발표가 아니라 번호 나열
        rank = _rank_list(words, expected)
        if not rank or sum(1 for it in rank[1] if it.time is not None) <= ascending[0]:
            return "ordinal", ascending[0], ascending[1]
    for style, finder in (("rank", _rank_list), ("ordinal", _ordinal_list)):
        found = finder(words, expected)
        if found:
            return style, found[0], found[1]
    return "none", 0, []


def suggest_title(words: list[Word], style: str = "none", count: int = 0) -> str:
    """첫 문장으로 제목을 추천한다. 순위형이면 뒤에 'TOP N'을 붙인다."""
    if not words:
        return ""
    end = _sentence_end_after(words, 0, limit=8)
    text = _clean(" ".join(w.text.strip() for w in words[: end + 1])).rstrip("?!")
    # "노무사님, …" 처럼 부르는 말로 시작하면 떼어낸다
    text = re.sub(r"^\S*(님|씨|선생)[,!]?\s+", "", text)
    text = re.sub(r"\s*(TOP|탑)\s*[0-9].*$", "", text, flags=re.I)
    if style == "tier" and "티어" not in text.replace("티어리스트", "티어"):
        return "티어리스트"
    if style == "tier" and not text.endswith(("티어리스트", "탄")) and "티어리스트" not in text:
        return "티어리스트"
    if style == "quiz" and "퀴즈" not in text:  # 인트로 없이 바로 문제로 시작하는 퀴즈
        return "O/X 퀴즈"
    if "퀴즈" in text:  # "일상 근로 상식 퀴즈 풀어보자" → "일상 근로 상식 퀴즈"
        text = text[: text.index("퀴즈") + 2]
    if style == "rank":
        text = re.sub(r"\s*(정리해\s*보자|알려\s*줄게|알려\s*드릴게요).*$", "", text)
    if len(text) > 30:  # 두 줄(한 줄 17자 안팎)에 들어가게
        text = text[:30].rsplit(" ", 1)[0]
    text = re.sub(r"^[1-7]\s*위\s*,?\s*", "", text)  # 앞에 잘못 들어간 "2위," 같은 말
    # "…이유가 뭐예요?" → "…이유 5가지" (레퍼런스: "병원이 노동청 신고 많이 당하는 이유 5가지")
    if style in ("rank", "ordinal") and count:
        m = re.search(r"\s*(이|가|는|은)?\s*뭐(예요|에요|야|일까요?|가 있을까)$", text)
        if m:
            text = text[: m.start()] + f" {count}가지"
    # "…이유 5가지"처럼 개수를 이미 말한 제목에는 TOP N을 붙이지 않는다
    has_count = re.search(r"([0-9]+|두|세|네|다섯|여섯|일곱)\s*가지", text)
    return f"{text} TOP {count}" if style == "rank" and not has_count else text

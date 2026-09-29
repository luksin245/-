"""O/X 퀴즈형: "…라고 하면 해고 효력이 없다?" 같은 문제를 찾고, 카드와 정답 표시(✅/❌)를 만든다.

레퍼런스(5. 근로 상식 퀴즈)처럼 문제를 말하기 시작하면 가운데에 그림 카드가 뜨고,
답을 말하기 시작하면 카드 위에 초록 체크 또는 빨간 X가 톡 튀어나온다.
"""
from __future__ import annotations

import re
from pathlib import Path

from .paths import app_dir
from .project import QuizItem, Word
from .stickers import Overlay, load_table, match, stickers_dir

CARD_W, CARD_H = 540, 300
CARD_CENTER = (540, 1258)  # 레퍼런스에서 잰 카드 중심
MARK_SIZE = 220
IMAGE_SIZE = 230  # 카드 안 스티커 크기

QUESTION_END = re.compile(r"다\?$")  # "없다?", "된다?", "있다?", "무효이다?"
SENTENCE_END = re.compile(r"[.?!]$")
SAY_O = re.compile(r"^(O|오|맞아|맞습니다|맞아요|정답|응|네|그렇지|그래)[.,!?]*$", re.I)
SAY_X = re.compile(r"^(X|엑스|아니|아니야|아니요|아뇨|틀려|틀렸어|땡)[.,!?]*$", re.I)
NEGATIVE = re.compile(r"안 |않|없|못|아니|무효|불가")


def quiz_dir() -> Path:
    return app_dir() / "assets" / "quiz"


def _sentences(words: list[Word]) -> list[tuple[int, int]]:
    """(시작 단어, 끝 단어) 문장 목록."""
    out, start = [], 0
    for i, w in enumerate(words):
        if SENTENCE_END.search(w.text.strip()) or i == len(words) - 1:
            out.append((start, i))
            start = i + 1
    return out


def _text(words: list[Word], a: int, b: int) -> str:
    return " ".join(w.text.strip() for w in words[a: b + 1])


def _guess_answer(question: str, words: list[Word], a: int, b: int) -> str:
    """답을 직접 말하면("O", "맞아", "아니") 그대로, 아니면 질문과 답의 부정 여부를 비교해서 추측."""
    for w in words[a: min(b + 1, a + 2)]:
        if SAY_O.match(w.text.strip()):
            return "O"
        if SAY_X.match(w.text.strip()):
            return "X"
    q_neg = bool(NEGATIVE.search(question))
    a_neg = bool(NEGATIVE.search(_text(words, a, b)))
    return "O" if q_neg == a_neg else "X"


def detect_quiz(words: list[Word], duration: float) -> list[QuizItem]:
    """퀴즈 문제들. '퀴즈'라는 말이 나오고 문제가 2개 이상이거나, 문제가 3개 이상이면 퀴즈형으로 본다."""
    sents = _sentences(words)
    questions = [k for k, (a, b) in enumerate(sents) if QUESTION_END.search(words[b].text.strip())]
    head = " ".join(w.text for w in words[:20])
    if not (len(questions) >= 3 or ("퀴즈" in head and len(questions) >= 2)):
        return []
    # 정답 표시와 헷갈리는 체크/X 그림은 카드 그림으로 쓰지 않는다
    picture_table = {k: v for k, v in load_table().items() if k not in ("확인", "금지")}
    items: list[QuizItem] = []
    for n, k in enumerate(questions):
        a, b = sents[k]
        question = _text(words, a, b)
        if k + 1 >= len(sents):
            continue
        ra, rb = sents[k + 1]
        start = words[a].start
        reveal = words[ra].start
        end = words[sents[questions[n + 1]][0]].start - 0.05 if n + 1 < len(questions) else duration
        image = match(question, picture_table) or "물음표"
        items.append(QuizItem(round(start, 2), round(reveal, 2), round(end, 2),
                              _guess_answer(question, words, ra, rb), image))
    return items


def overlays(items: list[QuizItem]) -> list[Overlay]:
    cx, cy = CARD_CENTER
    out: list[Overlay] = []
    for q in items:
        photo = Path(q.image)
        if photo.suffix and photo.exists():  # 사용자가 고른 사진
            out.append(Overlay(str(photo), q.start, q.end, cx, cy, CARD_W, CARD_H))
        else:
            out.append(Overlay(str(quiz_dir() / "card.png"), q.start, q.end, cx, cy, CARD_W, CARD_H))
            out.append(Overlay(str(stickers_dir() / f"{q.image}.png"), q.start, q.end, cx, cy, IMAGE_SIZE))
        mark = "mark_o.png" if q.answer.upper() == "O" else "mark_x.png"
        out.append(Overlay(str(quiz_dir() / mark), q.reveal, q.end, cx, cy, MARK_SIZE))
    return out

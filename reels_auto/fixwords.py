"""음성 인식이 잘못 적은 전문 용어 고치기.

1) assets/fix_words.txt 의 "틀린 말 = 바른 말" 목록대로 바꾼다. (예: 글록에압서 = 근로계약서)
2) 용어 사전(assets/words.txt)의 말과 글자 수가 같고 한 글자만 비슷하게 다르면 고친다.
   (예: 주휴수단 → 주휴수당, 근로계학서 → 근로계약서)
   멀쩡한 말을 잘못 바꾸지 않도록 두 글자 이상 다르면 건드리지 않는다.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from dataclasses import replace

from .project import Word

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
# 용어 뒤에 붙는 조사 (길이가 긴 것부터)
PARTICLES = ("에서는", "에서", "으로", "에는", "이나", "는", "은", "을", "를", "이", "가", "에", "도", "로", "의", "만")
MIN_RATIO = 0.8


def jamo(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out += [CHO[code // 588], JUNG[(code % 588) // 28], JONG[code % 28].strip()]
        else:
            out.append(ch)
    return "".join(out)


def _split(word: str) -> tuple[str, str, str]:
    """(앞 기호, 본문, 조사+뒤 기호)"""
    m = re.match(r"^(\W*)(.*?)(\W*)$", word)
    lead, body, trail = m.group(1), m.group(2), m.group(3)
    for p in PARTICLES:
        if body.endswith(p) and len(body) - len(p) >= 3:
            return lead, body[: -len(p)], p + trail
    return lead, body, trail


def _terms(glossary: list[str]) -> list[tuple[str, str]]:
    # 띄어쓰기 없는 3글자 이상 용어만 (짧은 말은 잘못 고칠 위험이 크다)
    return [(t, jamo(t)) for t in glossary if " " not in t and len(t) >= 4]


def best_term(body: str, terms: list[tuple[str, str]]) -> str | None:
    if len(body) < 3 or not re.fullmatch(r"[가-힣]+", body):
        return None
    j = jamo(body)
    best, best_r = None, MIN_RATIO
    for term, tj in terms:
        if body == term:
            return None
        if len(body) != len(term) or sum(a != b for a, b in zip(body, term)) != 1:
            continue
        r = SequenceMatcher(None, j, tj).ratio()
        if r > best_r:
            best, best_r = term, r
    return best


def load_fixes(path) -> list[tuple[str, str]]:
    """fix_words.txt → [(틀린 말, 바른 말)] (긴 것부터)"""
    if not path.exists():
        return []
    pairs = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"):
            wrong, right = (x.strip() for x in ln.split("=", 1))
            if wrong and right:
                pairs.append((wrong, right))
    return sorted(pairs, key=lambda p: -len(p[0]))


def fix_words(words: list[Word], glossary: list[str], fixes: list[tuple[str, str]] = ()) -> list[Word]:
    terms = _terms(glossary)
    out = []
    for w in words:
        text = w.text
        for wrong, right in fixes:
            if wrong in text:
                text = text.replace(wrong, right)
                break
        else:
            lead, body, trail = _split(text)
            term = best_term(body, terms)
            if term:
                text = lead + term + trail
        out.append(w if text == w.text else replace(w, text=text))
    return out

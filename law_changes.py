"""취업규칙 기준일 이후의 법령 개정 사항을 찾는다.

download_laws.py가 받아 둔 laws/versions/<법령명>/의 시행 버전들을 차례로 비교해
조문별로 기준일 당시 내용과 최신 내용(시행 예정 포함)을 돌려준다.
"""

import json
import re
from datetime import date
from pathlib import Path

from checks import norm
from rule_parser import ADDENDA, TOC_LINE

# 조문 끝의 개정 표시: <개정 2019. 1. 15.>, [본조신설 2019. 1. 15.] 등
ANNOTATION = re.compile(
    r"<\s*(?:개정|신설|전문개정|본조신설|삭제|타법개정|제목개정|종전)[^>]*>"
    r"|\[\s*(?:본조신설|전문개정|제목개정|본조제목개정|종전|시행일|제\d+조)[^\]]*\]"
)
# 취업규칙과 관련이 적은 조문 제목
IRRELEVANT = re.compile(
    r"벌칙|과태료|양벌|위원회|권한의\s*위임|위탁|규제의\s*재검토|공무원\s*의제|근로감독관|수수료"
    r"|포상금|자료\s*제출|보고|감독|시정명령|과징금|청문|목적|정의|국가|지방자치단체|기본계획|실태조사"
)
DATE = re.compile(r"(\d{4})\s*[.년-]\s*(\d{1,2})\s*[.월-]\s*(\d{1,2})")
SHORT = {
    "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률": "남녀고용평등법",
    "근로자퇴직급여 보장법": "퇴직급여법",
    "기간제 및 단시간근로자 보호 등에 관한 법률": "기간제법",
    "근로자참여 및 협력증진에 관한 법률": "근로자참여법",
    "고용상 연령차별금지 및 고령자고용촉진에 관한 법률": "고령자고용법",
}


def short_name(law):
    for full, short in SHORT.items():
        if law.startswith(full):
            return short + law[len(full):]
    return law


def clean(text):
    """개정 표시를 지운 조문. '삭제'된 조문은 빈 문자열."""
    text = ANNOTATION.sub("", text or "").strip()
    body = re.sub(r"^제\s*\d+\s*조(?:의\s*\d+)?(?:\([^)]*\))?", "", text).strip()
    return "" if body in ("", "삭제") else text


def fmt(ymd):
    return f"{ymd[:4]}. {int(ymd[4:6])}. {int(ymd[6:])}."


def detect_base_date(text):
    """취업규칙 부칙에 적힌 날짜 중 가장 늦은 날짜(YYYYMMDD). 못 찾으면 None.
    목차에 있는 '부칙'은 건너뛰고, 본문 뒤의 첫 '부칙'부터 찾는다."""
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    toc_end = max((offsets[i + 1] for i, line in enumerate(lines) if TOC_LINE.search(line)), default=0)
    starts = [offsets[i] for i, line in enumerate(lines) if ADDENDA.match(line) and offsets[i] >= toc_end]
    if not starts:
        return None
    limit = date.today().replace(year=date.today().year + 1).strftime("%Y%m%d")
    found = []
    for y, mo, d in DATE.findall(text[starts[0]:]):
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            ymd = f"{y}{int(mo):02d}{int(d):02d}"
            if "1990" <= ymd[:4] and ymd <= limit:
                found.append(ymd)
    return max(found) if found else None


def load_history(laws_dir):
    """{법령명: {"폴더", "버전": [...]}}"""
    history = {}
    for index in sorted(Path(laws_dir).glob("versions/*/index.json")):
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        versions = sorted((v for v in data.get("버전", []) if v.get("파일")), key=lambda v: v["시행일자"])
        if versions:
            history[data["법령명"]] = {"폴더": index.parent, "버전": versions}
    return history


def _articles(folder, version):
    data = json.loads((folder / version["파일"]).read_text(encoding="utf-8"))
    return {a["조문"]: a for a in data["조문"]}


def law_changes(history, base):
    """기준일(YYYYMMDD) 이후 바뀐 조문 목록과, 이력이 기준일까지 닿지 않는 법령 목록."""
    today = date.today().strftime("%Y%m%d")
    changes, short_history = [], []
    for law, h in history.items():
        versions = h["버전"]
        start = max((i for i, v in enumerate(versions) if v["시행일자"] <= base), default=None)
        if start is None:
            short_history.append(law)
            start = 0
        if start == len(versions) - 1:
            continue

        prev = _articles(h["폴더"], versions[start])
        found = {}
        for v in versions[start + 1:]:
            cur = _articles(h["폴더"], v)
            for label in list(dict.fromkeys([*prev, *cur])):
                before, after = prev.get(label), cur.get(label)
                old_text = clean(before["내용"]) if before else ""
                new_text = clean(after["내용"]) if after else ""
                if norm(old_text) == norm(new_text):
                    continue
                entry = found.setdefault(label, {"이전": old_text, "이력": []})
                entry["현재"] = new_text
                entry["제목"] = (after or before)["제목"]
                entry["이력"].append((v["시행일자"], v.get("제개정구분", "")))
            prev = cur

        for label, e in found.items():
            if norm(e["이전"]) == norm(e["현재"]):
                continue  # 바뀌었다가 원래대로 돌아온 경우
            kind = "신설" if not e["이전"] else "삭제" if not e["현재"] else "개정"
            changes.append({
                "법령명": law, "조문": label, "제목": e["제목"], "구분": kind,
                "이전": e["이전"], "현재": e["현재"], "이력": e["이력"],
                "시행예정": e["이력"][-1][0] > today,
            })
    return changes, short_history


def _title_tokens(title):
    parts = re.split(r"[\s·ㆍ,()]+|및|등|의|에\s*관한|에\s*대한|에\s*따른", title or "")
    return [norm(p) for p in parts if len(norm(p)) >= 2]


def related_articles(change, rules_articles):
    """개정된 법 조문과 관련된 취업규칙 조항 번호 목록."""
    title = norm(change["제목"])
    if not title or IRRELEVANT.search(change["제목"]):
        return []
    tokens = _title_tokens(change["제목"])
    hits = []
    for a in rules_articles:
        t = norm(a["제목"] + a["내용"])
        if title in t or (tokens and all(tok in t for tok in tokens)):
            hits.append(a["조항"])
    return hits


def is_relevant(change):
    return bool(change["제목"]) and not IRRELEVANT.search(change["제목"])

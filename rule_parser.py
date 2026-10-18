"""취업규칙 PDF에서 텍스트를 뽑아 조항 단위로 나눈다."""

import io
import re

import pdfplumber

CIRCLED = "".join(chr(c) for c in range(0x2460, 0x2474))  # ①~⑳

# "제12조(휴게)", "제12조 【휴게】", "제12조의2(직장 내 괴롭힘)" 형태의 조항 제목
HEADING = re.compile(
    r"^\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*"
    r"(?:[(（【\[]\s*([^)）】\]]{1,40}?)\s*[)）】\]])?"
)
CHAPTER = re.compile(r"^\s*제\s*\d+\s*장\s*.*")
ADDENDA = re.compile(r"^\s*<?\s*부\s*칙\s*>?\s*(?:[<(（].*)?$")
# 목차 줄: "제1조(목적) ·········· 7", "제1조(목적) ...... 7"
TOC_LINE = re.compile(r"(?:[·.…‥・ㆍ]\s*){4,}\s*\d+\s*$")
# 쪽번호만 있는 줄: "3", "- 3 -", "3 / 20"
PAGE_NO = re.compile(r"^\s*[-–]?\s*\d+\s*[-–]?\s*$|^\s*\d+\s*/\s*\d+\s*$")
# 제목 없는 조항 뒤에 이런 글자가 오면 본문 속 인용("제10조에 따라")으로 본다
REFERENCE_TAIL = re.compile(r"^\s*(?:에|의|및|와|과|을|를|은|는|이|가|부터|까지|,|·|ㆍ|제\d)")
# 줄바꿈을 유지해야 하는 줄의 시작: 항(①), 호(1.), 목(가.)
LIST_START = re.compile(rf"^\s*(?:[{CIRCLED}]|\d+\.|[가나다라마바사아자차카타파하]\.|\(\d+\)|\d+\))")


def extract_text(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _join_lines(lines):
    """PDF에서 문장 중간에 끊긴 줄을 이어 붙인다. 항·호·목은 줄을 바꾼다."""
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out and not LIST_START.match(line):
            out[-1] += " " + line
        else:
            out.append(line)
    return "\n".join(out)


def split_articles(text):
    """텍스트를 조항 목록으로 나눈다.

    반환: [{"조항", "제목", "장", "부칙", "내용"}, ...]
    """
    articles = []
    current = None
    chapter = ""
    in_addenda = False
    last_no = 0

    def close():
        if current:
            current["내용"] = _join_lines(current.pop("lines"))
            articles.append(current)

    for line in text.splitlines():
        if PAGE_NO.match(line) or TOC_LINE.search(line):
            continue
        # 본문 조항이 나오기 전의 '부칙'은 목차에 있는 것이다
        if ADDENDA.match(line) and (articles or current):
            close()
            current, in_addenda, last_no = None, True, 0
            continue
        if CHAPTER.match(line) and len(line.strip()) <= 40 and not HEADING.match(line):
            chapter = line.strip()
            continue

        m = HEADING.match(line)
        if m:
            no, branch, title = int(m.group(1)), m.group(2), m.group(3)
            if title:
                ok = no > last_no or (branch and no == last_no)
            else:
                rest = line[m.end():]
                ok = (no == last_no + 1 or (branch and no == last_no)) and not REFERENCE_TAIL.match(rest)
            if ok:
                close()
                label = f"제{no}조" + (f"의{branch}" if branch else "")
                current = {
                    "조항": ("부칙 " if in_addenda else "") + label,
                    "제목": (title or "").strip(),
                    "장": "" if in_addenda else chapter,
                    "부칙": in_addenda,
                    "lines": [line],
                }
                last_no = no
                continue

        if current:
            current["lines"].append(line)

    close()
    return articles


def sentences(text):
    """조항 본문을 문장 단위로 나눈다."""
    parts = re.split(r"(?<=[.。])\s+|\n", text)
    return [p.strip() for p in parts if p.strip()]


def detect_company(text):
    """PDF 앞부분에서 회사명을 찾는다: '(주)케미원스', '㈜○○', '주식회사 ○○', '○○ 주식회사'."""
    for line in text.splitlines()[:15]:
        m = re.search(r"(?:\(주\)|㈜|주식회사)\s*[가-힣A-Za-z0-9&·]+|[가-힣A-Za-z0-9&·]+\s*(?:\(주\)|㈜|주식회사)", line)
        if m:
            return m.group(0).strip()
    return ""

"""신구대조표: 개정안 초안 작성, 개정본 비교, Word 내보내기."""

import difflib
import html
import io
import re

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from checks import AGE, EQUAL, LABOR, OK, RETIRE, norm

NEW, CHANGE, DELETE = "신설", "개정", "삭제"
CIRCLED = [chr(c) for c in range(0x2460, 0x2474)]  # ①~⑳

LAW_SHORT = {LABOR: "근로기준법", EQUAL: "남녀고용평등법", RETIRE: "퇴직급여법", AGE: "고령자고용법"}

# 필수 기재사항(근로기준법 제93조)이 빠졌을 때 넣을 신설 조항 초안
TEMPLATES = {
    "시업·종업 시각": "제○조(근로시간) ① 1주간의 근로시간은 휴게시간을 제외하고 40시간, 1일의 근로시간은 휴게시간을 제외하고 8시간으로 한다.\n② 시업시각은 ○○시, 종업시각은 ○○시로 한다.",
    "휴게시간": "제○조(휴게) 회사는 근로시간이 4시간인 경우에는 30분 이상, 8시간인 경우에는 1시간 이상의 휴게시간을 근로시간 도중에 준다.",
    "휴일": "제○조(휴일) 회사는 1주 동안의 소정근로일을 개근한 직원에게 1주에 평균 1회 이상의 유급휴일을 주며, 관공서의 공휴일에 관한 규정에 따른 공휴일 및 대체공휴일을 유급휴일로 한다.",
    "휴가": "제○조(연차유급휴가) ① 회사는 1년간 80퍼센트 이상 출근한 직원에게 15일의 유급휴가를 준다.\n② 계속하여 근로한 기간이 1년 미만인 직원 또는 1년간 80퍼센트 미만 출근한 직원에게는 1개월 개근 시 1일의 유급휴가를 준다.",
    "결정·계산·지급 방법": "제○조(임금의 계산 및 지급방법) 임금은 월 단위로 계산하여 통화로 직접 직원에게 그 전액을 지급한다. 다만, 직원의 동의를 받아 직원 명의의 예금계좌로 지급할 수 있다.",
    "산정기간·지급시기": "제○조(임금의 산정기간 및 지급일) 임금은 매월 1일부터 말일까지를 산정기간으로 하여 다음 달 ○일에 지급한다. 지급일이 휴일인 경우에는 그 전날 지급한다.",
    "승급": "제○조(승급) 승급은 매년 1회 실시하며, 그 기준과 방법은 회사가 별도로 정한다.",
    "퇴직": "제○조(퇴직) 직원이 다음 각 호의 어느 하나에 해당하는 경우에는 퇴직으로 한다.\n1. 본인이 퇴직을 원하는 경우\n2. 사망한 경우\n3. 정년에 도달한 경우\n4. 근로계약기간이 끝난 경우",
    "퇴직급여": "제○조(퇴직급여) 회사는 계속근로기간이 1년 이상인 직원이 퇴직하는 경우 근로자퇴직급여 보장법에 따라 계속근로기간 1년에 대하여 30일분 이상의 평균임금을 퇴직금으로 지급하거나 퇴직연금제도를 운영한다.",
    "최저임금": "제○조(최저임금) 회사는 최저임금법에 따른 최저임금액 이상의 임금을 지급한다.",
    "출산전후휴가": "제○조(출산전후휴가) 회사는 임신 중인 직원에게 출산 전과 출산 후를 통하여 90일(한 번에 둘 이상 자녀를 임신한 경우에는 120일)의 출산전후휴가를 준다. 이 경우 출산 후의 휴가 기간이 45일(한 번에 둘 이상 자녀를 임신한 경우에는 60일) 이상이 되도록 한다.",
    "배우자 출산휴가": "제○조(배우자 출산휴가) 회사는 직원이 배우자의 출산을 이유로 휴가를 청구하는 경우 남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률에서 정하는 기간의 유급휴가를 준다.",
    "육아휴직": "제○조(육아휴직) 회사는 임신 중인 여성 직원이나 자녀를 양육하기 위하여 휴직을 신청하는 직원에게 남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률에서 정하는 바에 따라 육아휴직을 허용한다.",
    "육아기 근로시간 단축": "제○조(육아기 근로시간 단축) 회사는 자녀를 양육하기 위하여 근로시간의 단축을 신청하는 직원에게 남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률에서 정하는 바에 따라 근로시간 단축을 허용한다.",
    "안전·보건": "제○조(안전과 보건) 회사와 직원은 산업안전보건법 등 관계 법령에서 정하는 안전·보건에 관한 사항을 지키며, 회사는 관계 법령에 따라 직원에게 건강진단을 실시한다.",
    "사업장 환경 개선": "제○조(사업장 환경의 개선) 회사는 직원의 성별·연령 또는 신체적 조건 등의 특성을 고려하여 사업장 환경을 개선하도록 노력한다.",
    "업무상 재해": "제○조(재해보상) 직원이 업무상 부상을 당하거나 질병에 걸린 경우에는 산업재해보상보험법에 따라 보상을 받는다.",
    "업무 외 재해부조": "제○조(업무 외 재해부조) 직원이 업무 외의 사유로 부상·질병 또는 사망한 경우 회사는 별도로 정하는 바에 따라 부조할 수 있다.",
    "괴롭힘 예방": "제○조(직장 내 괴롭힘의 금지) 누구든지 직장에서의 지위 또는 관계 등의 우위를 이용하여 업무상 적정범위를 넘어 다른 직원에게 신체적·정신적 고통을 주거나 근무환경을 악화시키는 행위를 하여서는 아니 된다.",
    "발생 시 조치": "제○조(직장 내 괴롭힘 발생 시 조치) ① 누구든지 직장 내 괴롭힘 발생 사실을 알게 된 경우 회사에 신고할 수 있다.\n② 회사는 신고를 접수하거나 발생 사실을 인지한 경우 지체 없이 객관적으로 조사하고, 피해근로자 보호를 위하여 근무장소 변경, 유급휴가 명령 등 적절한 조치를 한다.\n③ 회사는 신고한 직원과 피해근로자에게 해고나 그 밖의 불리한 처우를 하여서는 아니 된다.",
    "표창": "제○조(표창) 회사는 업무 성과가 우수하거나 회사 발전에 공로가 있는 직원을 표창할 수 있다.",
    "제재": "제○조(징계의 종류) 징계는 견책, 감급, 정직, 해고로 한다. 감급은 1회의 금액이 평균임금의 1일분의 2분의 1을, 총액이 1임금지급기의 임금 총액의 10분의 1을 초과하지 못한다.",
}


def _row(kind, label, current, revised, reason):
    return {"구분": kind, "조항": label, "현행": current, "개정안": revised, "사유": reason}


def _basis_text(basis):
    return ", ".join(f"{LAW_SHORT.get(law, law)} {label}" for law, label in basis)


def _append_item(text, sentence):
    """조항 끝에 문장을 덧붙인다. 항(①②…)으로 나뉜 조항이면 다음 항 번호를 붙인다."""
    used = [i for i, c in enumerate(CIRCLED) if c in text]
    if used and used[-1] + 1 < len(CIRCLED):
        sentence = f"{CIRCLED[used[-1] + 1]} {sentence}"
    return f"{text}\n{sentence}"


def draft_rows(articles, required, findings):
    """점검 결과로 신구대조표 초안을 만든다."""
    by_label = {a["조항"]: a for a in articles}
    changed = {}  # 조항 → [개정안, 사유 목록]
    new_rows = []

    for f in findings:
        fix = f.get("fix")
        if not fix or f["상태"] == OK:
            continue
        reason = f"{f['주제']}({_basis_text(f['근거'])})"
        if "new" in fix:
            new_rows.append(_row(NEW, "", "", fix["new"], reason))
            continue
        article = by_label.get(f["조항"])
        if not article:
            continue
        entry = changed.setdefault(article["조항"], [article["내용"], []])
        if "pattern" in fix:
            fixed = re.sub(fix["pattern"], fix["repl"], f["발췌"], count=1)
            if fixed == f["발췌"] or f["발췌"] not in entry[0]:
                continue
            entry[0] = entry[0].replace(f["발췌"], fixed, 1)
        else:
            entry[0] = _append_item(entry[0], fix["add"])
        entry[1].append(reason)

    rows = [_row(CHANGE, label, by_label[label]["내용"], text, "\n".join(reasons))
            for label, (text, reasons) in changed.items()]
    rows.sort(key=lambda r: articles.index(by_label[r["조항"]]))

    for item in required:
        for d in item["세부"]:
            if not d["조항"] and not d["해당 시만"] and d["세부"] in TEMPLATES:
                new_rows.append(_row(NEW, "", "", TEMPLATES[d["세부"]],
                                     f"필수 기재사항 누락: {d['세부']}(근로기준법 제93조 제{item['번호']}호)"))
    return rows + new_rows


def _body(text):
    """조항 번호를 뺀 본문(공백 제거)."""
    return norm(re.sub(r"^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?", "", text))


def compare_rows(old_articles, new_articles):
    """현행 취업규칙과 개정본을 비교한다.

    조항 번호가 바뀌어도 같은 조항으로 볼 수 있도록 제목(본칙/부칙 구분 포함)으로 먼저 맞추고,
    제목으로 못 찾으면 조항 번호로 맞춘다.
    """
    def title_key(a):
        return (a["부칙"], norm(a["제목"])) if a["제목"] else None

    titles = [title_key(a) for a in old_articles]
    by_title = {t: a for t, a in zip(titles, old_articles) if t and titles.count(t) == 1}
    by_label = {a["조항"]: a for a in old_articles}
    used = set()
    rows = []
    for a in new_articles:
        before = by_title.get(title_key(a))
        if before is None or before["조항"] in used:
            before = by_label.get(a["조항"])
        if before is None or before["조항"] in used:
            rows.append(_row(NEW, a["조항"], "", a["내용"], ""))
            continue
        used.add(before["조항"])
        # 조항 번호만 바뀐 경우(제7조 → 제6조)는 개정으로 보지 않는다
        if _body(before["내용"]) != _body(a["내용"]):
            label = a["조항"] if a["조항"] == before["조항"] else f"{before['조항']} → {a['조항']}"
            rows.append(_row(CHANGE, label, before["내용"], a["내용"], ""))
    for a in old_articles:
        if a["조항"] not in used:
            rows.append(_row(DELETE, a["조항"], a["내용"], "", ""))

    def order(row):
        m = re.match(r"(부칙 )?제(\d+)조(?:의(\d+))?", row["조항"])
        return (bool(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else (True, 9999, 0)

    return sorted(rows, key=order)


# ---------------------------------------------------------------------------
# 변경 부분 표시
# ---------------------------------------------------------------------------
def _tokens(text):
    return re.findall(r"\s+|[^\s]+", text)


def diff_segments(current, revised):
    """(현행 조각, 개정안 조각)을 돌려준다. 조각은 (글자, 바뀐 부분인지)."""
    a, b = _tokens(current), _tokens(revised)
    left, right = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        changed = op != "equal"
        if i2 > i1:
            left.append(("".join(a[i1:i2]), changed))
        if j2 > j1:
            right.append(("".join(b[j1:j2]), changed))
    return left, right


def diff_html(segments):
    parts = []
    for text, changed in segments:
        t = html.escape(text).replace("\n", "<br>")
        parts.append(f"<u><b style='color:#c0392b'>{t}</b></u>" if changed and text.strip() else t)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Word 내보내기
# ---------------------------------------------------------------------------
FONT = "맑은 고딕"


def _set_font(run, size=10, bold=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)


def _shade(cell, color):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    cell._tc.get_or_add_tcPr().append(shd)


def _write_segments(cell, segments, placeholder=None):
    p = cell.paragraphs[0]
    if placeholder:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(p.add_run(placeholder))
        return
    for text, changed in segments:
        for i, piece in enumerate(text.split("\n")):
            if i:
                p = cell.add_paragraph()
            if piece:
                run = p.add_run(piece)
                _set_font(run, bold=changed and bool(piece.strip()))
                if changed and piece.strip():
                    run.font.underline = True
                    run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)


def to_docx(rows, title="취업규칙 신구대조표"):
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Cm(29.7), Cm(21.0)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Cm(1.8))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(p.add_run(title), size=16, bold=True)

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = (Cm(11.3), Cm(11.3), Cm(3.5))
    for column, width in zip(table.columns, widths):
        column.width = width
    for cell, name, width in zip(table.rows[0].cells, ("현 행", "개 정 (안)", "비 고"), widths):
        cell.width = width
        _shade(cell, "D9E2F3")
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(cell.paragraphs[0].add_run(name), bold=True)

    for r in rows:
        cells = table.add_row().cells
        for cell, width in zip(cells, widths):
            cell.width = width
        left, right = diff_segments(r["현행"], r["개정안"])
        _write_segments(cells[0], left, "<신 설>" if r["구분"] == NEW else None)
        _write_segments(cells[1], right, "<삭 제>" if r["구분"] == DELETE else None)
        _set_font(cells[2].paragraphs[0].add_run(r["사유"]), size=9)

    note = doc.add_paragraph()
    _set_font(note.add_run("※ 밑줄 친 부분이 바뀐 내용입니다."), size=9)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

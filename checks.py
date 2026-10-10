"""취업규칙 조항을 노동 관계 법령 기준으로 점검한다.

모두 키워드·숫자 기반의 1차 점검이다. 결과는 사람이 법령 원문과 함께 확인해야 한다.
"""

import re
from fractions import Fraction

from rule_parser import sentences

LABOR = "근로기준법"
EQUAL = "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률"
RETIRE = "근로자퇴직급여 보장법"
AGE = "고용상 연령차별금지 및 고령자고용촉진에 관한 법률"

VIOLATION, REVIEW, OK = "위반 의심", "확인 필요", "적합"
PRESENT, PARTIAL, MISSING = "기재됨", "일부 누락", "누락"


def norm(text):
    return re.sub(r"\s+", "", text or "")


def _text(article):
    return norm(article["제목"] + " " + article["내용"])


def find_articles(articles, keywords, scope=None):
    """키워드 중 하나라도 포함한 조항. scope가 있으면 그 단어가 있는 조항 안에서만 찾는다."""
    hits = []
    for a in articles:
        t = _text(a)
        if scope and scope not in t:
            continue
        if any(k in t for k in keywords):
            hits.append(a)
    # 제목에 키워드가 있는 조항을 앞에 둔다
    return sorted(hits, key=lambda a: not any(k in norm(a["제목"]) for k in keywords))


# ---------------------------------------------------------------------------
# 1. 필수 기재사항 (근로기준법 제93조)
# 각 세부 항목: (이름, 키워드, 해당 시에만 필요한지, scope)
# ---------------------------------------------------------------------------
REQUIRED_ITEMS = [
    ("1", "업무의 시작·종료 시각, 휴게시간, 휴일, 휴가, 교대 근로", [
        ("시업·종업 시각", ["시업", "종업", "출근시각", "퇴근시각", "업무의시작", "시작시각", "종료시각", "근로시간은"], False, None),
        ("휴게시간", ["휴게"], False, None),
        ("휴일", ["휴일"], False, None),
        ("휴가", ["휴가"], False, None),
        ("교대 근로", ["교대"], True, None),
    ]),
    ("2", "임금의 결정·계산·지급 방법, 산정기간·지급시기, 승급", [
        ("결정·계산·지급 방법", ["임금의결정", "임금의계산", "임금의구성", "임금계산", "지급방법", "통화로", "계좌"], False, None),
        ("산정기간·지급시기", ["지급일", "지급시기", "산정기간", "매월"], False, None),
        ("승급", ["승급", "호봉", "임금인상", "승호", "임금조정"], False, None),
    ]),
    ("3", "가족수당의 계산·지급 방법", [
        ("가족수당", ["가족수당"], True, None),
    ]),
    ("4", "퇴직에 관한 사항", [
        ("퇴직", ["퇴직", "정년", "사직", "해고"], False, None),
    ]),
    ("5", "퇴직급여, 상여, 최저임금", [
        ("퇴직급여", ["퇴직금", "퇴직급여", "퇴직연금"], False, None),
        ("상여", ["상여"], True, None),
        ("최저임금", ["최저임금"], False, None),
    ]),
    ("6", "식비·작업 용품 등의 근로자 부담", [
        ("식비·작업 용품 부담", ["식비", "식대", "작업용품", "작업복", "피복", "비용부담"], True, None),
    ]),
    ("7", "근로자를 위한 교육시설", [
        ("교육시설", ["교육시설", "교육훈련", "교육"], True, None),
    ]),
    ("8", "모성 보호 및 일·가정 양립 지원", [
        ("출산전후휴가", ["출산전후휴가", "출산휴가", "산전후휴가"], False, None),
        ("배우자 출산휴가", ["배우자출산휴가", "배우자의출산"], False, None),
        ("육아휴직", ["육아휴직"], False, None),
        ("육아기 근로시간 단축", ["육아기근로시간단축", "육아기"], False, None),
    ]),
    ("9", "안전과 보건", [
        ("안전·보건", ["안전보건", "안전과보건", "산업안전", "보건", "건강진단"], False, None),
    ]),
    ("9의2", "성별·연령·신체적 조건 등에 따른 사업장 환경 개선", [
        ("사업장 환경 개선", ["환경의개선", "환경개선", "작업환경", "근무환경"], False, None),
    ]),
    ("10", "업무상과 업무 외의 재해부조", [
        ("업무상 재해", ["업무상재해", "산업재해", "재해보상", "요양보상", "업무상부상"], False, None),
        ("업무 외 재해부조", ["업무외", "재해부조", "부조"], False, None),
    ]),
    ("11", "직장 내 괴롭힘의 예방 및 발생 시 조치", [
        ("괴롭힘 예방", ["직장내괴롭힘"], False, None),
        ("발생 시 조치", ["조사", "신고", "조치"], False, "괴롭힘"),
    ]),
    ("12", "표창과 제재", [
        ("표창", ["표창", "포상"], False, None),
        ("제재", ["징계", "제재", "감급", "견책"], False, None),
    ]),
]


def check_required(articles):
    results = []
    for no, title, subs in REQUIRED_ITEMS:
        details = []
        for name, keywords, optional, scope in subs:
            hits = find_articles(articles, keywords, scope)
            details.append({
                "세부": name,
                "해당 시만": optional,
                "조항": [a["조항"] for a in hits],
            })
        required = [d for d in details if not d["해당 시만"]]
        found = [d for d in required if d["조항"]]
        if not required:  # 모두 '해당 시에만' 필요한 항목
            status = PRESENT if any(d["조항"] for d in details) else REVIEW
        elif len(found) == len(required):
            status = PRESENT
        elif found:
            status = PARTIAL
        else:
            status = MISSING
        results.append({"번호": no, "항목": title, "상태": status, "세부": details})
    return results


# ---------------------------------------------------------------------------
# 2. 위반 점검
# ---------------------------------------------------------------------------
def _finding(topic, status, basis, explain, article=None, excerpt="", fix=None):
    """fix: 신구대조표 초안에 쓸 개정 방법.
    {"pattern", "repl"}: 발췌 문장에서 pattern을 repl로 한 번 바꾼다
    {"add"}: 조항 끝에 문장을 덧붙인다
    {"new"}: 조항을 새로 만든다
    """
    return {
        "주제": topic,
        "상태": status,
        "조항": article["조항"] if article else "",
        "발췌": excerpt,
        "설명": explain,
        "근거": basis,  # [(법령명, 조문), ...]
        "fix": fix,
    }


def _swap(value, unit, new):
    """발췌 문장의 '{value}{unit}'(사이 공백 허용)을 new로 바꾸는 fix."""
    return {"pattern": rf"(?<![\d.]){value}\s*{unit}", "repl": new}


def _sentences_with(articles, keywords, exclude=()):
    """키워드를 포함한 (조항, 원문 문장, 공백 제거 문장) 목록."""
    out = []
    for a in articles:
        for s in sentences(a["내용"]):
            n = norm(s)
            if any(k in n for k in keywords) and not any(x in n for x in exclude):
                out.append((a, s, n))
    return out


def _ints(pattern, text):
    return [int(x) for x in re.findall(pattern, text)]


# 원문(공백 포함)에서 비율 표현 하나를 찾는 패턴
RATIO = r"(?:\d+\s*분의\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?\s*(?:%|퍼센트|프로))"


def _ratios(text):
    """'2분의 1', '1/2', '10%' 같은 비율 표현을 모두 찾는다."""
    vals = [Fraction(int(b), int(a)) for a, b in re.findall(r"(\d+)분의(\d+)", text) if int(a)]
    vals += [Fraction(int(a), int(b)) for a, b in re.findall(r"(?<![\d.])(\d+)/(\d+)", text) if int(b)]
    vals += [Fraction(x) / 100 for x in re.findall(r"(\d+(?:\.\d+)?)(?:%|퍼센트|프로)", text)]
    return vals


def check_working_hours(articles):
    basis = [(LABOR, "제50조")]
    out = []
    for a, s, n in _sentences_with(articles, ["근로시간", "근무시간", "소정근로"],
                                   exclude=("연장", "초과", "탄력", "선택적", "야간", "휴일근로")):
        for h in _ints(r"1주(?:간|일)?[^\d]{0,25}?(\d+)시간", n):
            if h > 40:
                out.append(_finding("1주 근로시간", VIOLATION, basis,
                                    f"1주 소정근로시간 {h}시간이 법정 한도(40시간)를 넘습니다. 탄력적 근로시간제 등 예외 요건을 갖췄는지 확인하세요.", a, s,
                                    _swap(h, "시간", "40시간")))
        for h in _ints(r"1일[^\d]{0,25}?(\d+)시간", n):
            if h > 8:
                out.append(_finding("1일 근로시간", VIOLATION, basis,
                                    f"1일 소정근로시간 {h}시간이 법정 한도(8시간)를 넘습니다.", a, s,
                                    _swap(h, "시간", "8시간")))
    return out


def check_overtime(articles):
    basis = [(LABOR, "제53조")]
    hits = _sentences_with(articles, ["연장근로", "연장근무", "시간외근로", "시간외근무"])
    if not hits:
        return []
    out = []
    for a, s, n in hits:
        for h in _ints(r"1주(?:간|일)?[^\d]{0,25}?(\d+)시간", n):
            if h > 12:
                out.append(_finding("연장근로 한도", VIOLATION, basis,
                                    f"1주 연장근로 {h}시간이 한도(12시간)를 넘습니다.", a, s,
                                    _swap(h, "시간", "12시간")))
    if not any("합의" in n or "동의" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("연장근로 합의", REVIEW, basis,
                            "연장근로는 근로자와 합의(동의)가 있어야 합니다. 합의 절차가 규정에 있는지 확인하세요.", a, s,
                            {"add": "연장근로는 직원과 합의한 경우에 한하여 1주 12시간을 한도로 실시한다."}))
    return out


def check_break(articles):
    basis = [(LABOR, "제54조")]
    hits = find_articles(articles, ["휴게"])
    if not hits:
        return []
    t = "".join(_text(a) for a in hits)
    if ("4시간" in t and "30분" in t) and ("8시간" in t and "1시간" in t):
        return [_finding("휴게시간", OK, basis, "4시간에 30분, 8시간에 1시간 이상 휴게 기준이 모두 있습니다.", hits[0])]
    return [_finding("휴게시간", REVIEW, basis,
                     "근로시간 4시간에 30분 이상, 8시간에 1시간 이상의 휴게를 근로시간 도중에 주도록 되어 있는지 확인하세요.", hits[0],
                     fix={"add": "회사는 근로시간이 4시간인 경우에는 30분 이상, 8시간인 경우에는 1시간 이상의 휴게시간을 근로시간 도중에 준다."})]


def check_annual_leave(articles):
    basis = [(LABOR, "제60조")]
    hits = _sentences_with(articles, ["연차"])
    if not hits:
        return []
    out = []
    for a, s, n in hits:
        if "80" in n or "8할" in n:
            days = _ints(r"(\d+)일의?유급휴가", n) or _ints(r"(\d+)일", n.split("80", 1)[-1])
            if days and days[0] < 15:
                out.append(_finding("연차유급휴가 일수", VIOLATION, basis,
                                    f"1년간 80% 이상 출근한 근로자의 연차가 {days[0]}일로, 법정 15일보다 적습니다.", a, s,
                                    _swap(days[0], "일", "15일")))
    if not any("1개월" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("1년 미만 근로자 연차", REVIEW, basis,
                            "계속근로 1년 미만(또는 출근율 80% 미만)인 근로자에게 1개월 개근 시 1일의 유급휴가를 주는 규정이 있는지 확인하세요.", a, s,
                            {"add": "계속하여 근로한 기간이 1년 미만인 직원 또는 1년간 80퍼센트 미만 출근한 직원에게는 1개월 개근 시 1일의 유급휴가를 준다."}))
    return out


def check_dismissal_notice(articles):
    basis = [(LABOR, "제26조"), (LABOR, "제27조")]
    hits = _sentences_with(articles, ["해고"])
    if not hits:
        return []
    out = []
    for a, s, n in hits:
        if "예고" in n or "전에" in n:
            for d in _ints(r"(\d+)일전", n):
                if d < 30:
                    out.append(_finding("해고예고", VIOLATION, basis,
                                        f"해고예고 기간이 {d}일로, 법정 30일보다 짧습니다.", a, s,
                                        _swap(d, "일", "30일")))
    if not out and not any("30일" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("해고예고", REVIEW, basis,
                            "해고할 때 30일 전에 예고하거나 30일분 이상의 통상임금을 지급하는 규정, 해고 사유·시기의 서면 통지 규정이 있는지 확인하세요.", a, s,
                            {"add": "회사는 직원을 해고하려면 적어도 30일 전에 예고하여야 하고, 30일 전에 예고하지 아니하였을 때에는 30일분 이상의 통상임금을 지급한다. 해고는 해고사유와 해고시기를 서면으로 통지하여야 효력이 있다."}))
    return out


def check_pay_cut(articles):
    basis = [(LABOR, "제95조")]
    hits = _sentences_with(articles, ["감급", "감봉"])
    if not hits:
        return []
    out = []
    has_limit = False
    for a, s, n in hits:
        ratios = _ratios(n)
        if not ratios:
            continue
        has_limit = True
        if "1일분" in n:
            if max(ratios) > Fraction(1, 2):
                out.append(_finding("감급 한도(1회)", VIOLATION, basis,
                                    "1회 감급액이 평균임금 1일분의 2분의 1을 넘습니다.", a, s,
                                    {"pattern": RATIO, "repl": "2분의 1"}))
        elif max(ratios) > Fraction(1, 10):
            out.append(_finding("감급 한도(총액)", VIOLATION, basis,
                                "감급 총액이 1임금지급기 임금총액의 10분의 1을 넘을 수 있습니다.", a, s,
                                {"pattern": RATIO, "repl": "10분의 1"}))
    if not has_limit:
        a, s, _ = hits[0]
        out.append(_finding("감급 한도", REVIEW, basis,
                            "감급은 1회 평균임금 1일분의 2분의 1, 총액은 1임금지급기 임금총액의 10분의 1을 넘을 수 없습니다. 이 한도를 규정에 명시하는 것이 좋습니다.", a, s,
                            {"add": "감급은 1회의 금액이 평균임금의 1일분의 2분의 1을, 총액이 1임금지급기의 임금 총액의 10분의 1을 초과하지 못한다."}))
    return out


def check_maternity(articles):
    basis = [(LABOR, "제74조")]
    hits = _sentences_with(articles, ["출산전후휴가", "출산휴가", "산전후휴가"], exclude=("배우자",))
    if not hits:
        return []
    out = []
    for a, s, n in hits:
        days = _ints(r"(\d+)일", n)
        if days and max(days) < 90:
            out.append(_finding("출산전후휴가 기간", VIOLATION, basis,
                                f"출산전후휴가가 {max(days)}일로, 법정 90일보다 짧습니다.", a, s,
                                _swap(max(days), "일", "90일")))
    if not any("120" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("다태아 출산전후휴가", REVIEW, basis,
                            "한 번에 둘 이상 자녀를 임신한 경우 출산전후휴가 120일 규정이 있는지 확인하세요.", a, s,
                            {"add": "한 번에 둘 이상 자녀를 임신한 경우에는 120일의 출산전후휴가를 준다."}))
    return out


def check_spouse_leave(articles):
    basis = [(EQUAL, "제18조의2")]
    hits = _sentences_with(articles, ["배우자출산휴가", "배우자의출산"])
    out = []
    for a, s, n in hits:
        days = _ints(r"(\d+)일", n)
        if days and max(days) < 20:
            out.append(_finding("배우자 출산휴가 기간", VIOLATION, basis,
                                f"배우자 출산휴가가 {max(days)}일로 되어 있습니다. 현행 법정 일수(20일)보다 짧은지 법령 원문으로 확인하세요.", a, s,
                                _swap(max(days), "일", "20일")))
    return out


def check_parental_leave(articles):
    basis = [(EQUAL, "제19조")]
    out = []
    for a, s, n in _sentences_with(articles, ["육아휴직"]):
        if "기간" not in n:
            continue
        periods = [(y * 12, y, "년") for y in _ints(r"(\d+)년", n)] + [(m, m, "개월") for m in _ints(r"(\d+)개월", n)]
        if periods and max(periods)[0] < 12:
            months, value, unit = max(periods)
            out.append(_finding("육아휴직 기간", VIOLATION, basis,
                                f"육아휴직 기간이 {months}개월로, 법정 기간(1년 이상)보다 짧습니다.", a, s,
                                _swap(value, unit, "1년")))
    return out


def check_retirement_age(articles):
    basis = [(AGE, "제19조")]
    out = []
    for a, s, n in _sentences_with(articles, ["정년"]):
        for age in _ints(r"(\d+)세", n):
            if 40 <= age < 60:
                out.append(_finding("정년", VIOLATION, basis,
                                    f"정년이 {age}세로, 법정 정년(60세 이상)보다 낮습니다.", a, s,
                                    _swap(age, "세", "60세")))
    return out


def check_severance(articles):
    basis = [(RETIRE, "제4조"), (RETIRE, "제8조")]
    hits = _sentences_with(articles, ["퇴직금", "퇴직급여"])
    if not hits:
        return []
    out = []
    for a, s, n in hits:
        for y in _ints(r"(\d+)년이상", n):
            if y > 1:
                out.append(_finding("퇴직급여 지급 요건", VIOLATION, basis,
                                    f"계속근로 {y}년 이상을 요건으로 하고 있습니다. 법정 요건은 1년 이상입니다.", a, s,
                                    _swap(y, "년", "1년")))
    if not any("30일분" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("퇴직금 산정", REVIEW, basis,
                            "계속근로기간 1년에 대해 30일분 이상의 평균임금을 퇴직금으로 지급하는지(또는 퇴직연금 제도) 확인하세요.", a, s,
                            {"add": "퇴직금은 계속근로기간 1년에 대하여 30일분 이상의 평균임금으로 한다."}))
    return out


def check_sexual_harassment(articles):
    basis = [(EQUAL, "제13조"), (EQUAL, "제14조")]
    if find_articles(articles, ["성희롱"]):
        return []
    return [_finding("직장 내 성희롱 예방", REVIEW, basis,
                     "직장 내 성희롱 예방교육과 발생 시 조치에 관한 규정이 보이지 않습니다. 법정 의무이므로 규정에 두는 것이 좋습니다.",
                     fix={"new": "제○조(직장 내 성희롱의 금지 및 예방) ① 누구든지 직장 내 성희롱을 하여서는 아니 된다.\n"
                                 "② 회사는 직장 내 성희롱 예방을 위한 교육을 연 1회 이상 실시한다.\n"
                                 "③ 회사는 직장 내 성희롱 발생 사실을 알게 된 경우 지체 없이 사실 확인을 위한 조사를 하고, 피해근로자를 보호하기 위하여 필요한 조치를 한다."})]


CHECKS = [
    check_working_hours,
    check_overtime,
    check_break,
    check_annual_leave,
    check_dismissal_notice,
    check_pay_cut,
    check_maternity,
    check_spouse_leave,
    check_parental_leave,
    check_retirement_age,
    check_severance,
    check_sexual_harassment,
]


def check_violations(articles):
    body = [a for a in articles if not a["부칙"]]
    findings = []
    for check in CHECKS:
        findings += check(body)
    order = {VIOLATION: 0, REVIEW: 1, OK: 2}
    return sorted(findings, key=lambda f: order[f["상태"]])

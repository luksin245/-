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


def _has(keyword, text):
    """키워드가 text에 있는지. 're:'로 시작하면 정규식으로 찾는다."""
    if keyword.startswith("re:"):
        return re.search(keyword[3:], text) is not None
    return keyword in text


def find_articles(articles, keywords, scope=None):
    """키워드 중 하나라도 포함한 조항. scope가 있으면 그 단어가 있는 조항 안에서만 찾는다."""
    hits = []
    for a in articles:
        t = _text(a)
        if scope and scope not in t:
            continue
        if any(_has(k, t) for k in keywords):
            hits.append(a)
    # 제목에 키워드가 있는 조항을 앞에 둔다
    return sorted(hits, key=lambda a: not any(_has(k, norm(a["제목"])) for k in keywords))


# ---------------------------------------------------------------------------
# 1. 필수 기재사항 (근로기준법 제93조, 고용노동부 표준취업규칙(2026. 2.)의 [필수] 조항 기준)
# 각 세부 항목: (이름, 키워드, 해당 시에만 필요한지, scope)
# ---------------------------------------------------------------------------
REQUIRED_ITEMS = [
    ("총칙", "목적·적용범위", [
        ("목적", ["목적"], False, None),
        ("적용범위", ["적용범위", "적용대상", "에게적용한다"], False, None),
    ]),
    ("1", "업무의 시작·종료 시각, 휴게시간, 휴일, 휴가, 교대 근로", [
        ("시업·종업 시각", ["시업", "종업", "출근시각", "퇴근시각", "업무의시작", "시작시각", "종료시각", "근로시간은"], False, None),
        ("휴게시간", ["휴게"], False, None),
        ("연장·야간·휴일근로", ["연장근로", "야간근로", "휴일근로", "시간외근로"], False, None),
        ("유급휴일(주휴일)", ["주휴", "유급휴일"], False, None),
        ("공휴일 유급휴일", ["공휴일", "관공서"], False, None),
        ("연차유급휴가", ["연차"], False, None),
        ("교대 근로", ["교대"], True, None),
    ]),
    ("2", "임금의 결정·계산·지급 방법, 산정기간·지급시기, 승급", [
        ("임금 구성항목", ["구성항목", "임금의구성", "기본급"], False, None),
        ("결정·계산·지급 방법", ["임금의결정", "임금의계산", "임금의구성", "임금계산", "지급방법", "통화로", "계좌"], False, None),
        ("산정기간·지급시기", ["지급일", "지급시기", "산정기간", "매월"], False, None),
        ("임금명세서 교부", ["임금명세서"], False, None),
        ("승급", ["승급", "호봉", "임금인상", "승호", "임금조정"], False, None),
    ]),
    ("3", "가족수당의 계산·지급 방법", [
        ("가족수당", ["가족수당"], True, None),
    ]),
    ("4", "퇴직에 관한 사항", [
        ("퇴직 사유·퇴직일", ["퇴직", "사직"], False, None),
        ("정년", ["정년"], False, None),
    ]),
    ("5", "퇴직급여, 상여 및 최저임금", [
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
        ("출산전후휴가", ["출산전후휴가", "산전후휴가", "re:(?<!배우자)(?<!배우자의)출산휴가"], False, None),
        ("유산·사산휴가", ["유산", "사산"], False, None),
        ("임신기 근로시간 단축", ["임신기근로시간단축", "12주이내", "32주이후", "36주이후"], False, None),
        ("임신 중 업무 시작·종료 시각 변경", ["종료시각의변경", "종료시각변경", "시작및종료시각"], False, "임신"),
        ("태아검진 시간", ["태아검진", "정기건강진단"], False, None),
        ("임산부·18세 미만 야간·휴일근로 제한", ["임산부", "임신중", "산후1년", "18세미만"], False, "야간"),
        ("생리휴가", ["생리휴가"], False, None),
        ("육아시간(수유시간)", ["육아시간", "수유시간"], False, None),
        ("배우자 출산휴가", ["배우자출산휴가", "배우자의출산"], False, None),
        ("난임치료휴가", ["난임"], False, None),
        ("육아휴직", ["육아휴직"], False, None),
        ("육아기 근로시간 단축", ["육아기근로시간단축", "육아기"], False, None),
        ("가족돌봄휴직", ["가족돌봄휴직"], False, None),
        ("가족돌봄휴가", ["가족돌봄휴가"], False, None),
        ("가족돌봄 등을 위한 근로시간 단축", ["가족돌봄등을위한근로시간단축", "가족돌봄등을위한", "은퇴를준비"], False, None),
    ]),
    ("9", "안전과 보건", [
        ("안전보건교육", ["안전보건교육", "안전교육", "안전및보건에관한", "보건교육"], False, None),
        ("건강진단", ["건강진단"], False, None),
        ("산업안전보건법 준수", ["산업안전보건법", "안전보건", "안전과보건"], False, None),
        ("위험기계·기구 방호조치", ["방호"], True, None),
        ("보호구 지급·착용", ["보호구"], True, None),
        ("물질안전보건자료", ["물질안전보건자료"], True, None),
        ("작업환경측정", ["작업환경측정"], True, None),
    ]),
    ("9의2", "성별·연령·신체적 조건 등에 따른 사업장 환경 개선", [
        ("사업장 환경 개선", ["환경의개선", "환경개선", "작업환경", "근무환경"], False, None),
    ]),
    ("10", "업무상과 업무 외의 재해부조", [
        ("업무상 재해", ["업무상재해", "산업재해", "재해보상", "요양보상", "업무상부상"], False, None),
        ("업무 외 재해부조", ["업무외", "재해부조", "부조"], False, None),
    ]),
    ("11", "직장 내 괴롭힘의 예방 및 발생 시 조치", [
        ("괴롭힘 금지", ["직장내괴롭힘"], False, None),
        ("예방교육", ["예방교육", "교육"], False, "괴롭힘"),
        ("신고·접수", ["신고", "접수"], False, "괴롭힘"),
        ("조사", ["조사"], False, "괴롭힘"),
        ("피해자 보호", ["피해자", "피해근로자", "피해사원", "피해직원", "피해를입은"], False, "괴롭힘"),
        ("행위자 조치", ["행위자", "징계"], False, "괴롭힘"),
        ("불리한 처우 금지", ["불리한처우", "불이익"], False, "괴롭힘"),
        ("비밀 누설 금지", ["비밀", "누설"], False, "괴롭힘"),
    ]),
    ("12", "표창과 제재", [
        ("표창", ["표창", "포상"], False, None),
        ("징계 사유·종류", ["징계", "제재", "감급", "견책"], False, None),
        ("징계 절차(심의·소명)", ["소명", "징계심의", "징계위원회", "인사위원회", "징계의결"], False, None),
        ("징계 결과 통보", ["통보", "통지"], False, "징계"),
    ]),
]


def skipped_items():
    """'해당하는 경우에만' 적으면 되는 항목. 사업장마다 달라 점검하지 않는다."""
    return [f"{name}({no}호)" if all(o for *_, o, _ in subs) else name
            for no, _, subs in REQUIRED_ITEMS
            for name, _, optional, _ in subs if optional]


def check_required(articles):
    results = []
    for no, title, subs in REQUIRED_ITEMS:
        details = [{"세부": name, "조항": [a["조항"] for a in find_articles(articles, keywords, scope)]}
                   for name, keywords, optional, scope in subs if not optional]
        if not details:  # 모두 '해당하는 경우에만' 필요한 항목
            continue
        found = [d for d in details if d["조항"]]
        status = PRESENT if len(found) == len(details) else PARTIAL if found else MISSING
        results.append({"번호": no, "항목": title, "상태": status, "세부": details})
    return results


# ---------------------------------------------------------------------------
# 2. 위반 점검
# ---------------------------------------------------------------------------
def _finding(topic, status, basis, explain, article=None, excerpt="", fix=None):
    """fix: 신구대조표 초안에 쓸 개정 방법.
    {"pattern", "repl"}: 발췌 문장에서 pattern을 repl로 한 번 바꾼다
    {"subs": [(pattern, repl), ...]}: 여러 군데를 차례로 바꾼다
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
    titled = sorted(articles, key=lambda a: not any(k in norm(a["제목"]) for k in keywords))
    for a in titled:
        for s in sentences(a["내용"]):
            n = norm(s)
            if any(k in n for k in keywords) and not any(x in n for x in exclude):
                out.append((a, s, n))
    return out


def _article_sentences(articles, keywords):
    """키워드가 들어 있는 조항의 모든 문장. 둘째 항부터 키워드를 되풀이하지 않는 조항에 쓴다."""
    return [(a, s, norm(s)) for a in find_articles(articles, keywords) for s in sentences(a["내용"])]


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
        if "초과하여" in n or "초과한" in n:  # "1주 40시간을 초과하여 연장근로하는 경우" 같은 기준 문장
            continue
        for h in _ints(r"1주(?:간|일)?[^\d]{0,25}?(\d+)시간(?![을를]?초과)", n):
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
    hits = _article_sentences(articles, ["연차유급휴가", "연차휴가"])
    if not hits:
        return []
    out = []
    for a, s, n in hits:
        if re.search(r"(80(퍼센트|%|프로)|8할)이상", n) and "미만" not in n:
            days = _ints(r"(\d+)일의?유급휴가", n) or _ints(r"(\d+)일", n.split("80", 1)[-1])
            if days and days[0] < 15:
                out.append(_finding("연차유급휴가 일수", VIOLATION, basis,
                                    f"1년간 80% 이상 출근한 근로자의 연차가 {days[0]}일로, 법정 15일보다 적습니다.", a, s,
                                    _swap(days[0], "일", "15일")))
    if not any("25일" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("연차 가산휴가(최대 25일)", REVIEW, basis,
                            "3년 이상 근속한 근로자에게 최초 1년을 초과하는 근속 2년마다 1일을 가산하고 총 25일을 한도로 하는 규정이 있는지 확인하세요.", a, s,
                            {"add": "3년 이상 계속하여 근로한 직원에게는 최초 1년을 초과하는 계속 근로 연수 매 2년에 대하여 1일을 가산한 유급휴가를 주며, "
                                    "가산휴가를 포함한 총 휴가 일수는 25일을 한도로 한다."}))
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
    hits = _sentences_with(articles, ["출산전후휴가", "출산휴가", "산전후휴가"], exclude=("배우자", "급여", "최초", "차액"))
    if not hits:
        return []
    out = []
    for a, s, n in hits:
        days = _ints(r"(\d+)일", n)
        if days and max(days) < 90:
            out.append(_finding("출산전후휴가 기간", VIOLATION, basis,
                                f"출산전후휴가가 {max(days)}일로, 법정 90일보다 짧습니다.", a, s,
                                _swap(max(days), "일", "90일")))
    if not any("100일" in n or "미숙아" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("미숙아 출산전후휴가", REVIEW, basis,
                            "미숙아를 출산한 경우 출산전후휴가 100일 규정이 있는지 확인하세요. (2025. 2. 23. 시행)", a, s,
                            {"add": "미숙아를 출산한 경우에는 100일의 출산전후휴가를 준다."}))
    if not any("120" in n for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("다태아 출산전후휴가", REVIEW, basis,
                            "한 번에 둘 이상 자녀를 임신한 경우 출산전후휴가 120일 규정이 있는지 확인하세요.", a, s,
                            {"add": "한 번에 둘 이상 자녀를 임신한 경우에는 120일의 출산전후휴가를 준다."}))
    return out


def check_spouse_leave(articles):
    basis = [(EQUAL, "제18조의2")]
    hits = _article_sentences(articles, ["배우자출산휴가", "배우자의출산"])
    out = []
    for a, s, n in hits:
        days = _ints(r"(\d+)일", n)
        if days and max(days) < 20:
            out.append(_finding("배우자 출산휴가 기간", VIOLATION, basis,
                                f"배우자 출산휴가가 {max(days)}일로 되어 있습니다. 현행 법정 일수(20일)보다 짧은지 법령 원문으로 확인하세요.", a, s,
                                _swap(max(days), "일", "20일")))
        if "90일" in n and ("지나" in n or "이내" in n or "청구" in n):
            out.append(_finding("배우자 출산휴가 청구기간", VIOLATION, basis,
                                "배우자 출산휴가는 배우자가 출산한 날부터 120일 이내에 쓸 수 있습니다. (2025. 2. 23. 시행)", a, s,
                                _swap(90, "일", "120일")))
        m = re.search(r"(\d)회에?한(?:정)?하여", n)
        if m and "나누어" in n and int(m.group(1)) < 3:
            out.append(_finding("배우자 출산휴가 분할 사용", VIOLATION, basis,
                                f"배우자 출산휴가는 3회까지 나누어 쓸 수 있습니다. 규칙에는 {m.group(1)}회로 되어 있습니다. (2025. 2. 23. 시행)", a, s,
                                _swap(m.group(1), "회", "3회")))
    return out


def check_parental_leave(articles):
    basis = [(EQUAL, "제19조")]
    out = []
    hits = _sentences_with(articles, ["육아휴직"], exclude=("근로시간단축",))
    for a, s, n in hits:
        m = re.search(r"(\d)회", n)
        if m and ("나누어" in n or "분할" in n) and int(m.group(1)) < 3:
            out.append(_finding("육아휴직 분할 사용", VIOLATION, [(EQUAL, "제19조의4")],
                                f"육아휴직은 3회까지 나누어 쓸 수 있습니다. 규칙에는 {m.group(1)}회로 되어 있습니다. (2025. 2. 23. 시행)", a, s,
                                _swap(m.group(1), "회", "3회")))
    long_ok = any("6개월" in n and ("추가" in n or "1년6개월" in n) for _, _, n in hits)
    period = [(a, s) for a, s, n in hits if "기간" in n or "1년" in n]
    if period and not long_ok:
        a, s = period[0]
        out.append(_finding("육아휴직 기간 연장(1년 6개월)", REVIEW, basis,
                            "부모가 각각 3개월 이상 사용한 경우, 한부모, 중증 장애아동의 부모는 육아휴직을 6개월 더(최대 1년 6개월) "
                            "쓸 수 있습니다. 이 규정이 있는지 확인하세요. (2025. 2. 23. 시행)", a, s,
                            {"add": "다만, 같은 자녀에 대하여 부모가 각각 3개월 이상 육아휴직을 사용한 경우의 부 또는 모, 한부모가족지원법에 따른 부 또는 모, "
                                    "고용노동부령으로 정하는 장애아동의 부 또는 모는 6개월 이내에서 추가로 육아휴직을 사용할 수 있다."}))
    for a, s, n in hits:
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
    if not any("개인형퇴직연금" in n or "IRP" in n.upper() for _, _, n in hits):
        a, s, _ = hits[0]
        out.append(_finding("퇴직급여 IRP 이전 지급", REVIEW, [(RETIRE, "제9조")],
                            "퇴직급여는 근로자가 지정한 개인형퇴직연금제도(IRP) 계정 등으로 이전해 지급해야 합니다(55세 이후 퇴직 등 예외 있음). "
                            "이 규정이 있는지 확인하세요.", a, s,
                            {"add": "퇴직급여는 직원이 지정한 개인형퇴직연금제도의 계정 또는 중소기업퇴직연금기금제도의 가입자부담금 계정으로 이전하는 방법으로 지급한다. "
                                    "다만, 55세 이후에 퇴직하는 경우 등 근로자퇴직급여 보장법령에서 정한 경우에는 그러하지 아니하다."}))
    return out


def check_overtime_premium(articles):
    basis = [(LABOR, "제56조")]
    out = []
    hits = _sentences_with(articles, ["가산"])
    for a, s, n in hits:
        if not any(k in n for k in ("연장", "야간", "휴일", "시간외")):
            continue
        ratios = _ratios(n)
        if ratios and min(ratios) < Fraction(1, 2):
            out.append(_finding("연장·야간·휴일근로 가산임금", VIOLATION, basis,
                                "연장·야간·휴일근로에는 통상임금의 100분의 50 이상을 가산해야 합니다.", a, s,
                                {"pattern": RATIO, "repl": "100분의 50"}))
    holiday = _article_sentences(articles, ["휴일근로"])
    full = [norm(a["내용"]) for a in articles]
    has_100 = any("휴일" in t and any(k in t for k in ("100분의100", "100%", "100퍼센트")) for t in full)
    if holiday and not has_100:
        a, s, _ = holiday[0]
        out.append(_finding("8시간 초과 휴일근로 가산", REVIEW, basis,
                            "휴일근로 중 8시간을 넘는 부분은 통상임금의 100분의 100 이상을 가산해야 합니다. 이 규정이 있는지 확인하세요.", a, s,
                            {"add": "휴일근로 중 8시간을 초과한 근로에 대하여는 통상임금의 100분의 100 이상을 가산하여 지급한다."}))
    return out


def check_pregnancy(articles):
    """유산·사산휴가, 임신기 근로시간 단축 (근로기준법 제74조)"""
    basis = [(LABOR, "제74조")]
    out = []
    for a, s, n in _sentences_with(articles, ["유산", "사산"]):
        if "11주" in n and "5일" in n:
            out.append(_finding("유산·사산휴가 기간", VIOLATION, basis,
                                "임신 15주 이내 유산·사산 시 휴가가 5일에서 10일로 늘었습니다(11주 이내 5일·12~15주 10일 → 15주 이내 10일). "
                                "12주 이상 15주 이내 구간이 따로 있으면 함께 정리하세요. (2025. 2. 23. 시행)", a, s,
                                {"subs": [(r"11\s*주", "15주"), (r"(?<![\d.])5\s*일", "10일")]}))
    for a, s, n in _sentences_with(articles, ["36주"]):
        if "임신" in n and "단축" in n:
            out.append(_finding("임신기 근로시간 단축 기간", VIOLATION, basis,
                                "임신기 근로시간 단축은 임신 후 12주 이내 또는 32주 이후에 쓸 수 있습니다. 규칙에는 36주로 되어 있습니다. (2025. 2. 23. 시행)", a, s,
                                _swap(36, "주", "32주")))
    return out


def check_infertility(articles):
    basis = [(EQUAL, "제18조의3")]
    out = []
    for a, s, n in _sentences_with(articles, ["난임"]):
        days = _ints(r"(\d+)일(?!전)", n)
        if "최초" not in n and days and max(days) < 6:
            out.append(_finding("난임치료휴가 기간", VIOLATION, basis,
                                f"난임치료휴가는 연간 6일(최초 2일 유급)입니다. 규칙에는 {max(days)}일로 되어 있습니다. (2025. 2. 23. 시행)", a, s,
                                _swap(max(days), "일", "6일")))
        elif re.search(r"연간3일", n) or re.search(r"최초1일", n):
            subs = [(r"연간\s*3\s*일", "연간 6일"), (r"최초\s*1\s*일", "최초 2일")]
            out.append(_finding("난임치료휴가 기간", VIOLATION, basis,
                                "난임치료휴가는 연간 6일, 그중 최초 2일은 유급입니다. (2025. 2. 23. 시행)", a, s, {"subs": subs}))
    return out


def check_childcare_reduction(articles):
    """육아기 근로시간 단축 (남녀고용평등법 제19조의2, 제19조의4 — 2025. 2. 23. 시행 기준)"""
    out = []
    basis = [(EQUAL, "제19조의2")]
    for a, s, n in _article_sentences(articles, ["육아기근로시간단축"]):
        # 대상 자녀: 직접 '8세·2학년'으로 쓴 경우와 '육아휴직을 신청할 수 있는 사원'으로 육아휴직 대상(8세)을 끌어온 경우
        if re.search(r"(?<!\d)8세", n) or "2학년" in n:
            out.append(_finding("육아기 근로시간 단축 대상 자녀", VIOLATION, basis,
                                "육아기 근로시간 단축 대상 자녀가 만 12세 이하 또는 초등학교 6학년 이하로 넓어졌습니다. (2025. 2. 23. 시행)", a, s,
                                {"subs": [(r"(?<!\d)8\s*세", "12세"), (r"2\s*학년", "6학년")]}))
        elif "육아휴직을신청할수있는" in n and "신청하는경우" in n and "12세" not in n:
            out.append(_finding("육아기 근로시간 단축 대상 자녀", VIOLATION, basis,
                                "대상을 '육아휴직을 신청할 수 있는 사원'(만 8세·초2 이하 자녀)으로 정하고 있습니다. 육아기 근로시간 단축 대상은 "
                                "만 12세 이하 또는 초등학교 6학년 이하 자녀로 육아휴직보다 넓고, '육아휴직 대신' 쓰는 제도도 아닙니다. (2025. 2. 23. 시행)", a, s,
                                {"pattern": r"제\s*\d+\s*조\s*제\s*1\s*항에\s*따라\s*육아휴직을\s*신청할\s*수\s*있는\s*(?:남녀\s*)?(사원|직원|근로자)이\s*(?:육아휴직\s*대신\s*)?",
                                 "repl": "사원이 만 12세 이하 또는 초등학교 6학년 이하의 자녀를 양육하기 위하여 "}))
        # 기간: 미사용 육아휴직 기간의 두 배 가산
        if "사용하지아니한기간" in n and "가산" in n and not re.search(r"두배|2배", n):
            out.append(_finding("육아기 근로시간 단축 기간", VIOLATION, basis,
                                "육아휴직 기간 중 사용하지 않은 기간이 있으면 그 기간의 두 배를 가산한 기간까지 육아기 근로시간 단축을 쓸 수 있습니다. (2025. 2. 23. 시행)", a, s,
                                {"pattern": r"그\s*기간을\s*가산한", "repl": "그 기간의 두 배를 가산한"}))
        # 나누어 쓸 때 1회 최소 기간: 1개월
        if "나누어" in n and "1회의기간" in n and "1개월" not in n:
            out.append(_finding("육아기 근로시간 단축 최소 사용기간", VIOLATION, [(EQUAL, "제19조의4")],
                                "육아기 근로시간 단축을 나누어 쓸 때 1회 최소 기간은 1개월입니다(종전 3개월). (2025. 2. 23. 시행)", a, s,
                                {"subs": [(r"1회의\s*기간은\s*\d*\s*개월", "1회의 기간은 1개월"),
                                          (r"만료로\s*\d*\s*개월", "만료로 1개월")]}))
    return out


def check_leave_combination(articles):
    """육아휴직과 육아기 근로시간 단축을 합쳐 1년으로 묶는 옛 규정 (2019. 10. 1. 개정 전 방식)"""
    out = []
    for a, s, n in _article_sentences(articles, ["육아기근로시간단축"]):
        if re.search(r"총기간은1년을넘을수없", n):
            out.append(_finding("육아휴직·육아기 근로시간 단축 합산 제한", VIOLATION, [(EQUAL, "제19조의4")],
                                "육아휴직과 육아기 근로시간 단축을 합쳐 1년으로 제한하는 것은 옛 규정입니다. 지금은 육아휴직(1년, 일정 경우 1년 6개월)과 "
                                "육아기 근로시간 단축(1년 + 미사용 육아휴직 기간의 두 배)을 각각 쓸 수 있습니다.", a, s,
                                {"pattern": r"\s*이\s*경우\s*어느\s*방법을\s*사용하든지\s*그\s*총\s*기간은\s*1\s*년을\s*넘을\s*수\s*없다\.?",
                                 "repl": ""}))
    return out


def check_missing_numbers(articles):
    """PDF에서 숫자가 빠진 것으로 보이는 곳 ('기간이 개월 미만')"""
    out = []
    for a in articles:
        for s in sentences(a["내용"]):
            if re.search(r"(?:^|[^\d\s])\s+(개월|시간)\s*(이상|미만|이내|초과|까지)", s):
                out.append(_finding("숫자 누락 의심", REVIEW, [],
                                    "숫자 없이 '개월'·'시간'만 남은 곳이 있습니다. PDF에서 숫자가 빠졌거나 원본에 빈칸이 있는지 원본과 대조해 주세요.", a, s))
    return out


def check_family_care(articles):
    basis = [(EQUAL, "제22조의2")]
    out = []
    for a, s, n in _sentences_with(articles, ["가족돌봄휴가"]):
        days = _ints(r"(\d+)일(?!전)", n)
        if days and max(days) < 10:
            out.append(_finding("가족돌봄휴가 기간", VIOLATION, basis,
                                f"가족돌봄휴가는 연간 최장 10일입니다. 규칙에는 {max(days)}일로 되어 있습니다.", a, s,
                                _swap(max(days), "일", "10일")))
    for a, s, n in _sentences_with(articles, ["가족돌봄휴직"]):
        days = _ints(r"(\d+)일", n)
        if days and "연간" in n and max(days) < 90:
            out.append(_finding("가족돌봄휴직 기간", VIOLATION, basis,
                                f"가족돌봄휴직은 연간 최장 90일입니다. 규칙에는 {max(days)}일로 되어 있습니다.", a, s,
                                _swap(max(days), "일", "90일")))
    return out


def check_nursing_time(articles):
    basis = [(LABOR, "제75조")]
    out = []
    for a, s, n in _sentences_with(articles, ["육아시간", "수유시간"]):
        minutes = _ints(r"(\d+)분", n)
        times = _ints(r"1일(\d)회", n)
        if (minutes and min(minutes) < 30) or (times and times[0] < 2):
            out.append(_finding("육아시간(수유시간)", VIOLATION, basis,
                                "생후 1년 미만 자녀가 있는 여성 근로자에게는 1일 2회 각각 30분 이상의 유급 수유시간을 주어야 합니다.", a, s))
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
    check_overtime_premium,
    check_break,
    check_annual_leave,
    check_dismissal_notice,
    check_pay_cut,
    check_maternity,
    check_spouse_leave,
    check_parental_leave,
    check_childcare_reduction,
    check_leave_combination,
    check_pregnancy,
    check_infertility,
    check_family_care,
    check_nursing_time,
    check_retirement_age,
    check_severance,
    check_sexual_harassment,
    check_missing_numbers,
]


def check_violations(articles):
    body = [a for a in articles if not a["부칙"]]
    findings = []
    for check in CHECKS:
        findings += check(body)
    order = {VIOLATION: 0, REVIEW: 1, OK: 2}
    return sorted(findings, key=lambda f: order[f["상태"]])

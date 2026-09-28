"""표(엑셀 스타일) 형식의 은행 "계좌별거래내역" 텍스트 PDF 전용 파서.

인터넷뱅킹에서 내려받는 거래내역 PDF는 흔히 다음과 같은 표 형태다.

    No | 거래일시 | 적요 | 입금액 | 출금액 | 내용 | 잔액 | 거래점명 | 입금인코드 | 메모
    1  | 2026.09.22 12:16:03 | FB자금 | 329,725 | 0 | CMS집금 | 4,055,790 | 대기1 | ...

이 형식은 한 줄에 "입금"/"출금"이라는 단어가 직접 나오지 않고 숫자만 나열되어 있어,
local_ocr.py의 문장형 줄 단위 파서(_parse_line)로는 인식할 수 없다. 이 모듈은 PDF의
단어별 좌표(PyMuPDF의 "words" 모드)를 이용해 표의 행/열 구조를 직접 복원한다.

텍스트 레이어가 있는 PDF에서만 동작하며(스캔 이미지는 대상이 아님), 값이 애매하면
절대 추정하지 않고 None + '확인필요'로 남긴다 (다른 OCR 경로와 동일한 원칙).
"""
import re

from services.ocr.base import CANDIDATE_TEMPLATE, STATUS_NEEDS_REVIEW, STATUS_OK

# 헤더에 이 단어들이 모두 있어야 "표 형식 거래내역"으로 판단한다.
_REQUIRED_HEADER_LABELS = ("거래일시", "입금액", "출금액", "잔액")
_ALL_HEADER_LABELS = (
    "No", "거래일시", "적요", "입금액", "출금액", "내용", "잔액", "거래점명", "입금인코드", "메모",
)

# 텍스트 열(공백 없이 그대로 이어 붙여야 원래 값이 복원되는 열 - 한글 줄바꿈은
# 단어 중간에서 끊기는 경우가 많다).
_JOIN_NO_SPACE_COLUMNS = {"거래점명", "입금인코드", "메모"}
# 서로 다른 항목이라 공백으로 구분해 붙이는 게 자연스러운 열.
_JOIN_WITH_SPACE_COLUMNS = {"적요", "내용"}

_ROW_NUMBER_X_MAX = 32
_MAX_ASSIGN_DISTANCE = 12.0

_DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d):([0-5]\d)$")


def looks_like_transaction_table(page_text: str) -> bool:
    return all(label in page_text for label in _REQUIRED_HEADER_LABELS)


def _parse_amount_cell(text: str) -> int | None:
    cleaned = text.replace(",", "").replace("원", "").strip()
    if not cleaned or cleaned == "0" or not cleaned.lstrip("-").isdigit():
        return None
    value = int(cleaned)
    return value if value > 0 else None


def _find_row_markers(words: list[tuple]) -> list[tuple[int, float]]:
    """No 열(맨 왼쪽, 좁은 칸)에 있는 순번 후보를 y좌표와 함께 반환한다.

    1부터 순서대로 커지는 정수만 신뢰한다 - 합계 행 등 다른 숫자가 실수로
    섞여 들어오는 것을 막기 위해서다.
    """
    candidates = sorted(
        (w for w in words if w[0] <= _ROW_NUMBER_X_MAX and w[4].isdigit()),
        key=lambda w: w[1],
    )
    markers: list[tuple[int, float]] = []
    expected = 1
    for w in candidates:
        if int(w[4]) == expected:
            markers.append((expected, w[1]))
            expected += 1
    return markers


def _build_column_centers(words: list[tuple], header_y_cutoff: float) -> dict[str, float]:
    centers: dict[str, float] = {}
    for w in words:
        text = w[4]
        if text in _ALL_HEADER_LABELS and w[3] <= header_y_cutoff and text not in centers:
            centers[text] = (w[0] + w[2]) / 2
    return centers


def _nearest_label(x_center: float, column_centers: dict[str, float]) -> str:
    return min(column_centers, key=lambda label: abs(column_centers[label] - x_center))


def _reconstruct_datetime(tokens: list[str]) -> tuple[str | None, str | None]:
    """['2026.09.22', '12:', '16:03'] -> ('2026-09-22', '12:16:03') 형태로 복원한다.

    조합해도 유효한 날짜/시간이 되지 않으면 절대 추정하지 않고 None을 반환한다.
    """
    date_str = None
    rest: list[str] = []
    for t in tokens:
        if _DATE_RE.match(t):
            date_str = t.replace(".", "-")
        else:
            rest.append(t)

    time_str = None
    joined_time = "".join(rest)
    if _TIME_RE.match(joined_time):
        time_str = joined_time

    return date_str, time_str


def extract_candidates(page) -> list[dict]:
    """페이지 1개에서 표 형식 거래 후보 목록을 추출한다. 표 형식이 아니면 빈 목록."""
    page_text = page.get_text()
    if not looks_like_transaction_table(page_text):
        return []

    words = page.get_text("words")  # (x0, y0, x1, y1, text, block_no, line_no, word_no)
    markers = _find_row_markers(words)
    if not markers:
        return []

    header_y_cutoff = markers[0][1] - 2
    column_centers = _build_column_centers(words, header_y_cutoff)
    if not column_centers:
        return []

    marker_ys = [y for _, y in markers]

    # 각 단어를 가장 가까운 행(순번)에 배정한다 - 줄바꿈으로 다음/이전 행과
    # 시각적으로 가까워 보여도, PDF 블록 번호가 아니라 실제 y좌표 거리로
    # 판단해야 정확하다.
    rows: list[dict[str, list[tuple[float, float, str]]]] = [dict() for _ in markers]
    for w in words:
        if w[3] <= header_y_cutoff:
            continue
        y0 = w[1]
        distances = [abs(y0 - my) for my in marker_ys]
        best_idx = min(range(len(marker_ys)), key=lambda i: distances[i])
        if distances[best_idx] > _MAX_ASSIGN_DISTANCE:
            continue

        x_center = (w[0] + w[2]) / 2
        label = _nearest_label(x_center, column_centers)
        if label == "No":
            continue
        rows[best_idx].setdefault(label, []).append((y0, w[0], w[4]))

    candidates: list[dict] = []
    for row in rows:
        cells: dict[str, str] = {}
        for label, tokens in row.items():
            tokens.sort(key=lambda t: (t[0], t[1]))
            texts = [t[2] for t in tokens]
            if label == "거래일시":
                continue  # 아래에서 별도 처리
            elif label in _JOIN_NO_SPACE_COLUMNS:
                cells[label] = "".join(texts)
            elif label in _JOIN_WITH_SPACE_COLUMNS:
                cells[label] = " ".join(texts)
            else:
                cells[label] = "".join(texts)

        date_str = time_str = None
        if "거래일시" in row:
            tokens = sorted(row["거래일시"], key=lambda t: (t[0], t[1]))
            date_str, time_str = _reconstruct_datetime([t[2] for t in tokens])

        income = _parse_amount_cell(cells.get("입금액", ""))
        expense = _parse_amount_cell(cells.get("출금액", ""))
        balance = _parse_amount_cell(cells.get("잔액", ""))

        description = " ".join(
            part for part in (cells.get("적요"), cells.get("내용")) if part
        ).strip()

        candidate = dict(CANDIDATE_TEMPLATE)
        candidate.update(
            {
                "date": date_str,
                "time": time_str,
                "description": description,
                "income": income,
                "expense": expense,
                "balance": balance,
                "confidence": 100.0,
            }
        )

        if date_str is None or (income is None) == (expense is None):
            candidate["status"] = STATUS_NEEDS_REVIEW
        else:
            candidate["status"] = STATUS_OK

        candidates.append(candidate)

    return candidates

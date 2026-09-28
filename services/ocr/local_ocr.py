"""Tesseract 기반 로컬 OCR 엔진.

개인정보/금융정보 보호와 설치 편의성을 고려해, 외부로 이미지를 전송하지 않는
로컬 OCR을 기본으로 사용한다. Tesseract 실행파일이 시스템에 설치되어 있어야
하며(Windows는 별도 설치 필요), 설치되어 있지 않으면 알기 쉬운 오류 메시지를
그대로 올려보낸다 (조용히 잘못된 결과를 만들어내지 않는다).

파싱 규칙(중요): 날짜/금액이 명확하지 않으면 절대로 추정하지 않는다.
찾지 못한 값은 None으로 두고, status를 '확인필요'로 표시한다.
"""
import re
from io import BytesIO

from services.ocr.base import CANDIDATE_TEMPLATE, STATUS_NEEDS_REVIEW, STATUS_OK, OCREngine

CONFIDENCE_THRESHOLD = 60

_DATE_RE = re.compile(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})")
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")
_INCOME_RE = re.compile(r"입금\s*[:：]?\s*([0-9][0-9,]*)")
_EXPENSE_RE = re.compile(r"출금\s*[:：]?\s*([0-9][0-9,]*)")
_BALANCE_RE = re.compile(r"잔액\s*[:：]?\s*([0-9][0-9,]*)")


def _parse_amount(text: str | None) -> int | None:
    if not text:
        return None
    cleaned = text.replace(",", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _parse_line(line: str, confidence: float | None) -> dict | None:
    date_match = _DATE_RE.search(line)
    time_match = _TIME_RE.search(line)
    income_match = _INCOME_RE.search(line)
    expense_match = _EXPENSE_RE.search(line)
    balance_match = _BALANCE_RE.search(line)

    income = _parse_amount(income_match.group(1)) if income_match else None
    expense = _parse_amount(expense_match.group(1)) if expense_match else None
    balance = _parse_amount(balance_match.group(1)) if balance_match else None

    # 이 줄에서 거래로 볼 만한 단서(날짜 또는 금액)가 전혀 없으면 후보로 만들지 않는다
    # (표 제목/은행명 같은 줄을 걸러낸다).
    if not date_match and income is None and expense is None and balance is None:
        return None

    date_str = None
    if date_match:
        year, month, day = (int(g) for g in date_match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            date_str = f"{year:04d}-{month:02d}-{day:02d}"

    time_str = None
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        second = int(time_match.group(3)) if time_match.group(3) else 0
        if hour <= 23 and minute <= 59 and second <= 59:
            time_str = f"{hour:02d}:{minute:02d}:{second:02d}"

    description = line
    for m in (date_match, time_match, income_match, expense_match, balance_match):
        if m:
            description = description.replace(m.group(0), " ")
    description = re.sub(r"\s+", " ", description).strip()

    candidate = dict(CANDIDATE_TEMPLATE)
    candidate.update(
        {
            "date": date_str,
            "time": time_str,
            "description": description,
            "income": income,
            "expense": expense,
            "balance": balance,
            "confidence": round(confidence, 1) if confidence is not None else None,
        }
    )

    # 날짜가 불명확하거나, 입금/출금이 둘 다 없거나 둘 다 있으면 확실하지 않은 것이므로
    # 절대 추정하지 않고 '확인필요'로 표시한다.
    if (
        date_str is None
        or (income is None and expense is None)
        or (income is not None and expense is not None)
        or (confidence is not None and confidence < CONFIDENCE_THRESHOLD)
    ):
        candidate["status"] = STATUS_NEEDS_REVIEW
    else:
        candidate["status"] = STATUS_OK

    return candidate


def _group_words_into_lines(ocr_data: dict) -> list[tuple[str, float | None]]:
    """pytesseract.image_to_data 결과를 (줄 텍스트, 평균 신뢰도) 목록으로 묶는다."""
    lines: dict[tuple, list[tuple[str, float]]] = {}
    n = len(ocr_data["text"])
    for i in range(n):
        text = ocr_data["text"][i].strip()
        if not text:
            continue
        conf = float(ocr_data["conf"][i])
        key = (ocr_data["block_num"][i], ocr_data["par_num"][i], ocr_data["line_num"][i])
        lines.setdefault(key, []).append((text, conf))

    result = []
    for key in sorted(lines.keys()):
        words = lines[key]
        line_text = " ".join(w for w, _ in words)
        confs = [c for _, c in words if c >= 0]
        avg_conf = sum(confs) / len(confs) if confs else None
        result.append((line_text, avg_conf))
    return result


def _extract_from_image(image) -> list[dict]:
    import pytesseract

    try:
        # --psm 6: "균일한 텍스트 블록"으로 가정 - 기본(자동 레이아웃 분석) 모드보다
        # 통장 거래내역처럼 줄 단위로 나열된 표 형태 텍스트를 훨씬 안정적으로
        # 한 줄씩 인식한다 (실측 비교 결과 기본 모드는 한 거래가 여러 줄로
        # 쪼개지는 경우가 많았다).
        ocr_data = pytesseract.image_to_data(
            image, lang="kor+eng", config="--psm 6", output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError(
            "Tesseract OCR 실행 파일을 찾을 수 없습니다. "
            "Windows에서는 Tesseract OCR을 별도로 설치한 뒤 다시 시도해주세요."
        ) from e

    candidates = []
    for line_text, avg_conf in _group_words_into_lines(ocr_data):
        candidate = _parse_line(line_text, avg_conf)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


class LocalOCREngine(OCREngine):
    """Tesseract를 사용하는 로컬 OCR 구현체."""

    def extract_candidates(self, file_path: str, file_type: str) -> list[dict]:
        file_type = file_type.lower()
        if file_type in ("png", "jpg", "jpeg"):
            from PIL import Image

            with Image.open(file_path) as image:
                return _extract_from_image(image)
        if file_type == "pdf":
            return self._extract_from_pdf(file_path)
        raise ValueError(f"지원하지 않는 파일 형식입니다: {file_type}")

    def _extract_from_pdf(self, file_path: str) -> list[dict]:
        import pymupdf as fitz  # PyMuPDF
        from PIL import Image

        from services.ocr import bank_table_pdf

        candidates: list[dict] = []
        doc = fitz.open(file_path)
        try:
            for page in doc:
                # 텍스트 기반 PDF면 먼저 텍스트를 그대로 시도한다 (OCR보다 정확함).
                text = page.get_text().strip()
                if text:
                    # 인터넷뱅킹에서 내려받는 "계좌별거래내역" 표 형식(입금액/출금액/잔액
                    # 컬럼이 있는 표)은 한 줄에 "입금"/"출금" 글자가 없어 아래의 문장형
                    # 줄 단위 파서로는 인식할 수 없으므로, 표 형식이면 전용 파서를 먼저 쓴다.
                    if bank_table_pdf.looks_like_transaction_table(text):
                        candidates.extend(bank_table_pdf.extract_candidates(page))
                        continue

                    for line in text.splitlines():
                        candidate = _parse_line(line, confidence=100.0)
                        if candidate is not None:
                            candidates.append(candidate)
                    continue

                # 텍스트가 없는 스캔 PDF는 이미지로 변환해 OCR한다.
                pixmap = page.get_pixmap(dpi=200)
                image = Image.open(BytesIO(pixmap.tobytes("png")))
                candidates.extend(_extract_from_image(image))
        finally:
            doc.close()
        return candidates

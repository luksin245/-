"""금액 입력/표시용 유틸리티.

화면에서는 "500,000" 처럼 천 단위 구분을 허용하되,
DB에는 항상 정수(INTEGER, 원 단위)로 저장한다.
"""


def parse_amount(text: str | None) -> int:
    if text is None:
        raise ValueError("금액을 입력해주세요.")
    cleaned = text.replace(",", "").replace(" ", "").strip()
    if cleaned == "":
        raise ValueError("금액을 입력해주세요.")
    if not cleaned.lstrip("-").isdigit():
        raise ValueError("금액은 숫자만 입력할 수 있습니다. (예: 500000 또는 500,000)")
    return int(cleaned)


def format_amount(value: int | None) -> str:
    if value is None:
        return ""
    return f"{value:,}"

"""거래 입력 검증 로직.

UI는 이 검증을 직접 구현하지 않고 services 계층을 통해서만 사용한다.
"""


class ValidationError(Exception):
    pass


def validate_transaction_input(data: dict) -> None:
    if not data.get("transaction_date"):
        raise ValidationError("거래일자는 필수입니다.")

    if data.get("transaction_type") not in ("income", "expense"):
        raise ValidationError("수입/지출 구분은 필수입니다.")

    description = data.get("description")
    if not description or not str(description).strip():
        raise ValidationError("거래내용은 필수입니다.")

    amount = data.get("amount")
    if amount is None:
        raise ValidationError("금액은 필수입니다.")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValidationError("금액은 정수(원 단위)여야 합니다.")
    if amount <= 0:
        raise ValidationError("금액은 0원보다 커야 합니다.")

    balance = data.get("balance")
    if balance is not None and (not isinstance(balance, int) or isinstance(balance, bool)):
        raise ValidationError("잔액은 정수(원 단위)여야 합니다.")

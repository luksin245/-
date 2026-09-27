"""거래(transaction) 관련 비즈니스 로직.

UI는 이 모듈의 함수만 호출한다. DB 접근은 db.transaction_repository를 통해서만 한다.
나중에 OCR / CSV import가 추가되어도 create_transaction()을 그대로 재사용한다
(source_type 인자로 출처만 구분).
"""
from datetime import datetime

from db import category_repository
from db import transaction_repository as repo
from utils.validators import ValidationError, validate_transaction_input

VAT_STATUS_OPTIONS = ["과세", "면세", "불명", "해당없음"]
EVIDENCE_STATUS_OPTIONS = ["있음", "없음", "확인필요"]

DEFAULT_VAT_STATUS = "불명"
DEFAULT_EVIDENCE_STATUS = "확인필요"


def _validate_category_matches_type(category_id: int | None, transaction_type: str) -> None:
    """income 거래에는 income 카테고리만, expense 거래에는 expense 카테고리만 허용한다.

    UI에서도 선택지를 걸러주지만, 잘못된 조합이 DB에 저장되지 않도록
    service 계층에서 다시 한 번 검증한다.
    """
    if category_id is None:
        return
    category = category_repository.get_category_by_id(category_id)
    if category is None:
        raise ValidationError("존재하지 않는 카테고리입니다.")
    if category["type"] != transaction_type:
        raise ValidationError("수입/지출 구분과 카테고리 종류가 일치하지 않습니다.")


def create_transaction(
    transaction_date: str,
    transaction_type: str,
    description: str,
    amount: int,
    transaction_time: str | None = None,
    balance: int | None = None,
    category_id: int | None = None,
    client_id: int | None = None,
    work_type_id: int | None = None,
    vat_status: str = DEFAULT_VAT_STATUS,
    evidence_status: str = DEFAULT_EVIDENCE_STATUS,
    memo: str | None = None,
    source_type: str = "manual",
) -> int:
    data = {
        "transaction_date": transaction_date,
        "transaction_time": transaction_time or None,
        "description": description.strip() if description else description,
        "transaction_type": transaction_type,
        "amount": amount,
        "balance": balance,
        "category_id": category_id,
        "client_id": client_id,
        "work_type_id": work_type_id,
        "vat_status": vat_status,
        "evidence_status": evidence_status,
        "memo": memo,
        "source_type": source_type,
    }

    validate_transaction_input(data)
    _validate_category_matches_type(category_id, transaction_type)

    now = datetime.now().isoformat(timespec="seconds")
    data["created_at"] = now
    data["updated_at"] = now

    return repo.insert_transaction(data)


def update_transaction(
    transaction_id: int,
    transaction_date: str,
    transaction_type: str,
    description: str,
    amount: int,
    transaction_time: str | None = None,
    balance: int | None = None,
    category_id: int | None = None,
    client_id: int | None = None,
    work_type_id: int | None = None,
    vat_status: str = DEFAULT_VAT_STATUS,
    evidence_status: str = DEFAULT_EVIDENCE_STATUS,
    memo: str | None = None,
) -> None:
    """기존 거래 수정. create_transaction과 동일한 검증을 반드시 통과해야 한다.

    거래 유형(수입/지출)이 바뀌면서 기존 카테고리가 새 유형과 맞지 않는 경우,
    호출하는 쪽(UI)에서 category_id를 None으로 비워서 넘겨야 한다.
    이 함수는 그 조합이 실수로 넘어와도 다시 한 번 걸러낸다.
    """
    data = {
        "transaction_date": transaction_date,
        "transaction_time": transaction_time or None,
        "description": description.strip() if description else description,
        "transaction_type": transaction_type,
        "amount": amount,
        "balance": balance,
        "category_id": category_id,
        "client_id": client_id,
        "work_type_id": work_type_id,
        "vat_status": vat_status,
        "evidence_status": evidence_status,
        "memo": memo,
    }

    validate_transaction_input(data)
    _validate_category_matches_type(category_id, transaction_type)

    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    repo.update_transaction(transaction_id, data)


def list_transactions(filters: dict | None = None, limit: int | None = None) -> list[dict]:
    """카테고리/거래처/업무유형 이름까지 포함해 조회한다. filters는 DB 쿼리 조건으로 처리된다."""
    return repo.get_transactions(filters, limit=limit)


def get_summary(filters: dict | None = None) -> dict:
    """현재 필터 조건 기준 조회건수/총수입/총지출/순금액을 계산한다."""
    summary = repo.get_transaction_summary(filters)
    summary["net_amount"] = summary["total_income"] - summary["total_expense"]
    return summary


def get_transaction(transaction_id: int) -> dict | None:
    return repo.get_transaction_by_id(transaction_id)


def count_transactions() -> int:
    return repo.count_transactions()


def delete_transaction(transaction_id: int) -> None:
    """거래 삭제. UI에서 SQL을 직접 실행하지 않고 반드시 이 함수를 통해서만 삭제한다.

    현재는 실제 DELETE를 수행하지만, 추후 복구 기능이 필요해지면
    이 함수 내부만 soft-delete 방식으로 교체하면 되고 호출부는 변경할 필요가 없다.
    """
    repo.delete_transaction(transaction_id)

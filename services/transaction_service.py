"""거래(transaction) 관련 비즈니스 로직.

UI는 이 모듈의 함수만 호출한다. DB 접근은 db.transaction_repository를 통해서만 한다.
나중에 OCR / CSV import가 추가되어도 create_transaction()을 그대로 재사용한다
(source_type 인자로 출처만 구분).
"""
from datetime import datetime

from db import transaction_repository as repo
from utils.validators import validate_transaction_input

VAT_STATUS_OPTIONS = ["과세", "면세", "불명", "해당없음"]
EVIDENCE_STATUS_OPTIONS = ["있음", "없음", "확인필요"]

DEFAULT_VAT_STATUS = "불명"
DEFAULT_EVIDENCE_STATUS = "확인필요"


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

    now = datetime.now().isoformat(timespec="seconds")
    data["created_at"] = now
    data["updated_at"] = now

    return repo.insert_transaction(data)


def list_transactions() -> list[dict]:
    return repo.get_all_transactions()


def count_transactions() -> int:
    return repo.count_transactions()


def delete_transaction(transaction_id: int) -> None:
    """거래 삭제. UI에서 SQL을 직접 실행하지 않고 반드시 이 함수를 통해서만 삭제한다.

    현재는 실제 DELETE를 수행하지만, 추후 복구 기능이 필요해지면
    이 함수 내부만 soft-delete 방식으로 교체하면 되고 호출부는 변경할 필요가 없다.
    """
    repo.delete_transaction(transaction_id)

"""거래(transaction) 관련 비즈니스 로직.

UI는 이 모듈의 함수만 호출한다. DB 접근은 db.transaction_repository를 통해서만 한다.
나중에 OCR / CSV import가 추가되어도 create_transaction()을 그대로 재사용한다
(source_type 인자로 출처만 구분).
"""
from datetime import datetime

from db import account_repository, category_repository, client_repository, work_type_repository
from db import transaction_repository as repo
from utils.validators import ValidationError, validate_transaction_input

VAT_STATUS_OPTIONS = ["과세", "면세", "불명", "해당없음"]
EVIDENCE_STATUS_OPTIONS = ["있음", "없음", "확인필요"]

# 회계구분: transaction_type(입금/출금, 통장의 방향)과는 다른 개념이다.
# 예) 대표자가 법인에 자금을 입금 -> transaction_type='income'이지만
#     accounting_type='비매출입금'일 수 있다 (매출이 아님).
ACCOUNTING_TYPE_OPTIONS = ["매출", "비용", "자금이동", "비매출입금", "비비용출금", "미분류"]

DEFAULT_VAT_STATUS = "불명"
DEFAULT_EVIDENCE_STATUS = "확인필요"
DEFAULT_ACCOUNTING_TYPE = "미분류"


def _validate_category_matches_type(
    category_id: int | None, transaction_type: str, unchanged: bool
) -> None:
    """income 거래에는 income 카테고리만, expense 거래에는 expense 카테고리만 허용한다.

    비활성화된 카테고리는 새로 지정할 수 없다. 다만 기존 거래에 이미 설정되어
    있던 값을 그대로 두는 경우(unchanged=True)는 예외로 허용한다 - 그래야
    과거에 쓰던 카테고리를 나중에 비활성화해도 기존 거래가 깨지지 않는다.
    """
    if category_id is None:
        return
    category = category_repository.get_category_by_id(category_id)
    if category is None:
        raise ValidationError("존재하지 않는 카테고리입니다.")
    if category["type"] != transaction_type:
        raise ValidationError("수입/지출 구분과 카테고리 종류가 일치하지 않습니다.")
    if not unchanged and not category["is_active"]:
        raise ValidationError("비활성화된 카테고리입니다. 다른 카테고리를 선택해주세요.")


def _validate_client_reference(client_id: int | None, unchanged: bool) -> None:
    if client_id is None:
        return
    client = client_repository.get_client_by_id(client_id)
    if client is None:
        raise ValidationError("존재하지 않는 거래처입니다.")
    if not unchanged and not client["is_active"]:
        raise ValidationError("비활성화된 거래처입니다. 다른 거래처를 선택해주세요.")


def _validate_work_type_reference(work_type_id: int | None, unchanged: bool) -> None:
    if work_type_id is None:
        return
    work_type = work_type_repository.get_work_type_by_id(work_type_id)
    if work_type is None:
        raise ValidationError("존재하지 않는 업무유형입니다.")
    if not unchanged and not work_type["is_active"]:
        raise ValidationError("비활성화된 업무유형입니다. 다른 업무유형을 선택해주세요.")


def _validate_account_reference(account_id: int | None, unchanged: bool) -> None:
    if account_id is None:
        return
    account = account_repository.get_account_by_id(account_id)
    if account is None:
        raise ValidationError("존재하지 않는 계정과목입니다.")
    if not unchanged and not account["is_active"]:
        raise ValidationError("비활성화된 계정과목입니다. 다른 계정과목을 선택해주세요.")


def _validate_accounting_type(accounting_type: str) -> None:
    if accounting_type not in ACCOUNTING_TYPE_OPTIONS:
        raise ValidationError("회계구분 값이 올바르지 않습니다.")


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
    account_id: int | None = None,
    accounting_type: str = DEFAULT_ACCOUNTING_TYPE,
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
        "account_id": account_id,
        "accounting_type": accounting_type,
        "vat_status": vat_status,
        "evidence_status": evidence_status,
        "memo": memo,
        "source_type": source_type,
    }

    validate_transaction_input(data)
    _validate_accounting_type(accounting_type)
    # 신규 등록에서는 비활성화된 기준정보를 새로 지정하는 것을 항상 막는다 (unchanged=False).
    _validate_category_matches_type(category_id, transaction_type, unchanged=False)
    _validate_client_reference(client_id, unchanged=False)
    _validate_work_type_reference(work_type_id, unchanged=False)
    _validate_account_reference(account_id, unchanged=False)

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
    account_id: int | None = None,
    accounting_type: str = DEFAULT_ACCOUNTING_TYPE,
    vat_status: str = DEFAULT_VAT_STATUS,
    evidence_status: str = DEFAULT_EVIDENCE_STATUS,
    memo: str | None = None,
) -> None:
    """기존 거래 수정. create_transaction과 동일한 검증을 반드시 통과해야 한다.

    거래 유형(수입/지출)이 바뀌면서 기존 카테고리가 새 유형과 맞지 않는 경우,
    호출하는 쪽(UI)에서 category_id를 None으로 비워서 넘겨야 한다.
    이 함수는 그 조합이 실수로 넘어와도 다시 한 번 걸러낸다.

    category_id/client_id/work_type_id/account_id가 원래 거래에 이미 설정돼
    있던 값과 동일하면(수정하지 않고 그대로 둔 경우) 비활성 상태여도 허용한다.
    값을 실제로 "새로" 바꾸는 경우에만 활성 상태를 요구한다.
    """
    original = repo.get_transaction_by_id(transaction_id)
    if original is None:
        raise ValidationError("존재하지 않는 거래입니다.")

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
        "account_id": account_id,
        "accounting_type": accounting_type,
        "vat_status": vat_status,
        "evidence_status": evidence_status,
        "memo": memo,
    }

    validate_transaction_input(data)
    _validate_accounting_type(accounting_type)
    _validate_category_matches_type(
        category_id, transaction_type, unchanged=(category_id == original["category_id"])
    )
    _validate_client_reference(client_id, unchanged=(client_id == original["client_id"]))
    _validate_work_type_reference(
        work_type_id, unchanged=(work_type_id == original["work_type_id"])
    )
    _validate_account_reference(account_id, unchanged=(account_id == original["account_id"]))

    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    repo.update_transaction(transaction_id, data)


def list_transactions(filters: dict | None = None, limit: int | None = None) -> list[dict]:
    """카테고리/거래처/업무유형/계정과목 이름까지 포함해 조회한다. filters는 DB 쿼리 조건으로 처리된다."""
    return repo.get_transactions(filters, limit=limit)


def get_summary(filters: dict | None = None) -> dict:
    """현재 필터 조건 기준 조회건수/총수입/총지출/순금액을 계산한다."""
    summary = repo.get_transaction_summary(filters)
    summary["net_amount"] = summary["total_income"] - summary["total_expense"]
    return summary


def get_accounting_summary(filters: dict | None = None) -> dict:
    """회계구분(매출/비용) 기준 합계. 통장 기준 총수입/총지출과는 다른 개념이다."""
    return repo.get_accounting_type_summary(filters)


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


def find_potential_duplicates(
    transaction_date: str,
    amount: int,
    balance: int | None,
    transaction_time: str | None = None,
    description: str | None = None,
    transaction_type: str | None = None,
) -> list[dict]:
    return repo.find_potential_duplicates(
        transaction_date, amount, balance, transaction_time, description, transaction_type
    )

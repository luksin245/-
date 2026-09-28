"""법인카드 명세서 / 사용내역 비즈니스 로직.

- 카드 사용내역은 통장 거래와 분리해서 저장한다 (통장에는 카드값이 '카드결' 출금 한 건으로만
  찍히므로, 같은 돈이 두 번 지출로 잡히지 않게 하기 위함).
- 명세서의 총합계(청구금액)와 사용내역 합계가 1원이라도 다르면 저장하지 않는다. OCR이나
  입력 실수로 금액이 틀린 채 저장되는 것을 막는 핵심 안전장치다.
- 통장의 카드결 출금과의 연결(맞춰보기)과 그 출금의 회계구분 변경은 사용자가 버튼을
  눌렀을 때만 수행한다 (자동 확정 없음).
"""
from datetime import date, datetime, timedelta

from db import account_repository, card_repository, category_repository
from db import transaction_repository as tx_repo
from services import category_rule_service
from services.transaction_service import ACCOUNTING_TYPE_OPTIONS
from utils.validators import ValidationError

DEFAULT_CARD_NAME = "신한카드 법인"
DEFAULT_LINE_ACCOUNTING_TYPE = "미분류"
# 이용기간이 끝난 뒤 이 기간 안에 빠져나간 같은 금액의 출금을 카드값 결제 후보로 본다.
SETTLEMENT_SEARCH_DAYS = 60
SETTLEMENT_ACCOUNTING_TYPE = "비비용출금"
SETTLEMENT_ACCOUNT_NAME = "미지급금"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_iso_date(value, field_label: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValidationError(f"{field_label} 형식이 올바르지 않습니다 (예: 2026-08-07).")


def _validate_category(category_id: int | None, unchanged: bool) -> None:
    if category_id is None:
        return
    category = category_repository.get_category_by_id(category_id)
    if category is None:
        raise ValidationError("존재하지 않는 카테고리입니다.")
    if category["type"] != "expense":
        raise ValidationError("카드 사용내역에는 지출 카테고리만 지정할 수 있습니다.")
    if not unchanged and not category["is_active"]:
        raise ValidationError(f"비활성화된 카테고리입니다: {category['name']}")


def _validate_account(account_id: int | None, unchanged: bool) -> None:
    if account_id is None:
        return
    account = account_repository.get_account_by_id(account_id)
    if account is None:
        raise ValidationError("존재하지 않는 계정과목입니다.")
    if not unchanged and not account["is_active"]:
        raise ValidationError(f"비활성화된 계정과목입니다: {account['name']}")


def _validate_accounting_type(accounting_type: str) -> None:
    if accounting_type not in ACCOUNTING_TYPE_OPTIONS:
        raise ValidationError("회계구분 값이 올바르지 않습니다.")


def normalize_lines(lines: list[dict]) -> list[dict]:
    """입력된 사용내역을 검증/정리한다. 문제가 있으면 몇 번째 줄인지 알려주는 오류를 낸다."""
    normalized = []
    for idx, line in enumerate(lines, start=1):
        prefix = f"{idx}번째 줄: "
        try:
            merchant = (line.get("merchant") or "").strip()
            if not merchant:
                raise ValidationError("가맹점명은 필수입니다.")
            amount = line.get("amount")
            if amount is None or isinstance(amount, bool) or int(amount) != amount:
                raise ValidationError("청구금액은 원 단위 정수여야 합니다.")
            amount = int(amount)
            if amount == 0:
                raise ValidationError("청구금액은 0원일 수 없습니다 (취소·환불은 음수로 입력).")
            accounting_type = line.get("accounting_type") or DEFAULT_LINE_ACCOUNTING_TYPE
            _validate_accounting_type(accounting_type)
            _validate_category(line.get("category_id"), unchanged=False)
            _validate_account(line.get("account_id"), unchanged=False)
            normalized.append(
                {
                    "use_date": _parse_iso_date(line.get("use_date"), "이용일자"),
                    "merchant": merchant,
                    "amount": amount,
                    "category_id": line.get("category_id"),
                    "account_id": line.get("account_id"),
                    "accounting_type": accounting_type,
                    "memo": (line.get("memo") or "").strip() or None,
                }
            )
        except ValidationError as e:
            raise ValidationError(prefix + str(e))
    return normalized


def create_statement(
    card_name: str,
    period_start,
    period_end,
    billed_total: int,
    lines: list[dict],
    memo: str | None = None,
) -> int:
    card_name = (card_name or "").strip()
    if not card_name:
        raise ValidationError("카드 이름은 필수입니다.")
    start = _parse_iso_date(period_start, "이용기간 시작일")
    end = _parse_iso_date(period_end, "이용기간 종료일")
    if start > end:
        raise ValidationError("이용기간 종료일이 시작일보다 빠릅니다.")
    if billed_total is None or isinstance(billed_total, bool) or int(billed_total) != billed_total:
        raise ValidationError("명세서 총합계는 원 단위 정수여야 합니다.")
    if not lines:
        raise ValidationError("카드 사용내역을 한 줄 이상 입력해주세요.")

    normalized = normalize_lines(lines)
    line_total = sum(line["amount"] for line in normalized)
    if line_total != billed_total:
        diff = billed_total - line_total
        raise ValidationError(
            f"사용내역 합계({line_total:,}원)가 명세서 총합계({billed_total:,}원)와 {abs(diff):,}원 다릅니다. "
            "금액을 다시 확인하거나, 빠진 항목(연회비·수수료·취소 건 등)이 없는지 확인해주세요."
        )

    if card_repository.find_statement(card_name, start, end):
        raise ValidationError(f"'{card_name}' {start} ~ {end} 명세서는 이미 등록되어 있습니다.")

    now = _now()
    statement = {
        "card_name": card_name,
        "period_start": start,
        "period_end": end,
        "billed_total": int(billed_total),
        "memo": (memo or "").strip() or None,
        "created_at": now,
    }
    return card_repository.insert_statement_with_lines(
        statement, [{**line, "created_at": now, "updated_at": now} for line in normalized]
    )


def list_statements() -> list[dict]:
    return card_repository.get_statements()


def get_statement(statement_id: int) -> dict | None:
    return card_repository.get_statement_by_id(statement_id)


def get_lines(statement_id: int | None = None, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    return card_repository.get_lines(statement_id, start_date, end_date)


def update_classifications(statement_id: int, updates: list[dict]) -> None:
    """명세서에 속한 사용내역들의 분류를 한꺼번에 저장한다.

    원래 저장돼 있던 카테고리/계정과목을 그대로 두는 경우에는 그 항목이 나중에
    비활성화됐더라도 허용한다 (다른 화면들과 같은 원칙).
    """
    now = _now()
    prepared = []
    for update in updates:
        original = card_repository.get_line_by_id(update["id"])
        if original is None or original["statement_id"] != statement_id:
            raise ValidationError("이 명세서에 속하지 않은 사용내역입니다. 화면을 새로고침해주세요.")
        accounting_type = update.get("accounting_type") or DEFAULT_LINE_ACCOUNTING_TYPE
        _validate_accounting_type(accounting_type)
        _validate_category(update.get("category_id"), unchanged=update.get("category_id") == original["category_id"])
        _validate_account(update.get("account_id"), unchanged=update.get("account_id") == original["account_id"])
        prepared.append(
            {
                "id": update["id"],
                "category_id": update.get("category_id"),
                "account_id": update.get("account_id"),
                "accounting_type": accounting_type,
                "memo": (update.get("memo") or "").strip() or None,
                "updated_at": now,
            }
        )
    card_repository.update_line_classifications(prepared)


def suggest_for_merchant(merchant: str) -> dict:
    """자동분류 규칙으로 가맹점명에 대한 추천값을 돌려준다 (없으면 빈 dict).

    카드 사용내역에 맞지 않는 추천(수입 카테고리, 비활성 항목)은 걸러낸다.
    """
    suggestion = category_rule_service.suggest_for(merchant, None)
    if not suggestion:
        return {}
    result = {}
    if suggestion.get("category_id"):
        category = category_repository.get_category_by_id(suggestion["category_id"])
        if category and category["type"] == "expense" and category["is_active"]:
            result["category_id"] = category["id"]
    if suggestion.get("account_id"):
        account = account_repository.get_account_by_id(suggestion["account_id"])
        if account and account["is_active"]:
            result["account_id"] = account["id"]
    if suggestion.get("accounting_type"):
        result["accounting_type"] = suggestion["accounting_type"]
    return result


def find_settlement_candidates(statement_id: int) -> list[dict]:
    """명세서 총합계와 금액이 정확히 같은 통장 출금을 찾는다 (이용기간 종료 후 60일 이내).

    다른 명세서에 이미 연결된 출금에는 linked_elsewhere=True를 붙여 구분한다.
    """
    statement = card_repository.get_statement_by_id(statement_id)
    if statement is None or statement["billed_total"] <= 0:
        return []
    period_end = date.fromisoformat(statement["period_end"])
    date_from = (period_end + timedelta(days=1)).isoformat()
    date_to = (period_end + timedelta(days=SETTLEMENT_SEARCH_DAYS)).isoformat()
    linked = card_repository.get_linked_transaction_ids()
    candidates = tx_repo.find_expenses_by_amount(statement["billed_total"], date_from, date_to)
    for tx in candidates:
        tx["linked_elsewhere"] = tx["id"] in linked and tx["id"] != statement["settlement_transaction_id"]
    return candidates


def link_settlement(statement_id: int, transaction_id: int, reclassify: bool = True) -> None:
    """명세서를 통장의 카드값 결제 출금과 연결한다.

    reclassify=True면 그 출금을 회계구분 '비비용출금' / 계정과목 '미지급금'으로 바꾼다 -
    실제 비용은 카드 사용내역 쪽에서 잡히므로, 결제 출금까지 비용으로 두면 두 번 계산된다.
    """
    statement = card_repository.get_statement_by_id(statement_id)
    if statement is None:
        raise ValidationError("존재하지 않는 명세서입니다.")
    tx = tx_repo.get_transaction_by_id(transaction_id)
    if tx is None:
        raise ValidationError("존재하지 않는 통장 거래입니다.")
    if tx["transaction_type"] != "expense":
        raise ValidationError("카드값 결제는 통장 출금 거래와만 연결할 수 있습니다.")
    if tx["amount"] != statement["billed_total"]:
        raise ValidationError(
            f"금액이 다릅니다 (통장 출금 {tx['amount']:,}원 / 명세서 {statement['billed_total']:,}원)."
        )
    linked = card_repository.get_linked_transaction_ids()
    if transaction_id in linked and transaction_id != statement["settlement_transaction_id"]:
        raise ValidationError("이 출금은 이미 다른 카드 명세서와 연결되어 있습니다.")

    card_repository.set_settlement(statement_id, transaction_id)

    if reclassify:
        account = account_repository.find_account_by_name_ci(SETTLEMENT_ACCOUNT_NAME)
        account_id = account["id"] if account and account["is_active"] else tx["account_id"]
        tx_repo.set_accounting_classification(transaction_id, SETTLEMENT_ACCOUNTING_TYPE, account_id, _now())


def unlink_settlement(statement_id: int) -> None:
    """연결만 해제한다. 통장 출금의 회계구분은 되돌리지 않는다 (필요하면 거래내역에서 직접 수정)."""
    if card_repository.get_statement_by_id(statement_id) is None:
        raise ValidationError("존재하지 않는 명세서입니다.")
    card_repository.set_settlement(statement_id, None)


def delete_statement(statement_id: int) -> None:
    """명세서와 그 사용내역을 삭제한다. 연결돼 있던 통장 출금 자체는 지우지 않는다."""
    if card_repository.get_statement_by_id(statement_id) is None:
        raise ValidationError("존재하지 않는 명세서입니다.")
    card_repository.delete_statement(statement_id)


def get_card_cost_total(start_date: str, end_date: str) -> int:
    return card_repository.get_cost_total(start_date, end_date)

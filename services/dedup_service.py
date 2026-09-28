"""OCR로 추출한 거래 후보와 기존 거래내역 간의 중복 감지.

여기서는 절대 자동으로 삭제/제외하지 않는다. 의심되는 경우
'중복의심' 상태만 표시하고, 최종 판단은 항상 사용자가 검토 화면에서 내린다.

- 강한 중복(strong): 날짜+시간+거래내용+구분(입금/출금)+금액+잔액이 모두 일치
- 부분 중복(partial): 날짜+금액+잔액만 일치 (시간/거래내용 등은 다르거나 OCR로 못 읽음)
"""
from services import transaction_service

MATCH_STRONG = "strong"
MATCH_PARTIAL = "partial"
MATCH_NONE = None


def _candidate_amount_and_type(candidate: dict) -> tuple[int | None, str | None]:
    if candidate.get("income") is not None:
        return candidate["income"], "income"
    if candidate.get("expense") is not None:
        return candidate["expense"], "expense"
    return None, None


def _balance_matches(candidate: dict, existing: dict) -> bool:
    candidate_balance = candidate.get("balance")
    existing_balance = existing.get("balance")
    if candidate_balance is None or existing_balance is None:
        return False
    return candidate_balance == existing_balance


def _is_strong_match(candidate: dict, existing: dict, transaction_type: str) -> bool:
    if existing["transaction_type"] != transaction_type:
        return False
    if not _balance_matches(candidate, existing):
        return False
    if (candidate.get("time") or None) != (existing.get("transaction_time") or None):
        return False
    candidate_desc = (candidate.get("description") or "").strip()
    existing_desc = (existing.get("description") or "").strip()
    if not candidate_desc or not existing_desc or candidate_desc != existing_desc:
        return False
    return True


def check_duplicate(candidate: dict) -> str | None:
    """후보 거래가 기존 거래와 중복으로 의심되는지 판단한다.

    반환값: MATCH_STRONG / MATCH_PARTIAL / None(중복 후보 없음).
    날짜나 금액이 없어 비교 자체가 불가능하면 None을 반환한다(이 경우
    OCR 결과 자체가 이미 '확인필요' 상태여야 한다).
    """
    date_str = candidate.get("date")
    amount, transaction_type = _candidate_amount_and_type(candidate)
    if date_str is None or amount is None:
        return MATCH_NONE

    existing_rows = transaction_service.find_potential_duplicates(
        transaction_date=date_str,
        amount=amount,
        balance=candidate.get("balance"),
        transaction_time=candidate.get("time"),
        description=candidate.get("description"),
        transaction_type=transaction_type,
    )
    if not existing_rows:
        return MATCH_NONE

    has_partial = False
    for existing in existing_rows:
        if _is_strong_match(candidate, existing, transaction_type):
            return MATCH_STRONG
        if _balance_matches(candidate, existing):
            has_partial = True
    return MATCH_PARTIAL if has_partial else MATCH_NONE

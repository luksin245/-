"""자동분류 규칙 비즈니스 로직.

키워드 매칭으로 카테고리/거래처/업무유형/계정과목/회계구분을 "추천"만 한다.
절대로 자동으로 거래를 확정하거나 사용자가 고른 값을 덮어쓰지 않는다 -
UI에서 추천값은 어디까지나 미리 채워주는 기본값일 뿐이며, 사용자가 다른 값을
선택하면 그 선택이 그대로 유지된다.
"""
import sqlite3
from datetime import datetime

from db import category_rule_repository as repo
from services.transaction_service import ACCOUNTING_TYPE_OPTIONS
from utils.validators import ValidationError

MATCH_FIELD_OPTIONS = ["description", "client_name"]
MATCH_FIELD_LABELS = {"description": "거래내용", "client_name": "거래처명"}


def list_rules(status: str = "active") -> list[dict]:
    return repo.get_rules(status=status)


def get_rule(rule_id: int) -> dict | None:
    return repo.get_rule_by_id(rule_id)


def _validate_rule_input(keyword: str, match_field: str, suggested_accounting_type: str | None) -> None:
    if not keyword or not keyword.strip():
        raise ValidationError("키워드는 필수입니다.")
    if match_field not in MATCH_FIELD_OPTIONS:
        raise ValidationError("매칭 대상 값이 올바르지 않습니다.")
    if suggested_accounting_type is not None and suggested_accounting_type not in ACCOUNTING_TYPE_OPTIONS:
        raise ValidationError("추천 회계구분 값이 올바르지 않습니다.")


def create_rule(
    keyword: str,
    match_field: str = "description",
    suggested_category_id: int | None = None,
    suggested_client_id: int | None = None,
    suggested_work_type_id: int | None = None,
    suggested_account_id: int | None = None,
    suggested_accounting_type: str | None = None,
) -> int:
    keyword = (keyword or "").strip()
    _validate_rule_input(keyword, match_field, suggested_accounting_type)

    existing = repo.find_rule_by_keyword_ci(keyword, match_field)
    if existing:
        if existing["is_active"]:
            raise ValidationError("이미 등록된 규칙입니다 (동일한 키워드+매칭 대상).")
        raise ValidationError("이미 등록되어 있으나 비활성 상태인 규칙입니다. 목록에서 재활성화해주세요.")

    data = {
        "keyword": keyword,
        "match_field": match_field,
        "suggested_category_id": suggested_category_id,
        "suggested_client_id": suggested_client_id,
        "suggested_work_type_id": suggested_work_type_id,
        "suggested_account_id": suggested_account_id,
        "suggested_accounting_type": suggested_accounting_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        return repo.insert_rule(data)
    except sqlite3.IntegrityError:
        raise ValidationError("규칙을 저장하지 못했습니다.")


def update_rule_info(
    rule_id: int,
    keyword: str,
    match_field: str,
    suggested_category_id: int | None = None,
    suggested_client_id: int | None = None,
    suggested_work_type_id: int | None = None,
    suggested_account_id: int | None = None,
    suggested_accounting_type: str | None = None,
) -> None:
    keyword = (keyword or "").strip()
    _validate_rule_input(keyword, match_field, suggested_accounting_type)

    existing = repo.find_rule_by_keyword_ci(keyword, match_field)
    if existing and existing["id"] != rule_id:
        raise ValidationError("이미 등록된 규칙입니다 (동일한 키워드+매칭 대상).")

    data = {
        "keyword": keyword,
        "match_field": match_field,
        "suggested_category_id": suggested_category_id,
        "suggested_client_id": suggested_client_id,
        "suggested_work_type_id": suggested_work_type_id,
        "suggested_account_id": suggested_account_id,
        "suggested_accounting_type": suggested_accounting_type,
    }
    repo.update_rule(rule_id, data)


def deactivate_rule(rule_id: int) -> None:
    repo.set_rule_active(rule_id, False)


def activate_rule(rule_id: int) -> None:
    repo.set_rule_active(rule_id, True)


def suggest_for(description: str | None, client_name: str | None) -> dict | None:
    """거래내용/거래처명에 대해 매칭되는 활성 규칙 중 하나를 찾아 추천값을 반환한다.

    여러 규칙이 매칭되면 키워드가 더 긴(더 구체적인) 규칙을 우선한다.
    매칭되는 규칙이 없으면 None을 반환한다 - 이 경우 호출부는 추천값 없이
    그대로 두어야 하며 절대로 값을 지어내면 안 된다.
    """
    description = description or ""
    client_name = client_name or ""

    candidates = []
    for rule in repo.get_active_rules_for_matching():
        haystack = description if rule["match_field"] == "description" else client_name
        if rule["keyword"] and rule["keyword"].lower() in haystack.lower():
            candidates.append(rule)

    if not candidates:
        return None

    best = max(candidates, key=lambda r: len(r["keyword"]))
    return {
        "rule_id": best["id"],
        "category_id": best["suggested_category_id"],
        "category_name": best["suggested_category_name"],
        "client_id": best["suggested_client_id"],
        "client_name": best["suggested_client_name"],
        "work_type_id": best["suggested_work_type_id"],
        "work_type_name": best["suggested_work_type_name"],
        "account_id": best["suggested_account_id"],
        "account_name": best["suggested_account_name"],
        "accounting_type": best["suggested_accounting_type"],
    }


def record_suggestion_used(rule_id: int) -> None:
    """사용자가 추천값을 그대로 채택해 저장했을 때 사용 횟수를 늘린다 (통계용)."""
    repo.increment_hit_count(rule_id)

import sqlite3

from db import category_repository as repo
from utils.validators import ValidationError

TYPE_LABELS = {"income": "수입", "expense": "지출"}


def get_income_categories() -> list[dict]:
    return repo.get_categories(type_="income")


def get_expense_categories() -> list[dict]:
    return repo.get_categories(type_="expense")


def get_categories_by_type(transaction_type: str) -> list[dict]:
    return repo.get_categories(type_=transaction_type)


def get_category(category_id: int) -> dict | None:
    return repo.get_category_by_id(category_id)


def list_categories_admin(status: str = "active", type_filter: str | None = None) -> list[dict]:
    return repo.get_categories_admin(status=status, type_filter=type_filter)


def create_category(name: str, type_: str, sort_order: int = 0) -> int:
    name = (name or "").strip()
    if not name:
        raise ValidationError("카테고리명은 필수입니다.")
    if type_ not in ("income", "expense"):
        raise ValidationError("수입/지출 구분을 선택해주세요.")

    existing = repo.find_category_by_name_ci(name, type_)
    if existing:
        if existing["is_active"]:
            raise ValidationError("이미 등록된 카테고리입니다.")
        raise ValidationError("이미 등록되어 있으나 비활성 상태인 카테고리입니다. 목록에서 재활성화해주세요.")

    try:
        return repo.insert_category(name, type_, sort_order)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 카테고리입니다.")


def update_category_info(category_id: int, name: str, sort_order: int) -> None:
    """카테고리명과 정렬순서만 수정한다.

    수입/지출 구분(type)은 생성 후 변경할 수 없다 - 기존 거래와의 정합성을
    지키기 위한 정책이며, 이 함수는 애초에 type을 받지 않는다.
    """
    name = (name or "").strip()
    if not name:
        raise ValidationError("카테고리명은 필수입니다.")

    current = repo.get_category_by_id(category_id)
    if current is None:
        raise ValidationError("존재하지 않는 카테고리입니다.")

    existing = repo.find_category_by_name_ci(name, current["type"])
    if existing and existing["id"] != category_id:
        raise ValidationError("이미 등록된 카테고리입니다.")

    try:
        repo.update_category(category_id, name, sort_order)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 카테고리입니다.")


def deactivate_category(category_id: int) -> None:
    """삭제 대신 비활성화. 단, 해당 유형(수입/지출)의 활성 카테고리가
    0개가 되어버리는 경우는 막는다 (실수로 전부 비활성화하는 사고 방지)."""
    category = repo.get_category_by_id(category_id)
    if category is None:
        raise ValidationError("존재하지 않는 카테고리입니다.")

    active_count = repo.count_active_categories(category["type"], exclude_id=category_id)
    if active_count == 0:
        type_label = TYPE_LABELS[category["type"]]
        raise ValidationError(
            f"{type_label} 카테고리가 최소 1개는 활성 상태여야 합니다. "
            "다른 카테고리를 먼저 활성화한 뒤 다시 시도해주세요."
        )

    repo.set_category_active(category_id, False)


def activate_category(category_id: int) -> None:
    repo.set_category_active(category_id, True)

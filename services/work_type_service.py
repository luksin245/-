import sqlite3

from db import work_type_repository as repo
from utils.validators import ValidationError


def get_work_types() -> list[dict]:
    return repo.get_work_types()


def get_work_type(work_type_id: int) -> dict | None:
    return repo.get_work_type_by_id(work_type_id)


def list_work_types_admin(status: str = "active") -> list[dict]:
    return repo.get_work_types_admin(status=status)


def create_work_type(name: str, sort_order: int = 0) -> int:
    name = (name or "").strip()
    if not name:
        raise ValidationError("업무유형명은 필수입니다.")

    existing = repo.find_work_type_by_name_ci(name)
    if existing:
        if existing["is_active"]:
            raise ValidationError("이미 등록된 업무유형입니다.")
        raise ValidationError("이미 등록되어 있으나 비활성 상태인 업무유형입니다. 목록에서 재활성화해주세요.")

    try:
        return repo.insert_work_type(name, sort_order)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 업무유형입니다.")


def update_work_type_info(work_type_id: int, name: str, sort_order: int) -> None:
    """업무유형명/정렬순서 수정. 이름을 바꾸면 이미 이 업무유형을 참조 중인 과거
    거래에도 새 이름이 그대로 반영된다 (work_type_id로 참조하는 구조상 정상 동작)."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("업무유형명은 필수입니다.")

    existing = repo.find_work_type_by_name_ci(name)
    if existing and existing["id"] != work_type_id:
        raise ValidationError("이미 등록된 업무유형입니다.")

    try:
        repo.update_work_type(work_type_id, name, sort_order)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 업무유형입니다.")


def deactivate_work_type(work_type_id: int) -> None:
    repo.set_work_type_active(work_type_id, False)


def activate_work_type(work_type_id: int) -> None:
    repo.set_work_type_active(work_type_id, True)

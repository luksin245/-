import sqlite3

from db import account_repository as repo
from utils.validators import ValidationError


def get_accounts() -> list[dict]:
    return repo.get_accounts()


def get_account(account_id: int) -> dict | None:
    return repo.get_account_by_id(account_id)


def list_accounts_admin(status: str = "active") -> list[dict]:
    return repo.get_accounts_admin(status=status)


def create_account(name: str, sort_order: int = 0) -> int:
    name = (name or "").strip()
    if not name:
        raise ValidationError("계정과목명은 필수입니다.")

    existing = repo.find_account_by_name_ci(name)
    if existing:
        if existing["is_active"]:
            raise ValidationError("이미 등록된 계정과목입니다.")
        raise ValidationError("이미 등록되어 있으나 비활성 상태인 계정과목입니다. 목록에서 재활성화해주세요.")

    try:
        return repo.insert_account(name, sort_order)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 계정과목입니다.")


def update_account_info(account_id: int, name: str, sort_order: int) -> None:
    name = (name or "").strip()
    if not name:
        raise ValidationError("계정과목명은 필수입니다.")

    existing = repo.find_account_by_name_ci(name)
    if existing and existing["id"] != account_id:
        raise ValidationError("이미 등록된 계정과목입니다.")

    try:
        repo.update_account(account_id, name, sort_order)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 계정과목입니다.")


def deactivate_account(account_id: int) -> None:
    """삭제 대신 비활성화. 기존 거래는 그대로 유지되고 신규 거래등록에서만 제외된다."""
    repo.set_account_active(account_id, False)


def activate_account(account_id: int) -> None:
    repo.set_account_active(account_id, True)

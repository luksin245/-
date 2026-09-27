import sqlite3

from db import category_repository, work_type_repository
from db import client_repository as repo
from utils.validators import ValidationError


def get_clients() -> list[dict]:
    return repo.get_clients()


def get_client(client_id: int) -> dict | None:
    return repo.get_client_by_id(client_id)


def list_clients_admin(status: str = "active", keyword: str | None = None) -> list[dict]:
    return repo.get_clients_admin(status=status, keyword=keyword)


def get_or_create_client(name: str) -> int:
    """이름이 이미 존재하면 해당 id를, 없으면 새로 등록 후 id를 반환한다."""
    name = name.strip()
    existing = repo.get_client_by_name(name)
    if existing:
        return existing["id"]
    return repo.insert_client(name)


def _validate_client_name(name: str, exclude_id: int | None = None) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("거래처명은 필수입니다.")
    existing = repo.find_client_by_name_ci(name)
    if existing and existing["id"] != exclude_id:
        if existing["is_active"]:
            raise ValidationError("이미 등록된 거래처입니다.")
        raise ValidationError("이미 등록되어 있으나 비활성 상태인 거래처입니다. 목록에서 재활성화해주세요.")
    return name


def _validate_optional_category(category_id: int | None) -> None:
    if category_id is None:
        return
    if category_repository.get_category_by_id(category_id) is None:
        raise ValidationError("존재하지 않는 카테고리입니다.")


def _validate_optional_work_type(work_type_id: int | None) -> None:
    if work_type_id is None:
        return
    if work_type_repository.get_work_type_by_id(work_type_id) is None:
        raise ValidationError("존재하지 않는 업무유형입니다.")


def create_client(
    name: str,
    default_category_id: int | None = None,
    default_work_type_id: int | None = None,
    memo: str | None = None,
) -> int:
    name = _validate_client_name(name)
    _validate_optional_category(default_category_id)
    _validate_optional_work_type(default_work_type_id)
    try:
        return repo.insert_client(name, default_category_id, default_work_type_id, memo)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 거래처입니다.")


def update_client_info(
    client_id: int,
    name: str,
    default_category_id: int | None = None,
    default_work_type_id: int | None = None,
    memo: str | None = None,
) -> None:
    """거래처 정보 수정. 여기서 바뀐 기본값은 이미 저장된 과거 거래에는 영향을 주지 않는다
    (거래는 등록 시점의 category_id/work_type_id를 그대로 보관하기 때문)."""
    name = _validate_client_name(name, exclude_id=client_id)
    _validate_optional_category(default_category_id)
    _validate_optional_work_type(default_work_type_id)
    try:
        repo.update_client(client_id, name, default_category_id, default_work_type_id, memo)
    except sqlite3.IntegrityError:
        raise ValidationError("이미 등록된 거래처입니다.")


def deactivate_client(client_id: int) -> None:
    """삭제 대신 비활성화. 기존 거래내역은 그대로 유지되고, 신규 거래등록에서만 제외된다."""
    repo.set_client_active(client_id, False)


def activate_client(client_id: int) -> None:
    repo.set_client_active(client_id, True)

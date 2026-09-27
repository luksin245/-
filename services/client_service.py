from db import client_repository as repo


def get_clients() -> list[dict]:
    return repo.get_clients()


def get_or_create_client(name: str) -> int:
    """이름이 이미 존재하면 해당 id를, 없으면 새로 등록 후 id를 반환한다."""
    name = name.strip()
    existing = repo.get_client_by_name(name)
    if existing:
        return existing["id"]
    return repo.insert_client(name)

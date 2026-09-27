from db import work_type_repository as repo


def get_work_types() -> list[dict]:
    return repo.get_work_types()

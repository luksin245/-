from db import category_repository as repo


def get_income_categories() -> list[dict]:
    return repo.get_categories(type_="income")


def get_expense_categories() -> list[dict]:
    return repo.get_categories(type_="expense")


def get_categories_by_type(transaction_type: str) -> list[dict]:
    return repo.get_categories(type_=transaction_type)

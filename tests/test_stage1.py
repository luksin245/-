"""1단계(DB 구축 + 거래 직접 입력) 수동 검증 스크립트.

실행 방법:
    python tests/test_stage1.py

Streamlit UI를 직접 조작하지 않고, UI가 호출하는 것과 동일한
services / db 계층 함수를 그대로 호출하여 요구된 11개 시나리오를 검증한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db, DB_PATH
from db import category_repository, work_type_repository, transaction_repository
from services import transaction_service
from utils.validators import ValidationError

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def main() -> bool:
    # 1. DB 최초 생성 (기존 파일 제거 후 재생성하여 '최초 실행'을 재현)
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    check("1. DB 파일 최초 생성", DB_PATH.exists())

    # 2. 기본 카테고리 생성
    income_cats = category_repository.get_categories(type_="income")
    expense_cats = category_repository.get_categories(type_="expense")
    check("2. 기본 수입 카테고리 8개 생성", len(income_cats) == 8)
    check("2. 기본 지출 카테고리 14개 생성", len(expense_cats) == 14)

    # 3. 기본 업무유형 생성
    work_types = work_type_repository.get_work_types()
    check("3. 기본 업무유형 8개 생성", len(work_types) == 8)

    # 4. 수입 거래 저장
    income_id = transaction_service.create_transaction(
        transaction_date="2026-09-01",
        transaction_type="income",
        description="OO기업 자문료",
        amount=500000,
        category_id=income_cats[0]["id"],
    )
    saved = next(t for t in transaction_repository.get_all_transactions() if t["id"] == income_id)
    check(
        "4. 수입 거래 저장 (type=income, amount=500000, 양수)",
        saved["transaction_type"] == "income" and saved["amount"] == 500000,
    )

    # 5. 지출 거래 저장
    expense_id = transaction_service.create_transaction(
        transaction_date="2026-09-02",
        transaction_type="expense",
        description="통신비 결제",
        amount=100000,
        category_id=expense_cats[0]["id"],
    )
    saved = next(t for t in transaction_repository.get_all_transactions() if t["id"] == expense_id)
    check(
        "5. 지출 거래 저장 (type=expense, amount=100000, 양수)",
        saved["transaction_type"] == "expense" and saved["amount"] == 100000,
    )

    # 6. 선택항목 없이 필수값만 저장
    minimal_id = transaction_service.create_transaction(
        transaction_date="2026-09-03",
        transaction_type="income",
        description="최소 입력 테스트",
        amount=1000,
    )
    saved = next(t for t in transaction_repository.get_all_transactions() if t["id"] == minimal_id)
    check(
        "6. 선택항목(카테고리/거래처/업무유형) 없이 필수값만 저장",
        saved["category_id"] is None and saved["client_id"] is None and saved["work_type_id"] is None,
    )

    # 7. 금액 0원 입력 -> 거부되어야 함
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-04",
            transaction_type="income",
            description="0원 테스트",
            amount=0,
        )
        check("7. 금액 0원 입력 거부", False)
    except ValidationError:
        check("7. 금액 0원 입력 거부", True)

    # 8. 음수 금액 입력 -> 거부되어야 함
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-05",
            transaction_type="expense",
            description="음수 테스트",
            amount=-100000,
        )
        check("8. 음수 금액 입력 거부", False)
    except ValidationError:
        check("8. 음수 금액 입력 거부", True)

    # 9. 필수값(거래내용) 누락 -> 거부되어야 함
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-06",
            transaction_type="income",
            description="",
            amount=10000,
        )
        check("9. 필수값(거래내용) 누락 거부", False)
    except ValidationError:
        check("9. 필수값(거래내용) 누락 거부", True)

    # 10. 프로그램 재실행 후 기존 데이터 유지 (DB 파일을 지우지 않고 init_db 재호출)
    count_before_restart = transaction_repository.count_transactions()
    init_db()
    count_after_restart = transaction_repository.count_transactions()
    check(
        "10. 재실행 후 기존 거래 데이터 유지",
        count_before_restart == count_after_restart and count_after_restart > 0,
    )

    # 11. 기본 데이터가 재실행 시 중복 생성되지 않음
    income_cats_after = category_repository.get_categories(type_="income")
    expense_cats_after = category_repository.get_categories(type_="expense")
    work_types_after = work_type_repository.get_work_types()
    check(
        "11. 재실행 시 기본 카테고리/업무유형 중복 생성되지 않음",
        len(income_cats_after) == 8 and len(expense_cats_after) == 14 and len(work_types_after) == 8,
    )

    print()
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"결과: {passed}/{total} 통과")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

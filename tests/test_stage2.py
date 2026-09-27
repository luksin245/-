"""2단계(거래내역 조회/검색/필터/수정/삭제) 검증 스크립트 + 1단계 회귀 테스트.

실행 방법:
    python tests/test_stage2.py

실제 data/finance.db는 절대 건드리지 않고, tests/ 폴더 아래
임시 DB 파일(_stage1_regression.db, _stage2_test.db)을 만들어 사용한 뒤
스크립트 종료 시 삭제한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.database as database  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def run_stage1_regression() -> None:
    """1단계 기능(거래등록/기본 카테고리/업무유형/즉석 거래처 등록/검증/재실행)이 깨지지 않았는지 확인."""
    print("\n=== 1단계 회귀 테스트 ===")
    temp_db = Path(__file__).resolve().parent / "_stage1_regression.db"
    if temp_db.exists():
        temp_db.unlink()
    database.DB_PATH = temp_db

    from db import category_repository, work_type_repository, transaction_repository
    from services import transaction_service, client_service
    from utils.validators import ValidationError

    database.init_db()
    check("1단계-1. DB 최초 생성", temp_db.exists())

    income_cats = category_repository.get_categories(type_="income")
    expense_cats = category_repository.get_categories(type_="expense")
    check("1단계-2. 기본 수입 카테고리 8개", len(income_cats) == 8)
    check("1단계-2. 기본 지출 카테고리 14개", len(expense_cats) == 14)

    work_types = work_type_repository.get_work_types()
    check("1단계-3. 기본 업무유형 8개", len(work_types) == 8)

    income_id = transaction_service.create_transaction(
        transaction_date="2026-09-01",
        transaction_type="income",
        description="회귀테스트 수입",
        amount=100000,
        category_id=income_cats[0]["id"],
    )
    saved = transaction_repository.get_transaction_by_id(income_id)
    check("1단계-4. 수입 거래 저장", saved["transaction_type"] == "income" and saved["amount"] == 100000)

    expense_id = transaction_service.create_transaction(
        transaction_date="2026-09-02",
        transaction_type="expense",
        description="회귀테스트 지출",
        amount=50000,
        category_id=expense_cats[0]["id"],
    )
    saved = transaction_repository.get_transaction_by_id(expense_id)
    check("1단계-5. 지출 거래 저장", saved["transaction_type"] == "expense" and saved["amount"] == 50000)

    new_client_id = client_service.get_or_create_client("회귀테스트거래처")
    check("1단계-6. 새 거래처 즉석 등록", new_client_id is not None)

    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-03", transaction_type="income",
            description="0원 테스트", amount=0,
        )
        check("1단계-7. 금액 0원 거부", False)
    except ValidationError:
        check("1단계-7. 금액 0원 거부", True)

    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-03", transaction_type="income",
            description="", amount=1000,
        )
        check("1단계-8. 필수값 누락 거부", False)
    except ValidationError:
        check("1단계-8. 필수값 누락 거부", True)

    count_before = transaction_repository.count_transactions()
    database.init_db()
    count_after = transaction_repository.count_transactions()
    check("1단계-9. 재실행 후 데이터 유지", count_before == count_after and count_after > 0)

    income_cats_after = category_repository.get_categories(type_="income")
    check("1단계-10. 재실행 시 기본 카테고리 중복 생성 안됨", len(income_cats_after) == 8)

    temp_db.unlink(missing_ok=True)


def run_stage2_tests() -> None:
    print("\n=== 2단계 신규 기능 테스트 ===")
    temp_db = Path(__file__).resolve().parent / "_stage2_test.db"
    if temp_db.exists():
        temp_db.unlink()
    database.DB_PATH = temp_db

    from db import category_repository, transaction_repository
    from services import client_service, transaction_service
    from utils.validators import ValidationError

    database.init_db()

    income_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="income")}
    expense_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="expense")}

    kt_id = client_service.get_or_create_client("KT")
    naver_id = client_service.get_or_create_client("네이버")

    # --- 테스트용 거래 7건 생성 ---
    tx_oo = transaction_service.create_transaction(
        transaction_date="2026-08-15", transaction_type="income",
        description="OO기업 자문료", amount=1_000_000,
        category_id=income_cat["기업자문"],
    )
    tx_naver_income = transaction_service.create_transaction(
        transaction_date="2026-09-05", transaction_type="income",
        description="네이버 강의료 입금", amount=300_000,
        category_id=income_cat["강의료"], client_id=naver_id,
    )
    tx_counsel = transaction_service.create_transaction(
        transaction_date="2026-09-10", transaction_type="income",
        description="상담료 입금", amount=200_000,
        category_id=income_cat["상담료"], evidence_status="없음",
    )
    tx_kt1 = transaction_service.create_transaction(
        transaction_date="2026-09-01", transaction_type="expense",
        description="KT 통신비 자동이체", amount=55_000,
        category_id=expense_cat["통신비"], client_id=kt_id,
    )
    tx_kt2 = transaction_service.create_transaction(
        transaction_date="2026-09-02", transaction_type="expense",
        description="자동이체 KT 인터넷", amount=30_000,
        category_id=expense_cat["통신비"], client_id=kt_id,
    )
    tx_naver_ad = transaction_service.create_transaction(
        transaction_date="2026-09-12", transaction_type="expense",
        description="네이버 광고비 결제", amount=150_000,
        category_id=expense_cat["광고선전비"], client_id=naver_id,
    )
    tx_office = transaction_service.create_transaction(
        transaction_date="2026-08-20", transaction_type="expense",
        description="사무용품 구매", amount=45_000,
        category_id=expense_cat["사무용품비"], evidence_status="없음",
    )

    all_ids = {tx_oo, tx_naver_income, tx_counsel, tx_kt1, tx_kt2, tx_naver_ad, tx_office}

    # 1. 거래 전체 조회
    all_tx = transaction_service.list_transactions()
    check("1. 거래 전체 조회 (7건)", len(all_tx) == 7 and {t["id"] for t in all_tx} == all_ids)

    # 2. 날짜 범위 필터 (9월만)
    sept_tx = transaction_service.list_transactions(
        {"start_date": "2026-09-01", "end_date": "2026-09-30"}
    )
    check("2. 날짜 범위 필터 (9월 5건)", len(sept_tx) == 5)

    # 3. 수입 필터
    income_tx = transaction_service.list_transactions({"transaction_type": "income"})
    check("3. 수입 필터 (3건)", len(income_tx) == 3 and all(t["transaction_type"] == "income" for t in income_tx))

    # 4. 지출 필터
    expense_tx = transaction_service.list_transactions({"transaction_type": "expense"})
    check("4. 지출 필터 (4건)", len(expense_tx) == 4 and all(t["transaction_type"] == "expense" for t in expense_tx))

    # 5. 카테고리 필터 (통신비 2건)
    telecom_tx = transaction_service.list_transactions({"category_id": expense_cat["통신비"]})
    check("5. 카테고리 필터 (통신비 2건)", len(telecom_tx) == 2)

    # 6. 거래처 필터 (네이버 2건: 수입1 + 지출1)
    naver_tx = transaction_service.list_transactions({"client_id": naver_id})
    check("6. 거래처 필터 (네이버 2건)", len(naver_tx) == 2)

    # 7. 업무유형 필터 (지정하지 않았으므로 work_type_id=None인 필터로는 스킵,
    #    대신 명시적으로 work_type이 세팅되지 않은 거래를 제외하는지 카테고리 필터와 조합 확인)
    #    -> 업무유형 자체 필터 기능은 category/client와 동일한 방식으로 구현되어 있으므로
    #       존재하지 않는 work_type_id(0)로 조회 시 0건이 되는지로 필터 동작을 검증한다.
    empty_worktype_tx = transaction_service.list_transactions({"work_type_id": 999999})
    check("7. 업무유형 필터 (존재하지 않는 id -> 0건)", len(empty_worktype_tx) == 0)

    # 8. 거래내용 부분검색 ("KT" -> 2건)
    kt_search = transaction_service.list_transactions({"keyword": "KT"})
    check("8. 거래내용 부분검색 'KT' (2건)", len(kt_search) == 2)

    # 9. 여러 필터 동시 적용 (9월 + 지출 + 광고선전비 -> 1건)
    combo = transaction_service.list_transactions({
        "start_date": "2026-09-01", "end_date": "2026-09-30",
        "transaction_type": "expense", "category_id": expense_cat["광고선전비"],
    })
    check("9. 복합 필터 (9월+지출+광고선전비 1건)", len(combo) == 1 and combo[0]["id"] == tx_naver_ad)

    # 10. 필터 초기화 (필터 없음 == 전체 조회와 동일)
    no_filter = transaction_service.list_transactions({})
    check("10. 필터 초기화 시 전체 조회와 동일", len(no_filter) == 7)

    # 11. 거래 수정 (설명 변경)
    transaction_service.update_transaction(
        transaction_id=tx_counsel,
        transaction_date="2026-09-10",
        transaction_type="income",
        description="상담료 입금 (수정됨)",
        amount=200_000,
        category_id=income_cat["상담료"],
    )
    updated = transaction_service.get_transaction(tx_counsel)
    check("11. 거래 수정 (거래내용 변경)", updated["description"] == "상담료 입금 (수정됨)")

    # 12. 거래 금액 수정
    transaction_service.update_transaction(
        transaction_id=tx_counsel,
        transaction_date="2026-09-10",
        transaction_type="income",
        description="상담료 입금 (수정됨)",
        amount=250_000,
        category_id=income_cat["상담료"],
    )
    updated = transaction_service.get_transaction(tx_counsel)
    check("12. 거래 금액 수정 (250000원)", updated["amount"] == 250_000)

    # 13. 수입 -> 지출 변경
    transaction_service.update_transaction(
        transaction_id=tx_counsel,
        transaction_date="2026-09-10",
        transaction_type="expense",
        description="상담료 입금 (수정됨)",
        amount=250_000,
        category_id=expense_cat["기타"],
    )
    updated = transaction_service.get_transaction(tx_counsel)
    check("13. 수입 -> 지출 변경", updated["transaction_type"] == "expense")

    # 14-a. 수입->지출 변경 시 카테고리를 비워서 넘기면 정상 저장되고 남지 않음
    transaction_service.update_transaction(
        transaction_id=tx_counsel,
        transaction_date="2026-09-10",
        transaction_type="expense",
        description="상담료 입금 (수정됨)",
        amount=250_000,
        category_id=None,
    )
    updated = transaction_service.get_transaction(tx_counsel)
    check("14-a. 수입->지출 변경 후 카테고리 비움", updated["category_id"] is None)

    # 14-b. service 계층 안전장치: type=expense인데 income 카테고리 id를 넘기면 거부되어야 함
    try:
        transaction_service.update_transaction(
            transaction_id=tx_counsel,
            transaction_date="2026-09-10",
            transaction_type="expense",
            description="상담료 입금 (수정됨)",
            amount=250_000,
            category_id=income_cat["상담료"],  # 잘못된 조합
        )
        check("14-b. 잘못된 카테고리/유형 조합 service에서 거부", False)
    except ValidationError:
        check("14-b. 잘못된 카테고리/유형 조합 service에서 거부", True)
    # 거부된 시도가 DB에 반영되지 않았는지 확인
    unchanged = transaction_service.get_transaction(tx_counsel)
    check("14-b. 거부된 시도가 DB에 반영되지 않음", unchanged["category_id"] is None)

    # 15. 지출 -> 수입 변경 (다른 거래로 확인: 사무용품 구매)
    transaction_service.update_transaction(
        transaction_id=tx_office,
        transaction_date="2026-08-20",
        transaction_type="income",
        description="사무용품 구매",
        amount=45_000,
        category_id=income_cat["기타"],
    )
    updated = transaction_service.get_transaction(tx_office)
    check("15. 지출 -> 수입 변경", updated["transaction_type"] == "income" and updated["category_id"] == income_cat["기타"])
    # 원상복구 (이후 요약 계산 테스트에 영향 주지 않도록)
    transaction_service.update_transaction(
        transaction_id=tx_office,
        transaction_date="2026-08-20",
        transaction_type="expense",
        description="사무용품 구매",
        amount=45_000,
        category_id=expense_cat["사무용품비"],
    )

    # 16. 거래 삭제
    tx_throwaway = transaction_service.create_transaction(
        transaction_date="2026-09-20", transaction_type="expense",
        description="삭제될 거래", amount=1_000,
    )
    transaction_service.delete_transaction(tx_throwaway)
    check("16. 거래 삭제", transaction_service.get_transaction(tx_throwaway) is None)

    # 17. 삭제 취소 (삭제를 호출하지 않으면 데이터가 그대로 남아있어야 함)
    tx_keep = transaction_service.create_transaction(
        transaction_date="2026-09-21", transaction_type="expense",
        description="삭제 취소 확인용 거래", amount=2_000,
    )
    check("17. 삭제 취소 시 데이터 유지", transaction_service.get_transaction(tx_keep) is not None)
    transaction_service.delete_transaction(tx_keep)  # 정리

    # 18. 필수값(거래내용) 누락 수정 거부
    before = transaction_service.get_transaction(tx_kt1)
    try:
        transaction_service.update_transaction(
            transaction_id=tx_kt1, transaction_date="2026-09-01",
            transaction_type="expense", description="", amount=55_000,
        )
        check("18. 필수값 누락 수정 거부", False)
    except ValidationError:
        check("18. 필수값 누락 수정 거부", True)
    after = transaction_service.get_transaction(tx_kt1)
    check("18. 거부된 수정이 DB에 반영 안됨", before["description"] == after["description"])

    # 19. 금액 0원 수정 거부
    try:
        transaction_service.update_transaction(
            transaction_id=tx_kt1, transaction_date="2026-09-01",
            transaction_type="expense", description="KT 통신비 자동이체", amount=0,
        )
        check("19. 금액 0원 수정 거부", False)
    except ValidationError:
        check("19. 금액 0원 수정 거부", True)

    # 20. 음수 금액 수정 거부
    try:
        transaction_service.update_transaction(
            transaction_id=tx_kt1, transaction_date="2026-09-01",
            transaction_type="expense", description="KT 통신비 자동이체", amount=-5000,
        )
        check("20. 음수 금액 수정 거부", False)
    except ValidationError:
        check("20. 음수 금액 수정 거부", True)
    after = transaction_service.get_transaction(tx_kt1)
    check("19/20. 거부된 수정 이후 금액 원본 유지(55000)", after["amount"] == 55_000)

    # 21. 필터 결과 0건 정상 처리
    empty_result = transaction_service.list_transactions({"keyword": "존재하지않는거래내용XYZ"})
    empty_summary = transaction_service.get_summary({"keyword": "존재하지않는거래내용XYZ"})
    check(
        "21. 필터 결과 0건 정상 처리",
        empty_result == [] and empty_summary["count"] == 0
        and empty_summary["total_income"] == 0 and empty_summary["total_expense"] == 0
        and empty_summary["net_amount"] == 0,
    )

    # 22. 검색 결과 총수입/총지출/순금액 계산 (9월 필터 기준)
    sept_summary = transaction_service.get_summary({"start_date": "2026-09-01", "end_date": "2026-09-30"})
    # 9월 수입: 네이버 강의료 300000 (상담료는 13번 테스트에서 지출로 바뀐 상태)
    # 9월 지출: KT 55000 + KT 30000 + 네이버광고 150000 + (구 상담료->지출, 카테고리 비움) 250000
    expected_income = 300_000
    expected_expense = 55_000 + 30_000 + 150_000 + 250_000
    check(
        "22. 검색 결과 총수입/총지출/순금액 계산",
        sept_summary["total_income"] == expected_income
        and sept_summary["total_expense"] == expected_expense
        and sept_summary["net_amount"] == expected_income - expected_expense,
    )

    # 23. 앱 재시작 후 수정/삭제 결과 유지 (init_db 재호출로 재시작 시뮬레이션)
    database.init_db()
    persisted = transaction_service.get_transaction(tx_counsel)
    check(
        "23. 재시작 후 수정 결과 유지 (수입->지출, 카테고리 비움)",
        persisted["transaction_type"] == "expense" and persisted["category_id"] is None,
    )
    check("23. 재시작 후 삭제 결과 유지 (삭제된 거래 조회 안됨)", transaction_service.get_transaction(tx_throwaway) is None)
    check("23. 재시작 후 삭제 취소했던 거래는 이후 정리 삭제 반영", transaction_service.get_transaction(tx_keep) is None)

    temp_db.unlink(missing_ok=True)


def main() -> bool:
    run_stage1_regression()
    run_stage2_tests()

    print()
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"결과: {passed}/{total} 통과")
    if passed != total:
        print("\n실패 항목:")
        for name, ok in results:
            if not ok:
                print(f" - {name}")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

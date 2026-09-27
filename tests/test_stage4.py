"""4단계(기준정보 관리: 거래처/카테고리/업무유형) 검증 스크립트 + 1~3단계 회귀 테스트.

실행 방법:
    python tests/test_stage4.py

실제 data/finance.db는 어떤 테스트에서도 절대 읽기/쓰기/삭제하지 않는다.
모든 검증은 tests/ 폴더 아래 임시 DB 파일을 만들어 사용하고, 끝나면 삭제한다.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.database as database  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def use_temp_db(name: str) -> Path:
    temp_db = Path(__file__).resolve().parent / name
    if temp_db.exists():
        temp_db.unlink()
    database.DB_PATH = temp_db
    return temp_db


# ---------------------------------------------------------------------------
# Phase 0: 1~3단계 회귀 (32~38)
# ---------------------------------------------------------------------------
def run_regression() -> None:
    print("\n=== 1~3단계 회귀 테스트 ===")
    temp_db = use_temp_db("_stage4_regression.db")

    from db import category_repository, work_type_repository
    from services import client_service, dashboard_service, transaction_service
    from utils.validators import ValidationError

    database.init_db()

    income_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="income")}
    expense_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="expense")}
    work_type_ids = {w["name"]: w["id"] for w in work_type_repository.get_work_types()}
    naver_id = client_service.get_or_create_client("네이버")

    # 32. 거래등록
    tx1 = transaction_service.create_transaction(
        transaction_date="2026-09-01", transaction_type="income",
        description="네이버 강의료", amount=300_000,
        category_id=income_cat["강의료"], work_type_id=work_type_ids["강의"], client_id=naver_id,
    )
    tx2 = transaction_service.create_transaction(
        transaction_date="2026-09-05", transaction_type="expense",
        description="사무용품 구매", amount=45_000, category_id=expense_cat["사무용품비"],
    )
    check("32. 거래등록", transaction_service.get_transaction(tx1) is not None and transaction_service.get_transaction(tx2) is not None)

    # 33. 거래검색/필터
    found = transaction_service.list_transactions({"keyword": "네이버"})
    check("33. 거래검색/필터", len(found) == 1 and found[0]["id"] == tx1)

    # 34. 거래수정
    transaction_service.update_transaction(
        transaction_id=tx2, transaction_date="2026-09-05", transaction_type="expense",
        description="사무용품 구매(수정)", amount=50_000, category_id=expense_cat["사무용품비"],
    )
    check("34. 거래수정", transaction_service.get_transaction(tx2)["amount"] == 50_000)

    # 35. 거래삭제
    transaction_service.delete_transaction(tx2)
    check("35. 거래삭제", transaction_service.get_transaction(tx2) is None)

    # 미분류 집계용 거래(카테고리/거래처/업무유형 없음)
    transaction_service.create_transaction(
        transaction_date="2026-09-10", transaction_type="expense",
        description="미분류 지출", amount=20_000,
    )

    # 36/37/38. 대시보드 KPI/차트/미분류 집계
    start, end = dashboard_service.get_period_range("이번 달", today=date(2026, 9, 27))
    data = dashboard_service.get_dashboard_data(start, end)
    check("36. 대시보드 KPI", data["summary"]["total_income"] == 300_000 and data["summary"]["total_expense"] == 20_000)
    check("37. 대시보드 차트 집계 (업무유형별)", any(r["work_type_name"] == "강의" and r["total"] == 300_000 for r in data["income_by_work_type"]))
    check("38. 미분류 데이터 집계", any(r["category_name"] == "미분류" and r["total"] == 20_000 for r in data["expense_by_category"]))

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase A: 거래처
# ---------------------------------------------------------------------------
def run_client_tests() -> None:
    print("\n=== 거래처 관리 테스트 ===")
    temp_db = use_temp_db("_stage4_client.db")

    from db import category_repository, work_type_repository
    from services import client_service, transaction_service
    from utils.validators import ValidationError

    database.init_db()
    income_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="income")}
    work_type_ids = {w["name"]: w["id"] for w in work_type_repository.get_work_types()}

    # 1. 거래처 추가
    client_id = client_service.create_client(
        "A거래처", default_category_id=income_cat["기업자문"], default_work_type_id=work_type_ids["기업자문"], memo="주요 고객"
    )
    check("1. 거래처 추가", client_service.get_client(client_id)["name"] == "A거래처")
    # 8/9. 기본 카테고리/업무유형 저장
    saved = client_service.get_client(client_id)
    check("8. 거래처 기본 카테고리 저장", saved["default_category_id"] == income_cat["기업자문"])
    check("9. 거래처 기본 업무유형 저장", saved["default_work_type_id"] == work_type_ids["기업자문"])

    # 2. 거래처 중복 추가 차단 (대소문자/공백 차이 포함)
    try:
        client_service.create_client("A거래처")
        check("2. 거래처 중복 추가 차단", False)
    except ValidationError:
        check("2. 거래처 중복 추가 차단", True)
    try:
        client_service.create_client("  a거래처  ")  # 대소문자+공백 차이
        check("2-보조. 대소문자/공백 차이 중복도 차단", False)
    except ValidationError:
        check("2-보조. 대소문자/공백 차이 중복도 차단", True)

    # 3. 거래처 수정
    client_service.update_client_info(client_id, "A거래처(수정)", income_cat["기업자문"], work_type_ids["기업자문"], "메모 수정")
    check("3. 거래처 수정", client_service.get_client(client_id)["name"] == "A거래처(수정)")

    # 12. 거래처 기본값 수정이 과거 거래에는 영향 없음
    tx_id = transaction_service.create_transaction(
        transaction_date="2026-09-01", transaction_type="income", description="A거래처 자문료",
        amount=1_000_000, category_id=income_cat["기업자문"], client_id=client_id,
    )
    client_service.update_client_info(client_id, "A거래처(수정)", income_cat["컨설팅"], work_type_ids["컨설팅"], "메모 수정")
    check(
        "12. 거래처 기본값 수정이 과거 거래에 영향 없음",
        transaction_service.get_transaction(tx_id)["category_id"] == income_cat["기업자문"],
    )

    # 4. 거래처 비활성화
    client_service.deactivate_client(client_id)
    check("4. 거래처 비활성화", client_service.get_client(client_id)["is_active"] == 0)

    # 6. 비활성 거래처가 신규 거래등록 목록에서 제외
    active_clients = client_service.get_clients()
    check("6. 비활성 거래처가 신규 목록에서 제외", all(c["id"] != client_id for c in active_clients))

    # 7. 비활성 거래처가 기존 거래에는 정상 표시
    tx = transaction_service.get_transaction(tx_id)
    check("7. 비활성 거래처가 기존 거래에는 정상 표시", tx["client_name"] == "A거래처(수정)")

    # 신규 등록 시 비활성 거래처를 새로 지정하면 거부
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-02", transaction_type="income", description="비활성 거래처 테스트",
            amount=10_000, client_id=client_id,
        )
        check("신규 등록에서 비활성 거래처 지정 거부", False)
    except ValidationError:
        check("신규 등록에서 비활성 거래처 지정 거부", True)

    # 수정 시 기존 값(비활성 거래처) 그대로 두는 것은 허용
    transaction_service.update_transaction(
        transaction_id=tx_id, transaction_date="2026-09-01", transaction_type="income",
        description="A거래처 자문료(메모수정)", amount=1_000_000,
        category_id=income_cat["기업자문"], client_id=client_id,
    )
    check("수정 시 기존 비활성 거래처값 유지 허용", transaction_service.get_transaction(tx_id)["client_id"] == client_id)

    # 5. 거래처 재활성화
    client_service.activate_client(client_id)
    check("5. 거래처 재활성화", client_service.get_client(client_id)["is_active"] == 1)
    active_clients_after = client_service.get_clients()
    check("5-보조. 재활성화 후 신규 목록에 다시 포함", any(c["id"] == client_id for c in active_clients_after))

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase B: 카테고리
# ---------------------------------------------------------------------------
def run_category_tests() -> None:
    print("\n=== 카테고리 관리 테스트 ===")
    temp_db = use_temp_db("_stage4_category.db")

    from services import category_service, transaction_service
    from utils.validators import ValidationError

    database.init_db()

    # 13/14. 수입/지출 카테고리 추가
    income_id = category_service.create_category("신규수입카테고리", "income", sort_order=99)
    expense_id = category_service.create_category("신규지출카테고리", "expense", sort_order=99)
    check("13. 수입 카테고리 추가", category_service.get_category(income_id)["type"] == "income")
    check("14. 지출 카테고리 추가", category_service.get_category(expense_id)["type"] == "expense")

    # 15. 동일 type+name 중복 차단
    try:
        category_service.create_category("신규수입카테고리", "income")
        check("15. 동일 type+name 중복 차단", False)
    except ValidationError:
        check("15. 동일 type+name 중복 차단", True)

    # 16. 수입/지출 동일 이름 각각 허용
    try:
        dup_id = category_service.create_category("신규수입카테고리", "expense")
        check("16. 수입/지출 동일 이름 각각 허용", category_service.get_category(dup_id)["type"] == "expense")
    except ValidationError:
        check("16. 수입/지출 동일 이름 각각 허용", False)

    # 17. 카테고리 이름 수정
    category_service.update_category_info(income_id, "수입카테고리(수정)", 5)
    updated = category_service.get_category(income_id)
    check("17. 카테고리 이름 수정", updated["name"] == "수입카테고리(수정)" and updated["sort_order"] == 5)

    # 18. type 변경 제한 (update_category_info는 애초에 type을 받지 않음 -> 항상 유지)
    check("18. type 변경 제한 (수정 후에도 income 유지)", category_service.get_category(income_id)["type"] == "income")

    # 19. 카테고리 비활성화
    category_service.deactivate_category(income_id)
    check("19. 카테고리 비활성화", category_service.get_category(income_id)["is_active"] == 0)

    # 21. 비활성 카테고리 신규 등록에서 제외
    active_income = category_service.get_income_categories()
    check("21. 비활성 카테고리 신규 등록에서 제외", all(c["id"] != income_id for c in active_income))

    # 22. 기존 거래의 비활성 카테고리 유지
    another_income_id = category_service.create_category("또다른수입카테고리", "income")
    tx_id = transaction_service.create_transaction(
        transaction_date="2026-09-01", transaction_type="income", description="비활성카테고리테스트",
        amount=100_000, category_id=another_income_id,
    )
    category_service.deactivate_category(another_income_id)
    check("22. 기존 거래의 비활성 카테고리 유지", transaction_service.get_transaction(tx_id)["category_name"] == "또다른수입카테고리")

    # 신규 등록 시 비활성 카테고리 새로 지정하면 거부
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-02", transaction_type="income", description="거부되어야함",
            amount=1000, category_id=another_income_id,
        )
        check("신규 등록에서 비활성 카테고리 지정 거부", False)
    except ValidationError:
        check("신규 등록에서 비활성 카테고리 지정 거부", True)

    # 20. 카테고리 재활성화
    category_service.activate_category(income_id)
    check("20. 카테고리 재활성화", category_service.get_category(income_id)["is_active"] == 1)

    # 23/24. 수입/지출 카테고리 교차 저장 차단
    expense_cat_id = category_service.get_expense_categories()[0]["id"]
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-03", transaction_type="income", description="교차저장테스트",
            amount=1000, category_id=expense_cat_id,
        )
        check("23. 수입 거래에 지출 카테고리 저장 차단", False)
    except ValidationError:
        check("23. 수입 거래에 지출 카테고리 저장 차단", True)

    income_cat_id = category_service.get_income_categories()[0]["id"]
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-03", transaction_type="expense", description="교차저장테스트2",
            amount=1000, category_id=income_cat_id,
        )
        check("24. 지출 거래에 수입 카테고리 저장 차단", False)
    except ValidationError:
        check("24. 지출 거래에 수입 카테고리 저장 차단", True)

    # 마지막 활성 카테고리 보호 (모든 수입 카테고리를 비활성화하려 하면 마지막 1개는 막힘)
    all_income = category_service.list_categories_admin(status="active", type_filter="income")
    for c in all_income[:-1]:
        category_service.deactivate_category(c["id"])
    last_one = category_service.list_categories_admin(status="active", type_filter="income")
    check("last-guard 준비: 활성 수입 카테고리 1개 남음", len(last_one) == 1)
    try:
        category_service.deactivate_category(last_one[0]["id"])
        check("마지막 활성 카테고리 비활성화 방지", False)
    except ValidationError:
        check("마지막 활성 카테고리 비활성화 방지", True)

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase C: 업무유형
# ---------------------------------------------------------------------------
def run_work_type_tests() -> None:
    print("\n=== 업무유형 관리 테스트 ===")
    temp_db = use_temp_db("_stage4_work_type.db")

    from services import transaction_service, work_type_service
    from utils.validators import ValidationError

    database.init_db()

    # 25. 업무유형 추가
    wt_id = work_type_service.create_work_type("신규업무유형", sort_order=50)
    check("25. 업무유형 추가", work_type_service.get_work_type(wt_id)["name"] == "신규업무유형")

    # 26. 중복 추가 차단
    try:
        work_type_service.create_work_type("신규업무유형")
        check("26. 중복 추가 차단", False)
    except ValidationError:
        check("26. 중복 추가 차단", True)

    # 27. 업무유형 수정
    work_type_service.update_work_type_info(wt_id, "신규업무유형(수정)", 10)
    updated = work_type_service.get_work_type(wt_id)
    check("27. 업무유형 수정", updated["name"] == "신규업무유형(수정)" and updated["sort_order"] == 10)

    # 이름 수정이 과거 거래에도 반영되는지 (work_type_id로 참조하는 구조상 정상)
    tx_id = transaction_service.create_transaction(
        transaction_date="2026-09-01", transaction_type="income", description="업무유형이름반영테스트",
        amount=50_000, work_type_id=wt_id,
    )
    check("업무유형 이름 수정이 과거 거래 조회에도 반영됨", transaction_service.get_transaction(tx_id)["work_type_name"] == "신규업무유형(수정)")

    # 28. 업무유형 비활성화
    work_type_service.deactivate_work_type(wt_id)
    check("28. 업무유형 비활성화", work_type_service.get_work_type(wt_id)["is_active"] == 0)

    # 30. 신규 거래에서 비활성 업무유형 제외
    active_work_types = work_type_service.get_work_types()
    check("30. 신규 거래에서 비활성 업무유형 제외", all(w["id"] != wt_id for w in active_work_types))

    # 31. 기존 거래의 비활성 업무유형 유지
    check("31. 기존 거래의 비활성 업무유형 유지", transaction_service.get_transaction(tx_id)["work_type_name"] == "신규업무유형(수정)")

    # 신규 등록 시 비활성 업무유형 새로 지정하면 거부
    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-02", transaction_type="income", description="거부되어야함",
            amount=1000, work_type_id=wt_id,
        )
        check("신규 등록에서 비활성 업무유형 지정 거부", False)
    except ValidationError:
        check("신규 등록에서 비활성 업무유형 지정 거부", True)

    # 29. 업무유형 재활성화
    work_type_service.activate_work_type(wt_id)
    check("29. 업무유형 재활성화", work_type_service.get_work_type(wt_id)["is_active"] == 1)

    temp_db.unlink(missing_ok=True)


def main() -> bool:
    run_regression()
    run_client_tests()
    run_category_tests()
    run_work_type_tests()

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

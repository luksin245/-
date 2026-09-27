"""3단계(대시보드) 검증 스크립트 + 1/2단계 회귀 테스트.

실행 방법:
    python tests/test_stage3.py

중요: 실제 data/finance.db는 절대 읽기/쓰기/삭제하지 않는다.
모든 검증은 tests/ 폴더 아래 임시 DB 파일(FINANCE_DB_PATH 오버라이드와 동일한
방식으로 db.database.DB_PATH를 그때그때 바꿔치기)을 사용하고, 각 단계가
끝나면 그 임시 파일을 정리한다.
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
# Phase 0: 1단계 회귀
# ---------------------------------------------------------------------------
def run_stage1_regression() -> None:
    print("\n=== 1단계 회귀 테스트 ===")
    temp_db = use_temp_db("_stage3_regression1.db")

    from db import category_repository, work_type_repository, transaction_repository
    from services import transaction_service, client_service
    from utils.validators import ValidationError

    database.init_db()
    check("29-1. DB 최초 생성", temp_db.exists())

    income_cats = category_repository.get_categories(type_="income")
    expense_cats = category_repository.get_categories(type_="expense")
    check("29-2. 기본 카테고리 생성(수입8/지출14)", len(income_cats) == 8 and len(expense_cats) == 14)

    work_types = work_type_repository.get_work_types()
    check("29-3. 기본 업무유형 8개", len(work_types) == 8)

    income_id = transaction_service.create_transaction(
        transaction_date="2026-09-01", transaction_type="income",
        description="회귀테스트 수입", amount=100000, category_id=income_cats[0]["id"],
    )
    check(
        "29-4. 수입 거래 저장",
        transaction_repository.get_transaction_by_id(income_id)["amount"] == 100000,
    )

    client_id = client_service.get_or_create_client("회귀테스트거래처")
    check("29-5. 새 거래처 즉석 등록", client_id is not None)

    try:
        transaction_service.create_transaction(
            transaction_date="2026-09-02", transaction_type="income",
            description="0원 테스트", amount=0,
        )
        check("29-6. 금액 0원 거부", False)
    except ValidationError:
        check("29-6. 금액 0원 거부", True)

    count_before = transaction_repository.count_transactions()
    database.init_db()
    count_after = transaction_repository.count_transactions()
    check("29-7. 재실행 후 데이터 유지 + 기본데이터 중복 없음", count_before == count_after)

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 0-2: 2단계 회귀
# ---------------------------------------------------------------------------
def run_stage2_regression() -> None:
    print("\n=== 2단계 회귀 테스트 ===")
    temp_db = use_temp_db("_stage3_regression2.db")

    from db import category_repository
    from services import transaction_service
    from utils.validators import ValidationError

    database.init_db()
    income_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="income")}
    expense_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="expense")}

    tx1 = transaction_service.create_transaction(
        transaction_date="2026-09-01", transaction_type="income",
        description="조회수정삭제 테스트", amount=100000, category_id=income_cat["상담료"],
    )
    tx2 = transaction_service.create_transaction(
        transaction_date="2026-09-02", transaction_type="expense",
        description="지출 테스트", amount=50000, category_id=expense_cat["교통비"],
    )

    found = transaction_service.list_transactions({"keyword": "조회수정삭제"})
    check("30-1. 조회/검색", len(found) == 1 and found[0]["id"] == tx1)

    transaction_service.update_transaction(
        transaction_id=tx1, transaction_date="2026-09-01", transaction_type="expense",
        description="조회수정삭제 테스트", amount=100000, category_id=None,
    )
    updated = transaction_service.get_transaction(tx1)
    check(
        "30-2. 수정(수입->지출, 카테고리 비움)",
        updated["transaction_type"] == "expense" and updated["category_id"] is None,
    )

    try:
        transaction_service.update_transaction(
            transaction_id=tx1, transaction_date="2026-09-01", transaction_type="expense",
            description="조회수정삭제 테스트", amount=100000, category_id=income_cat["상담료"],
        )
        check("30-3. 잘못된 카테고리/유형 조합 거부", False)
    except ValidationError:
        check("30-3. 잘못된 카테고리/유형 조합 거부", True)

    transaction_service.delete_transaction(tx2)
    check("30-4. 삭제", transaction_service.get_transaction(tx2) is None)

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 1: 완전히 빈 DB (거래 0건)
# ---------------------------------------------------------------------------
def run_empty_dashboard_test() -> None:
    print("\n=== 대시보드: 거래 0건 ===")
    temp_db = use_temp_db("_stage3_empty.db")

    from services import dashboard_service

    database.init_db()
    start, end = dashboard_service.get_period_range("이번 달", today=date(2026, 9, 27))
    data = dashboard_service.get_dashboard_data(start, end)

    check("1. 거래 0건일 때 count=0", data["summary"]["count"] == 0)
    check("1. 거래 0건일 때 total_income/expense=0", data["summary"]["total_income"] == 0 and data["summary"]["total_expense"] == 0)
    check("1. 거래 0건일 때 월별추이 빈 리스트(오류 없음)", data["monthly_trend"] == [])
    check("1. 거래 0건일 때 지출카테고리 빈 리스트(오류 없음)", data["expense_by_category"] == [])
    check("1. 거래 0건일 때 업무유형 빈 리스트(오류 없음)", data["income_by_work_type"] == [])
    check("1. 거래 0건일 때 거래처 빈 리스트(오류 없음)", data["income_by_client"] == [])
    check("1. 거래 0건일 때 최근거래 빈 리스트(오류 없음)", data["recent_transactions"] == [])

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 2: 수입만 존재
# ---------------------------------------------------------------------------
def run_income_only_test() -> None:
    print("\n=== 대시보드: 수입만 존재 ===")
    temp_db = use_temp_db("_stage3_income_only.db")

    from db import category_repository
    from services import transaction_service, dashboard_service

    database.init_db()
    income_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="income")}
    transaction_service.create_transaction(
        transaction_date="2026-09-05", transaction_type="income",
        description="수입만 있는 케이스", amount=500000, category_id=income_cat["강의료"],
    )

    start, end = dashboard_service.get_period_range("이번 달", today=date(2026, 9, 27))
    data = dashboard_service.get_dashboard_data(start, end)

    check("2. 수입만 존재 - 총수입 계산", data["summary"]["total_income"] == 500000)
    check("2. 수입만 존재 - 총지출 0", data["summary"]["total_expense"] == 0)
    check("2. 수입만 존재 - 순현금흐름", data["summary"]["net_amount"] == 500000)
    check("27. 지출 0건일 때 지출카테고리 차트 빈 리스트(오류 없음)", data["expense_by_category"] == [])
    check("2. 수입만 존재 - 업무유형 차트는 정상 표시", len(data["income_by_work_type"]) == 1)

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 3: 지출만 존재
# ---------------------------------------------------------------------------
def run_expense_only_test() -> None:
    print("\n=== 대시보드: 지출만 존재 ===")
    temp_db = use_temp_db("_stage3_expense_only.db")

    from db import category_repository
    from services import transaction_service, dashboard_service

    database.init_db()
    expense_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="expense")}
    transaction_service.create_transaction(
        transaction_date="2026-09-05", transaction_type="expense",
        description="지출만 있는 케이스", amount=80000, category_id=expense_cat["식비"],
    )

    start, end = dashboard_service.get_period_range("이번 달", today=date(2026, 9, 27))
    data = dashboard_service.get_dashboard_data(start, end)

    check("3. 지출만 존재 - 총지출 계산", data["summary"]["total_expense"] == 80000)
    check("3. 지출만 존재 - 총수입 0", data["summary"]["total_income"] == 0)
    check("3. 지출만 존재 - 순현금흐름(음수)", data["summary"]["net_amount"] == -80000)
    check("26. 수입 0건일 때 업무유형 차트 빈 리스트(오류 없음)", data["income_by_work_type"] == [])
    check("26. 수입 0건일 때 거래처 차트 빈 리스트(오류 없음)", data["income_by_client"] == [])
    check("3. 지출만 존재 - 지출카테고리 차트는 정상 표시", len(data["expense_by_category"]) == 1)

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 4: 기간 프리셋 계산 (날짜 로직만 검증, DB 불필요)
# ---------------------------------------------------------------------------
def run_period_preset_tests() -> None:
    print("\n=== 기간 프리셋 계산 ===")
    from services import dashboard_service

    today = date(2026, 9, 27)

    start, end = dashboard_service.get_period_range("이번 달", today=today)
    check("10. 이번 달", (start, end) == (date(2026, 9, 1), date(2026, 9, 27)))

    start, end = dashboard_service.get_period_range("지난달", today=today)
    check("11. 지난달", (start, end) == (date(2026, 8, 1), date(2026, 8, 31)))

    start, end = dashboard_service.get_period_range("최근 3개월", today=today)
    check("12. 최근 3개월", (start, end) == (date(2026, 7, 1), date(2026, 9, 27)))

    start, end = dashboard_service.get_period_range("올해", today=today)
    check("13. 올해", (start, end) == (date(2026, 1, 1), date(2026, 9, 27)))

    start, end = dashboard_service.get_period_range(
        "직접 선택", custom_start=date(2026, 5, 3), custom_end=date(2026, 5, 20), today=today
    )
    check("14. 직접 기간 선택", (start, end) == (date(2026, 5, 3), date(2026, 5, 20)))

    try:
        dashboard_service.get_period_range(
            "직접 선택", custom_start=date(2026, 5, 20), custom_end=date(2026, 5, 3), today=today
        )
        check("15. 시작일 > 종료일 오류 처리", False)
    except ValueError:
        check("15. 시작일 > 종료일 오류 처리", True)

    # 최근 3개월이 연도를 넘어가는 경우(1~2월 조회)도 안전한지 확인
    start, end = dashboard_service.get_period_range("최근 3개월", today=date(2026, 2, 15))
    check("12-보조. 최근 3개월(연도 경계)", (start, end) == (date(2025, 12, 1), date(2026, 2, 15)))


# ---------------------------------------------------------------------------
# Phase 5: 혼합 데이터 (여러 달, 여러 카테고리/업무유형/거래처, 미분류, 큰 금액)
# ---------------------------------------------------------------------------
def run_mixed_data_tests() -> None:
    print("\n=== 대시보드: 혼합 데이터(여러 달/카테고리/업무유형/거래처) ===")
    temp_db = use_temp_db("_stage3_mixed.db")

    from db import category_repository
    from services import transaction_service, client_service, dashboard_service

    database.init_db()
    income_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="income")}
    expense_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="expense")}
    client_a = client_service.get_or_create_client("A거래처")
    client_b = client_service.get_or_create_client("B거래처")

    plan = [
        # (date, type, amount, category_key, work_type, client)
        ("2026-07-10", "income", 4_000_000, "기업자문", "기업자문", client_a),
        ("2026-07-15", "expense", 1_200_000, "광고선전비", None, None),
        ("2026-08-05", "income", 5_000_000, "컨설팅", "컨설팅", client_b),
        ("2026-08-20", "expense", 1_500_000, "교통비", None, None),
        ("2026-09-01", "income", 4_000_000, "기업자문", "기업자문", client_a),
        ("2026-09-03", "income", 2_000_000, "상담료", None, None),  # work_type/client 미지정 -> 미분류
        ("2026-09-10", "expense", 1_200_000, "광고선전비", None, None),
        ("2026-09-12", "expense", 800_000, None, None, None),  # category 미지정 -> 미분류
        ("2026-09-15", "income", 999_999_999, "컨설팅", "컨설팅", None),  # 큰 금액 + client 미분류
    ]

    from db import work_type_repository
    work_type_ids = {w["name"]: w["id"] for w in work_type_repository.get_work_types()}

    inserted_ids = []
    for tx_date, ttype, amount, cat_key, wt_key, client_id in plan:
        cat_map = income_cat if ttype == "income" else expense_cat
        tx_id = transaction_service.create_transaction(
            transaction_date=tx_date,
            transaction_type=ttype,
            description=f"{tx_date} {ttype} {amount}",
            amount=amount,
            category_id=cat_map.get(cat_key) if cat_key else None,
            work_type_id=work_type_ids.get(wt_key) if wt_key else None,
            client_id=client_id,
        )
        inserted_ids.append((tx_id, tx_date, ttype, amount))

    expected_income_total = sum(a for _, _, t, a in inserted_ids if t == "income")
    expected_expense_total = sum(a for _, _, t, a in inserted_ids if t == "expense")
    expected_count = len(inserted_ids)

    start, end = dashboard_service.get_period_range("올해", today=date(2026, 9, 27))
    data = dashboard_service.get_dashboard_data(start, end)
    summary = data["summary"]

    check("4. 수입+지출 존재 - 정상 계산", summary["count"] == expected_count)
    check("5. 총수입 계산 정확성", summary["total_income"] == expected_income_total)
    check("6. 총지출 계산 정확성", summary["total_expense"] == expected_expense_total)
    check("7. 순현금흐름 계산 정확성", summary["net_amount"] == expected_income_total - expected_expense_total)
    check("8. 거래건수 계산", summary["count"] == expected_count)
    check(
        "28. 큰 금액(999,999,999) INTEGER 정확성",
        summary["total_income"] == expected_income_total and isinstance(summary["total_income"], int),
    )

    # 9. 기간 필터: 7월만 조회하면 7월 데이터만 집계되어야 함
    july_summary = dashboard_service.get_dashboard_data(date(2026, 7, 1), date(2026, 7, 31))["summary"]
    check("9. 기간 필터 (7월만)", july_summary["count"] == 2 and july_summary["total_income"] == 4_000_000)

    # 16. 월별 수입/지출 집계 + 25. 여러 달 데이터 차트 정상
    trend = data["monthly_trend"]
    trend_by_month = {r["month"]: r for r in trend}
    check("25. 여러 달 데이터 - 월 3개(07,08,09) 정상 표시", len(trend) == 3)
    check(
        "16. 월별 수입/지출 집계 정확성",
        trend_by_month["2026-07"]["income"] == 4_000_000
        and trend_by_month["2026-07"]["expense"] == 1_200_000
        and trend_by_month["2026-08"]["income"] == 5_000_000
        and trend_by_month["2026-08"]["expense"] == 1_500_000
        and trend_by_month["2026-09"]["expense"] == 2_000_000,
    )

    # 17/18. 지출 카테고리별 집계 + 미분류
    expense_by_cat = {r["category_name"]: r["total"] for r in data["expense_by_category"]}
    check(
        "17. 지출 카테고리별 집계 (금액 큰 순)",
        [r["category_name"] for r in data["expense_by_category"]][0] == "광고선전비",
    )
    check("18. 카테고리 없는 지출 -> 미분류", expense_by_cat.get("미분류") == 800_000)

    # 19/20. 업무유형별 매출 + 미분류
    income_by_wt = {r["work_type_name"]: r["total"] for r in data["income_by_work_type"]}
    check(
        "19. 업무유형별 매출 (금액 큰 순)",
        [r["work_type_name"] for r in data["income_by_work_type"]][0] == "컨설팅",
    )
    check("20. 업무유형 없는 수입 -> 미분류", income_by_wt.get("미분류") == 2_000_000)

    # 21/22. 거래처별 매출 TOP10 + client 없는 수입 -> 미분류 포함
    income_by_client = {r["client_name"]: r["total"] for r in data["income_by_client"]}
    check(
        "21. 거래처별 매출 TOP10 (금액 큰 순)",
        [r["client_name"] for r in data["income_by_client"]][0] == "미분류",  # 999,999,999가 가장 큼
    )
    check(
        "22. client 없는 수입 -> '미분류'로 포함 (제외되지 않음)",
        "미분류" in income_by_client and "A거래처" in income_by_client and "B거래처" in income_by_client,
    )

    # 23. 최근 거래 10건 정렬 (거래일자desc -> 시간desc -> id desc)
    recent = data["recent_transactions"]
    expected_order = sorted(
        inserted_ids, key=lambda r: (r[1], r[0]), reverse=True
    )  # (date, id) desc - 시간이 전부 없으므로 id로 2차 정렬
    check(
        "23. 최근 거래 정렬(최신순)",
        [r["id"] for r in recent] == [r[0] for r in expected_order][: len(recent)],
    )

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 6: 한 달만 데이터가 있는 경우 (24)
# ---------------------------------------------------------------------------
def run_single_month_test() -> None:
    print("\n=== 대시보드: 한 달 데이터만 존재 ===")
    temp_db = use_temp_db("_stage3_single_month.db")

    from db import category_repository
    from services import transaction_service, dashboard_service

    database.init_db()
    income_cat = {c["name"]: c["id"] for c in category_repository.get_categories(type_="income")}
    transaction_service.create_transaction(
        transaction_date="2026-09-10", transaction_type="income",
        description="한달치 데이터", amount=1_000_000, category_id=income_cat["기타"],
    )

    start, end = dashboard_service.get_period_range("이번 달", today=date(2026, 9, 27))
    data = dashboard_service.get_dashboard_data(start, end)
    check("24. 한 달 데이터만 있어도 월별추이 오류 없이 1개월 표시", len(data["monthly_trend"]) == 1)

    temp_db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 7: 최근 거래 10건 제한 (11건 이상 삽입 후 상위 10건만 반환되는지)
# ---------------------------------------------------------------------------
def run_recent_limit_test() -> None:
    print("\n=== 대시보드: 최근 거래 10건 제한 ===")
    temp_db = use_temp_db("_stage3_recent_limit.db")

    from services import transaction_service, dashboard_service

    database.init_db()
    for day in range(1, 13):  # 12건 생성
        transaction_service.create_transaction(
            transaction_date=f"2026-09-{day:02d}", transaction_type="income",
            description=f"거래 {day}", amount=1000 * day,
        )

    start, end = dashboard_service.get_period_range("이번 달", today=date(2026, 9, 27))
    data = dashboard_service.get_dashboard_data(start, end)
    check("23-보조. 최근 거래는 최대 10건만 반환", len(data["recent_transactions"]) == 10)
    check(
        "23-보조. 가장 최근(9/12)이 첫 번째",
        data["recent_transactions"][0]["transaction_date"] == "2026-09-12",
    )

    temp_db.unlink(missing_ok=True)


def main() -> bool:
    run_stage1_regression()
    run_stage2_regression()
    run_empty_dashboard_test()
    run_income_only_test()
    run_expense_only_test()
    run_period_preset_tests()
    run_mixed_data_tests()
    run_single_month_test()
    run_recent_limit_test()

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

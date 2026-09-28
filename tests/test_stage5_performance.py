"""18단계: 약 1만 건의 가짜 거래로 목록/검색/필터/대시보드 응답 속도를 점검하는 스크립트.

실행 방법:
    python tests/test_stage5_performance.py

실제 data/finance.db는 절대 건드리지 않고, tests/ 폴더 아래 임시 DB 파일에
1만 건을 생성한 뒤 각 조회 시나리오의 소요 시간을 측정하고 종료 시 삭제한다.
이 스크립트는 성능 "측정"이 목적이며, 기준 시간을 넘으면 실패로 처리해
인덱스 추가 등 개선이 필요한지 판단하는 데 사용한다.
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.database as database  # noqa: E402

TEMP_DB_PATH = Path(__file__).resolve().parent / "_stage5_perf_test.db"
if TEMP_DB_PATH.exists():
    TEMP_DB_PATH.unlink()
database.DB_PATH = TEMP_DB_PATH

from db.database import init_db  # noqa: E402
from services import category_service, client_service, dashboard_service, transaction_service, work_type_service  # noqa: E402

N_TRANSACTIONS = 10_000
# 사람이 "느리다"고 체감하기 시작하는 지점을 기준으로 넉넉하게 잡은 상한선(초).
MAX_SECONDS = 2.0

results: list[tuple[str, bool, float]] = []


def check(name: str, condition: bool, elapsed: float) -> None:
    results.append((name, bool(condition), elapsed))
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name} ({elapsed:.3f}초)")


def main() -> bool:
    init_db()

    income_cats = category_service.get_income_categories()
    expense_cats = category_service.get_expense_categories()
    work_types = work_type_service.get_work_types()

    client_ids = [client_service.get_or_create_client(f"거래처{i}") for i in range(30)]

    print(f"{N_TRANSACTIONS:,}건의 가짜 거래를 생성하는 중...")
    start_gen = time.perf_counter()
    base_date = date(2020, 1, 1)
    rows = []
    for i in range(N_TRANSACTIONS):
        is_income = i % 3 == 0
        transaction_type = "income" if is_income else "expense"
        categories = income_cats if is_income else expense_cats
        category = categories[i % len(categories)]
        work_type = work_types[i % len(work_types)]
        client_id = client_ids[i % len(client_ids)]
        tx_date = (base_date + timedelta(days=i % 2000)).isoformat()
        rows.append(
            {
                "transaction_date": tx_date,
                "transaction_time": None,
                "description": f"성능테스트거래 {i} KT",
                "transaction_type": transaction_type,
                "amount": 10_000 + (i % 500) * 1000,
                "balance": None,
                "category_id": category["id"],
                "client_id": client_id,
                "work_type_id": work_type["id"],
                "account_id": None,
                "accounting_type": "매출" if is_income else "비용",
                "vat_status": "과세",
                "evidence_status": "확인필요",
                "memo": None,
                "source_type": "manual",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        )

    conn = database.get_connection()
    try:
        conn.executemany(
            """
            INSERT INTO transactions (
                transaction_date, transaction_time, description, transaction_type, amount, balance,
                category_id, client_id, work_type_id, account_id, accounting_type,
                vat_status, evidence_status, memo, source_type, created_at, updated_at
            ) VALUES (
                :transaction_date, :transaction_time, :description, :transaction_type, :amount, :balance,
                :category_id, :client_id, :work_type_id, :account_id, :accounting_type,
                :vat_status, :evidence_status, :memo, :source_type, :created_at, :updated_at
            )
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    gen_elapsed = time.perf_counter() - start_gen
    print(f"생성 완료: {gen_elapsed:.1f}초")

    check("실제 저장된 거래건수가 1만 건과 일치", transaction_service.count_transactions() == N_TRANSACTIONS, gen_elapsed)

    # 1. 필터 없는 전체 목록 조회 (최근 거래 페이지 첫 진입 시나리오 - limit 사용)
    start = time.perf_counter()
    rows_page = transaction_service.list_transactions(limit=200)
    elapsed = time.perf_counter() - start
    check("1. 목록 첫 페이지(200건) 조회", len(rows_page) == 200 and elapsed < MAX_SECONDS, elapsed)

    # 2. 날짜 범위 필터
    start = time.perf_counter()
    filtered = transaction_service.list_transactions({"start_date": "2020-06-01", "end_date": "2020-06-30"})
    elapsed = time.perf_counter() - start
    check("2. 날짜 범위 필터 조회", len(filtered) > 0 and elapsed < MAX_SECONDS, elapsed)

    # 3. 수입/지출 구분 필터
    start = time.perf_counter()
    income_only = transaction_service.list_transactions({"transaction_type": "income"})
    elapsed = time.perf_counter() - start
    check("3. 수입/지출 구분 필터 조회", len(income_only) > 0 and elapsed < MAX_SECONDS, elapsed)

    # 4. 카테고리 필터
    start = time.perf_counter()
    by_category = transaction_service.list_transactions({"category_id": expense_cats[0]["id"]})
    elapsed = time.perf_counter() - start
    check("4. 카테고리 필터 조회", len(by_category) > 0 and elapsed < MAX_SECONDS, elapsed)

    # 5. 거래처 필터
    start = time.perf_counter()
    by_client = transaction_service.list_transactions({"client_id": client_ids[0]})
    elapsed = time.perf_counter() - start
    check("5. 거래처 필터 조회", len(by_client) > 0 and elapsed < MAX_SECONDS, elapsed)

    # 6. 업무유형 필터
    start = time.perf_counter()
    by_work_type = transaction_service.list_transactions({"work_type_id": work_types[0]["id"]})
    elapsed = time.perf_counter() - start
    check("6. 업무유형 필터 조회", len(by_work_type) > 0 and elapsed < MAX_SECONDS, elapsed)

    # 7. 회계구분 필터
    start = time.perf_counter()
    by_accounting_type = transaction_service.list_transactions({"accounting_type": "매출"})
    elapsed = time.perf_counter() - start
    check("7. 회계구분 필터 조회", len(by_accounting_type) > 0 and elapsed < MAX_SECONDS, elapsed)

    # 8. 거래내용 키워드 검색 (LIKE 검색 - 인덱스 없이도 허용 가능한 수준인지 확인)
    start = time.perf_counter()
    by_keyword = transaction_service.list_transactions({"keyword": "KT"})
    elapsed = time.perf_counter() - start
    check("8. 거래내용 키워드 검색", len(by_keyword) == N_TRANSACTIONS and elapsed < MAX_SECONDS, elapsed)

    # 9. 복합 필터(날짜+구분+카테고리 동시 적용)
    start = time.perf_counter()
    combined = transaction_service.list_transactions(
        {"start_date": "2020-01-01", "end_date": "2021-12-31", "transaction_type": "expense", "category_id": expense_cats[0]["id"]}
    )
    elapsed = time.perf_counter() - start
    check("9. 복합 필터(날짜+구분+카테고리) 조회", len(combined) > 0 and elapsed < MAX_SECONDS, elapsed)

    # 10. 요약 집계(총수입/총지출)
    start = time.perf_counter()
    summary = transaction_service.get_summary()
    elapsed = time.perf_counter() - start
    check("10. 전체 요약 집계(총수입/총지출)", summary["count"] == N_TRANSACTIONS and elapsed < MAX_SECONDS, elapsed)

    # 11. 대시보드 전체 데이터 조회(기간 지정)
    start = time.perf_counter()
    dashboard_data = dashboard_service.get_dashboard_data(date(2020, 1, 1), date(2020, 12, 31))
    elapsed = time.perf_counter() - start
    check("11. 대시보드 데이터 조회(1년치, 차트 4개 포함)", dashboard_data["summary"]["count"] > 0 and elapsed < MAX_SECONDS, elapsed)

    # 12. 회계구분 요약 집계
    start = time.perf_counter()
    accounting_summary = transaction_service.get_accounting_summary()
    elapsed = time.perf_counter() - start
    check("12. 회계구분(매출/비용) 요약 집계", accounting_summary["total_revenue"] > 0 and elapsed < MAX_SECONDS, elapsed)

    print()
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"결과: {passed}/{total} 통과")
    print(f"(참고: 1만 건 생성 자체는 {gen_elapsed:.1f}초 소요 - 실사용에서는 한 번에 발생하지 않는 시나리오)")

    TEMP_DB_PATH.unlink(missing_ok=True)
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

"""7단계(대시보드 '매출' 차트에서 매출이 아닌 입금 제외) 검증 스크립트.

실행 방법:
    python tests/test_stage7.py

"업무유형별 매출" / "거래처별 매출 TOP 10" 차트는 통장 입금 중 회계구분이 '매출' 또는
'미분류'인 거래만 합산해야 한다. 대표자 가수금(비매출입금), 계좌 간 이체(자금이동) 등은
빠져야 하고, 통장 기준 총수입·월별 추이는 그대로(모든 입금 포함) 유지되어야 한다.

실제 data/finance.db는 절대 건드리지 않고 tests/ 아래 임시 DB(_stage7_test.db)만 사용한다.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.database as database  # noqa: E402

TEMP_DB_PATH = Path(__file__).resolve().parent / "_stage7_test.db"
if TEMP_DB_PATH.exists():
    TEMP_DB_PATH.unlink()
database.DB_PATH = TEMP_DB_PATH

from db.database import init_db  # noqa: E402
from services import client_service, dashboard_service, transaction_service, work_type_service  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def main() -> bool:
    init_db()
    work_type_id = work_type_service.get_work_types()[0]["id"]
    work_type_name = work_type_service.get_work_types()[0]["name"]
    client_id = client_service.create_client("테스트고객사", None, None, None)

    def income(amount: int, accounting_type: str, with_refs: bool = True) -> None:
        transaction_service.create_transaction(
            transaction_date="2026-06-10",
            transaction_type="income",
            description=f"입금 {accounting_type}",
            amount=amount,
            client_id=client_id if with_refs else None,
            work_type_id=work_type_id if with_refs else None,
            accounting_type=accounting_type,
        )

    income(500_000, "매출")
    income(30_000, "미분류")
    income(1_000_000, "비매출입금")  # 대표자 가수금
    income(2_000_000, "자금이동")  # 다른 계좌에서 옮겨온 돈
    income(7_000, "비용")  # 비용 환급 등 매출이 아닌 입금
    income(1_000_000, "비매출입금", with_refs=False)  # 거래처/업무유형 없는 가수금 -> '미분류' 막대에도 안 들어가야 함

    data = dashboard_service.get_dashboard_data(date(2026, 6, 1), date(2026, 6, 30))
    by_work_type = {r["work_type_name"]: r["total"] for r in data["income_by_work_type"]}
    by_client = {r["client_name"]: r["total"] for r in data["income_by_client"]}

    check("1. 업무유형별 매출: 매출 + 미분류 입금만 합산", by_work_type.get(work_type_name) == 530_000)
    check("2. 거래처별 매출: 매출 + 미분류 입금만 합산", by_client.get("테스트고객사") == 530_000)
    check("3. 거래처 없는 가수금은 '미분류' 막대로도 들어가지 않음",
          "미분류" not in by_client and "미분류" not in by_work_type)
    check("4. 차트 전체 합계에 가수금·자금이동·비용 입금이 없음",
          sum(by_client.values()) == 530_000 and sum(by_work_type.values()) == 530_000)

    summary = data["summary"]
    check("5. 통장 기준 총수입은 모든 입금 그대로 포함(잔액과 일치해야 함)",
          summary["total_income"] == 500_000 + 30_000 + 1_000_000 + 2_000_000 + 7_000 + 1_000_000)
    check("6. 월별 추이(통장 입금)도 모든 입금 포함",
          data["monthly_trend"][0]["income"] == summary["total_income"])
    check("7. 총매출(회계구분 기준)은 '매출'만 합산", data["accounting_summary"]["total_revenue"] == 500_000)

    # 가수금만 있는 기간이면 매출 차트는 비어야 한다 (오류 없이)
    transaction_service.create_transaction(
        transaction_date="2026-07-05", transaction_type="income", description="대표자가수금",
        amount=3_000_000, accounting_type="비매출입금",
    )
    july = dashboard_service.get_dashboard_data(date(2026, 7, 1), date(2026, 7, 31))
    check("8. 가수금만 있는 기간은 매출 차트가 빈 목록(오류 없음)",
          july["income_by_work_type"] == [] and july["income_by_client"] == [])
    check("9. 그 기간에도 총수입(통장 기준)에는 가수금이 포함됨", july["summary"]["total_income"] == 3_000_000)

    real_db_path = Path(__file__).resolve().parent.parent / "data" / "finance.db"
    check("10. 실제 data/finance.db는 생성/변경되지 않음", database.DB_PATH == TEMP_DB_PATH and not real_db_path.exists())

    print()
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"결과: {passed}/{total} 통과")

    TEMP_DB_PATH.unlink(missing_ok=True)
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

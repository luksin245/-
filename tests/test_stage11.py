"""11단계(체크한 거래 한꺼번에 수정 / 자동분류 규칙 삭제) 검증 스크립트.

실행 방법:
    python tests/test_stage11.py

실제 data/finance.db는 절대 건드리지 않고 tests/ 아래 임시 DB만 사용한 뒤 종료 시 삭제한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.database as database  # noqa: E402

TEMP_DB_PATH = Path(__file__).resolve().parent / "_stage11_test.db"
if TEMP_DB_PATH.exists():
    TEMP_DB_PATH.unlink()
database.DB_PATH = TEMP_DB_PATH

from db.database import init_db  # noqa: E402
from services import (  # noqa: E402
    account_service,
    category_rule_service,
    category_service,
    client_service,
    transaction_service,
)
from utils.validators import ValidationError  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def expect_error(name: str, fn, must_contain: str = "") -> None:
    try:
        fn()
        check(name, False)
    except ValidationError as e:
        check(name, must_contain in str(e))


def main() -> bool:
    init_db()
    accounts = {a["name"]: a["id"] for a in account_service.get_accounts()}
    expense_cat = category_service.get_expense_categories()[0]
    income_cat = category_service.get_income_categories()[0]
    client_id = client_service.get_or_create_client("가짜노무법인")

    def tx(kind, desc, amount, **kw):
        return transaction_service.create_transaction(
            transaction_date="2026-09-10", transaction_type=kind, description=desc, amount=amount, **kw
        )

    e1 = tx("expense", "BZ뱅크 노무법인돋움", 70_400, memo="원래 메모")
    e2 = tx("expense", "FB자동 노무법인돋움", 192_500, account_id=accounts.get("지급수수료"))
    i1 = tx("income", "FB자금 CMS집금", 329_725)

    # ---------------- 한꺼번에 수정 ----------------
    fee_account = next(iter(accounts.values()))
    updated = transaction_service.bulk_update_transactions(
        [e1, e2],
        {"accounting_type": "비용", "vat_status": "과세", "client_id": client_id, "account_id": fee_account,
         "category_id": expense_cat["id"]},
    )
    a, b = transaction_service.get_transaction(e1), transaction_service.get_transaction(e2)
    check("1. 체크한 2건의 분류를 한꺼번에 바꿈",
          updated == 2 and all(t["accounting_type"] == "비용" and t["vat_status"] == "과세"
                               and t["client_id"] == client_id and t["account_id"] == fee_account
                               and t["category_id"] == expense_cat["id"] for t in (a, b)))
    check("2. 고르지 않은 항목(증빙·메모)과 금액·날짜·거래내용은 그대로",
          a["memo"] == "원래 메모" and a["evidence_status"] == "확인필요" and a["amount"] == 70_400
          and b["description"] == "FB자동 노무법인돋움" and b["transaction_date"] == "2026-09-10")
    check("3. 다른 거래는 건드리지 않음", transaction_service.get_transaction(i1)["accounting_type"] == "미분류")

    transaction_service.bulk_update_transactions([e1, e2], {"client_id": None, "account_id": None})
    a = transaction_service.get_transaction(e1)
    check("4. '(비우기)'로 거래처·계정과목을 비울 수 있음", a["client_id"] is None and a["account_id"] is None
          and a["accounting_type"] == "비용")

    expect_error("5. 수입·지출이 섞이면 카테고리 일괄 변경 거부",
                 lambda: transaction_service.bulk_update_transactions([e1, i1], {"category_id": expense_cat["id"]}),
                 "섞여")
    expect_error("6. 지출 거래에 수입 카테고리 거부",
                 lambda: transaction_service.bulk_update_transactions([e1, e2], {"category_id": income_cat["id"]}))
    check("7. 수입·지출이 섞여도 카테고리 말고 다른 항목은 가능",
          transaction_service.bulk_update_transactions([e1, i1], {"evidence_status": "있음"}) == 2)
    expect_error("8. 잘못된 회계구분 거부",
                 lambda: transaction_service.bulk_update_transactions([e1], {"accounting_type": "경비"}))
    expect_error("9. 바꿀 항목이 없으면 거부",
                 lambda: transaction_service.bulk_update_transactions([e1], {}), "하나 이상")
    expect_error("10. 금액 같은 원본 값은 일괄 변경 대상이 아님",
                 lambda: transaction_service.bulk_update_transactions([e1], {"amount": 1}), "하나 이상")
    expect_error("11. 선택 없음 거부", lambda: transaction_service.bulk_update_transactions([], {"vat_status": "과세"}))
    expect_error("12. 없는 거래가 섞이면 거부(아무것도 안 바뀜)",
                 lambda: transaction_service.bulk_update_transactions([e1, 999_999], {"vat_status": "면세"}), "찾을 수 없는")
    check("12-보조. 거부됐을 때 기존 값 유지", transaction_service.get_transaction(e1)["vat_status"] == "과세")

    client_service.deactivate_client(client_id)
    expect_error("13. 비활성 거래처는 새로 지정 불가",
                 lambda: transaction_service.bulk_update_transactions([e1], {"client_id": client_id}), "비활성")

    # ---------------- 자동분류 규칙 삭제 ----------------
    r1 = category_rule_service.create_rule(keyword="CMS사용료", suggested_vat_status="과세")
    r2 = category_rule_service.create_rule(keyword="노무법인", suggested_accounting_type="비용")
    r3 = category_rule_service.create_rule(keyword="이자", suggested_vat_status="해당없음")
    deleted = category_rule_service.delete_rules([r1, r2])
    remaining = {r["id"] for r in category_rule_service.list_rules(status="all")}
    check("14. 체크한 규칙 2개 삭제 (나머지는 그대로)", deleted == 2 and remaining == {r3})
    check("15. 삭제한 규칙은 더 이상 추천에 쓰이지 않음", category_rule_service.suggest_for("FB자동 CMS사용료", None) is None)
    check("16. 삭제 후 같은 키워드로 다시 등록 가능",
          category_rule_service.create_rule(keyword="CMS사용료", suggested_vat_status="과세") > 0)
    check("17. 규칙을 지워도 거래는 그대로", transaction_service.get_transaction(e1) is not None)
    expect_error("18. 선택 없이 삭제 거부", lambda: category_rule_service.delete_rules([]))

    real_db_path = Path(__file__).resolve().parent.parent / "data" / "finance.db"
    check("19. 실제 data/finance.db는 생성/변경되지 않음", not real_db_path.exists())

    print()
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"결과: {passed}/{total} 통과")
    TEMP_DB_PATH.unlink(missing_ok=True)
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

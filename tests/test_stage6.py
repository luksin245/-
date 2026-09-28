"""6단계(거래 여러 건 한꺼번에 삭제) 검증 스크립트.

실행 방법:
    python tests/test_stage6.py

다른 단계 테스트와 동일하게 실제 data/finance.db는 절대 건드리지 않고,
tests/ 폴더 아래 임시 DB 파일(_stage6_test.db)과 그에 딸린 backups/temp 폴더만
사용한 뒤 종료 시 모두 삭제한다.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.database as database  # noqa: E402

TEMP_DB_PATH = Path(__file__).resolve().parent / "_stage6_test.db"
BACKUP_DIR = TEMP_DB_PATH.parent / "backups"
TEMP_DIR = TEMP_DB_PATH.parent / "temp"
if TEMP_DB_PATH.exists():
    TEMP_DB_PATH.unlink()
shutil.rmtree(BACKUP_DIR, ignore_errors=True)
shutil.rmtree(TEMP_DIR, ignore_errors=True)
database.DB_PATH = TEMP_DB_PATH

from db.database import init_db  # noqa: E402
from db import ocr_repository  # noqa: E402
from services import backup_service, import_service, transaction_service  # noqa: E402
from utils.validators import ValidationError  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def _make(desc: str, tx_type: str = "expense", amount: int = 10_000, date: str = "2026-09-10") -> int:
    return transaction_service.create_transaction(
        transaction_date=date, transaction_type=tx_type, description=desc, amount=amount
    )


def main() -> bool:
    init_db()

    keep_id = _make("남길 거래")
    delete_ids = [_make(f"지울 거래 {i}") for i in range(3)]

    # 1. 여러 건 한꺼번에 삭제
    result = transaction_service.delete_transactions(delete_ids)
    remaining_ids = {t["id"] for t in transaction_service.list_transactions()}
    check("1. 선택한 거래만 모두 삭제됨", not (set(delete_ids) & remaining_ids))
    check("2. 선택하지 않은 거래는 그대로 남음", keep_id in remaining_ids)
    check("3. 실제 삭제 건수를 정확히 반환", result["deleted"] == 3)

    # 4~5. 삭제 직전 자동 백업
    backup_path = BACKUP_DIR / result["backup_filename"]
    check("4. 삭제 직전 자동 백업 파일이 생성됨", backup_path.exists() and backup_path.name.startswith("pre_bulk_delete"))
    conn = sqlite3.connect(backup_path)
    try:
        backed_up = conn.execute(
            f"SELECT COUNT(*) FROM transactions WHERE id IN ({','.join('?' for _ in delete_ids)})", delete_ids
        ).fetchone()[0]
    finally:
        conn.close()
    check("5. 자동 백업에는 삭제된 거래가 그대로 들어 있음", backed_up == 3)

    # 6. 자동 백업으로 복구하면 삭제한 거래가 되돌아옴
    backup_service.restore_backup(result["backup_filename"])
    restored_ids = {t["id"] for t in transaction_service.list_transactions()}
    check("6. 자동 백업으로 복구하면 삭제 전 상태로 되돌아옴", set(delete_ids) <= restored_ids)

    # 7~9. 잘못된 입력
    try:
        transaction_service.delete_transactions([])
        check("7. 아무것도 선택하지 않으면 거부", False)
    except ValidationError:
        check("7. 아무것도 선택하지 않으면 거부", True)

    backups_before = len(backup_service.list_backups())
    try:
        transaction_service.delete_transactions([999_999])
        check("8. 존재하지 않는 거래만 선택하면 거부", False)
    except ValidationError:
        check("8. 존재하지 않는 거래만 선택하면 거부", True)
    check("9. 거부된 경우에는 불필요한 백업을 만들지 않음", len(backup_service.list_backups()) == backups_before)

    # 10. 같은 id가 중복으로 넘어와도 한 번만 처리
    dup_id = _make("중복 선택 거래")
    dup_result = transaction_service.delete_transactions([dup_id, dup_id])
    check("10. 같은 거래를 중복 선택해도 1건으로 처리", dup_result["deleted"] == 1)

    # 11~13. OCR로 저장한 거래 (문서에 아직 검토 안 끝난 줄이 남아 있는 상태)
    with open(FIXTURES_DIR / "fake_bank_table_statement.pdf", "rb") as f:
        pdf_bytes = f.read()
    doc_id = import_service.process_uploaded_file(pdf_bytes, "fake_bank_table_statement.pdf")
    lines = import_service.get_review_lines(doc_id)
    ocr_tx_ids = []
    for line in lines:
        if line["status"] != "정상":
            continue
        ocr_tx_ids.append(
            import_service.confirm_line(
                line["id"], line["raw_income"], line["raw_expense"],
                {"transaction_date": line["raw_date"], "description": line["raw_description"]},
            )
        )
    doc_still_open = any(d["id"] == doc_id for d in import_service.list_documents())
    check("11. (전제) 확인필요 줄이 남아 있어 문서가 아직 검토 대기 상태", doc_still_open and len(ocr_tx_ids) == 5)

    single_target = ocr_tx_ids.pop()
    try:
        transaction_service.delete_transaction(single_target)
        check("12. OCR로 저장한 거래도 한 건 삭제가 정상 동작", transaction_service.get_transaction(single_target) is None)
    except Exception:
        check("12. OCR로 저장한 거래도 한 건 삭제가 정상 동작", False)

    try:
        ocr_result = transaction_service.delete_transactions(ocr_tx_ids)
        check("13. OCR로 저장한 거래도 여러 건 한꺼번에 삭제 가능", ocr_result["deleted"] == len(ocr_tx_ids))
    except Exception:
        check("13. OCR로 저장한 거래도 여러 건 한꺼번에 삭제 가능", False)

    pending = [l for l in import_service.get_review_lines(doc_id) if not l["is_confirmed"]]
    check("14. 거래를 지워도 아직 검토 안 한 줄은 검토 화면에 그대로 남음", len(pending) == 1)
    confirmed_links = [
        ocr_repository.get_raw_line_by_id(l["id"])["linked_transaction_id"]
        for l in import_service.get_review_lines(doc_id) if l["is_confirmed"]
    ]
    check("15. 지운 거래를 가리키던 연결은 비워짐(깨진 참조 없음)", all(link is None for link in confirmed_links))

    real_db_path = Path(__file__).resolve().parent.parent / "data" / "finance.db"
    check("16. 실제 data/finance.db는 생성/변경되지 않음", database.DB_PATH == TEMP_DB_PATH and not real_db_path.exists())

    print()
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"결과: {passed}/{total} 통과")

    TEMP_DB_PATH.unlink(missing_ok=True)
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

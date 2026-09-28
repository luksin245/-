"""통장 파일 업로드 -> OCR -> 검토 -> 확정 전체 흐름을 조율하는 서비스.

개인정보/금융정보 보호를 위해, 업로드된 원본 파일(이미지/PDF)은 OCR 처리
직후 즉시 삭제하고 장기 보관하지 않는다. OCR로 추출한 거래 후보만
ocr_documents/ocr_raw_lines에 남아 있다가, 사용자가 검토 화면에서
확정(또는 취소)하면 그 결과에 따라 정리된다.

이 계층은 절대 후보를 자동으로 transactions에 확정 저장하지 않는다 -
반드시 사용자가 검토 화면에서 명시적으로 저장을 눌러야 한다.
"""
import uuid
from datetime import datetime
from pathlib import Path

from db import database, ocr_repository as repo
from services import category_rule_service, dedup_service, transaction_service
from services.ocr.base import STATUS_SUSPECTED_DUPLICATE
from services.ocr.local_ocr import LocalOCREngine
from utils.validators import ValidationError

ALLOWED_FILE_TYPES = ("png", "jpg", "jpeg", "pdf")

_ocr_engine = LocalOCREngine()


def _get_temp_dir() -> Path:
    temp_dir = database.DB_PATH.parent / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def _detect_file_type(original_filename: str) -> str:
    ext = Path(original_filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_FILE_TYPES:
        raise ValidationError(
            f"지원하지 않는 파일 형식입니다: {original_filename} "
            "(PNG/JPG/JPEG/PDF 파일만 업로드할 수 있습니다.)"
        )
    return ext


def process_uploaded_file(file_bytes: bytes, original_filename: str) -> int:
    """업로드된 파일 1개를 OCR 처리하고, 결과 후보들을 ocr_raw_lines에 저장한다.

    반환값은 새로 생성된 ocr_documents.id. 원본 파일은 이 함수가 끝나기 전에
    (성공하든 실패하든) 반드시 삭제된다.
    """
    file_type = _detect_file_type(original_filename)
    temp_dir = _get_temp_dir()
    temp_path = temp_dir / f"{uuid.uuid4().hex}.{file_type}"

    try:
        with open(temp_path, "wb") as f:
            f.write(file_bytes)

        candidates = _ocr_engine.extract_candidates(str(temp_path), file_type)
    finally:
        # 개인정보 보호: OCR 처리 결과와 무관하게 원본 파일은 즉시 삭제한다.
        temp_path.unlink(missing_ok=True)

    document_id = repo.insert_document(
        file_name=original_filename,
        file_type=file_type,
        uploaded_at=datetime.now().isoformat(timespec="seconds"),
    )
    repo.set_document_status(document_id, "ocr_done")

    for line_no, candidate in enumerate(candidates, start=1):
        suggestion = category_rule_service.suggest_for(candidate.get("description"), None)
        match_type = dedup_service.check_duplicate(candidate)

        status = candidate["status"]
        if match_type is not None:
            # 중복 의심은 OCR 자체 판정(정상/확인필요)보다 우선해 사용자에게 보여준다.
            status = STATUS_SUSPECTED_DUPLICATE

        repo.insert_raw_line(
            {
                "document_id": document_id,
                "line_no": line_no,
                "raw_date": candidate.get("date"),
                "raw_time": candidate.get("time"),
                "raw_description": candidate.get("description"),
                "raw_income": candidate.get("income"),
                "raw_expense": candidate.get("expense"),
                "raw_balance": candidate.get("balance"),
                "confidence": candidate.get("confidence"),
                "status": status,
                "suggested_category_id": suggestion["category_id"] if suggestion else None,
                "suggested_client_id": suggestion["client_id"] if suggestion else None,
                "suggested_work_type_id": suggestion["work_type_id"] if suggestion else None,
                "suggested_account_id": suggestion["account_id"] if suggestion else None,
                "suggested_accounting_type": suggestion["accounting_type"] if suggestion else None,
            }
        )

    return document_id


def list_documents() -> list[dict]:
    """아직 검토가 끝나지 않은(전부 확정/취소되지 않은) 업로드 문서 목록.

    검토가 모두 끝난 문서는 확정/취소 시점에 정리되어 목록에서 사라진다.
    """
    return repo.get_documents()


def get_review_lines(document_id: int) -> list[dict]:
    return repo.get_raw_lines_with_names(document_id)


def _cleanup_if_resolved(document_id: int) -> None:
    if repo.count_unresolved_lines(document_id) == 0:
        repo.delete_document(document_id)


def confirm_line(
    line_id: int,
    income: int | None,
    expense: int | None,
    transaction_data: dict,
    rule_id: int | None = None,
) -> int:
    """검토 화면에서 사용자가 확정한 값으로 실제 거래를 생성하고 후보를 확정 처리한다.

    income/expense는 검토 화면에 표시된 최종 값 그대로 전달해야 한다 - 이 함수가
    직접 "동시에 있거나 둘 다 없으면 안 된다"는 규칙을 검증하므로, 호출하는 쪽(UI)이
    이 검증을 대신 수행할 필요가 없다 (서비스 계층에서 한 번 더 확실히 막는다).

    transaction_data는 services.transaction_service.create_transaction에 그대로
    전달할 나머지 키(transaction_date, description, category_id 등 - transaction_type/amount 제외)를
    담은 dict여야 한다.
    """
    line = repo.get_raw_line_by_id(line_id)
    if line is None:
        raise ValidationError("존재하지 않는 검토 항목입니다.")

    if income is not None and expense is not None:
        raise ValidationError("입금액과 출금액을 동시에 입력할 수 없습니다. 하나만 남겨주세요.")
    if income is None and expense is None:
        raise ValidationError("입금액 또는 출금액 중 하나는 반드시 입력해야 합니다.")

    transaction_type = "income" if income is not None else "expense"
    amount = income if income is not None else expense

    transaction_id = transaction_service.create_transaction(
        transaction_type=transaction_type, amount=amount, source_type="ocr", **transaction_data
    )
    repo.mark_line_confirmed(line_id, transaction_id)

    if rule_id is not None:
        category_rule_service.record_suggestion_used(rule_id)

    _cleanup_if_resolved(line["document_id"])
    return transaction_id


def discard_line(line_id: int) -> None:
    """검토 화면에서 사용자가 이 후보를 저장하지 않기로 결정했을 때 삭제한다."""
    line = repo.get_raw_line_by_id(line_id)
    if line is None:
        return
    document_id = line["document_id"]
    repo.delete_raw_line(line_id)
    _cleanup_if_resolved(document_id)


def discard_document(document_id: int) -> None:
    """문서 전체(아직 확정하지 않은 후보 전부 포함)를 취소한다."""
    repo.delete_document(document_id)

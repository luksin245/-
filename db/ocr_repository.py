"""OCR 업로드 문서(ocr_documents) 및 검토 전 거래 후보(ocr_raw_lines) 접근 계층.

OCR 결과는 이 테이블들에만 머무르고, 사용자가 검토/확정한 뒤에만
services.transaction_service를 통해 transactions로 옮겨진다.
"""
from db.database import get_connection


def insert_document(file_name: str, file_type: str, uploaded_at: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO ocr_documents (file_name, file_type, uploaded_at, status) "
            "VALUES (?, ?, ?, 'uploaded')",
            (file_name, file_type, uploaded_at),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def set_document_status(document_id: int, status: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE ocr_documents SET status = ? WHERE id = ?", (status, document_id))
        conn.commit()
    finally:
        conn.close()


def get_document_by_id(document_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ocr_documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_documents(status: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        query = "SELECT * FROM ocr_documents"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY uploaded_at DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_document(document_id: int) -> None:
    """문서와 그에 딸린 raw_lines를 모두 지운다 (확정/취소 후 정리용)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM ocr_raw_lines WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM ocr_documents WHERE id = ?", (document_id,))
        conn.commit()
    finally:
        conn.close()


def insert_raw_line(data: dict) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO ocr_raw_lines (
                document_id, line_no, raw_date, raw_time, raw_description,
                raw_income, raw_expense, raw_balance, confidence, status,
                suggested_category_id, suggested_client_id, suggested_work_type_id,
                suggested_account_id, suggested_accounting_type,
                is_confirmed, linked_transaction_id
            ) VALUES (
                :document_id, :line_no, :raw_date, :raw_time, :raw_description,
                :raw_income, :raw_expense, :raw_balance, :confidence, :status,
                :suggested_category_id, :suggested_client_id, :suggested_work_type_id,
                :suggested_account_id, :suggested_accounting_type,
                0, NULL
            )
            """,
            {
                "suggested_account_id": None,
                "suggested_accounting_type": None,
                **data,
            },
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_raw_lines(document_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM ocr_raw_lines WHERE document_id = ? ORDER BY line_no", (document_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_raw_lines_with_names(document_id: int) -> list[dict]:
    """검토 화면 표시용 - 추천된 카테고리/거래처/업무유형/계정과목 이름까지 함께 조회한다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                l.*,
                c.name AS suggested_category_name,
                cl.name AS suggested_client_name,
                w.name AS suggested_work_type_name,
                a.name AS suggested_account_name
            FROM ocr_raw_lines l
            LEFT JOIN categories c ON l.suggested_category_id = c.id
            LEFT JOIN clients cl ON l.suggested_client_id = cl.id
            LEFT JOIN work_types w ON l.suggested_work_type_id = w.id
            LEFT JOIN chart_of_accounts a ON l.suggested_account_id = a.id
            WHERE l.document_id = ?
            ORDER BY l.line_no
            """,
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_raw_line_by_id(line_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ocr_raw_lines WHERE id = ?", (line_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_raw_line_fields(line_id: int, data: dict) -> None:
    """사용자가 검토 화면에서 원시값(날짜/시간/내용/금액)을 직접 수정했을 때 갱신한다.

    카테고리/거래처/업무유형/계정과목/회계구분 등 사용자의 최종 선택값은 이
    테이블에 별도로 저장하지 않는다 - 검토 화면에서 저장 버튼을 누르는 즉시
    services.transaction_service.create_transaction으로 바로 넘어가 실제
    거래로 확정되기 때문이다 (중간 상태를 별도로 영속화할 필요가 없다).
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE ocr_raw_lines SET
                raw_date = :raw_date, raw_time = :raw_time, raw_description = :raw_description,
                raw_income = :raw_income, raw_expense = :raw_expense, raw_balance = :raw_balance,
                status = :status
            WHERE id = :id
            """,
            {**data, "id": line_id},
        )
        conn.commit()
    finally:
        conn.close()


def set_raw_line_status(line_id: int, status: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE ocr_raw_lines SET status = ? WHERE id = ?", (status, line_id))
        conn.commit()
    finally:
        conn.close()


def mark_line_confirmed(line_id: int, transaction_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE ocr_raw_lines SET is_confirmed = 1, linked_transaction_id = ? WHERE id = ?",
            (transaction_id, line_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_raw_line(line_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM ocr_raw_lines WHERE id = ?", (line_id,))
        conn.commit()
    finally:
        conn.close()


def count_unresolved_lines(document_id: int) -> int:
    """아직 확정 저장되지 않은(is_confirmed=0) 줄 개수."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM ocr_raw_lines WHERE document_id = ? AND is_confirmed = 0",
            (document_id,),
        ).fetchone()[0]
    finally:
        conn.close()

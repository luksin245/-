"""transactions 테이블에 대한 순수 SQL 접근 계층.

이 모듈은 검증이나 비즈니스 로직을 갖지 않는다.
검증/기본값 처리는 services.transaction_service에서 담당한다.
"""
from db.database import get_connection


def _build_filter_clause(filters: dict | None) -> tuple[str, list]:
    """조회 필터 dict를 WHERE 절과 파라미터 목록으로 변환한다.

    get_transactions()와 get_transaction_summary()가 동일한 조건으로
    조회/집계하도록 로직을 공유한다 (필터링은 pandas가 아닌 DB 쿼리에서 수행).
    """
    filters = filters or {}
    clauses = []
    params: list = []

    if filters.get("start_date"):
        clauses.append("t.transaction_date >= ?")
        params.append(filters["start_date"])
    if filters.get("end_date"):
        clauses.append("t.transaction_date <= ?")
        params.append(filters["end_date"])
    if filters.get("transaction_type"):
        clauses.append("t.transaction_type = ?")
        params.append(filters["transaction_type"])
    if filters.get("category_id"):
        clauses.append("t.category_id = ?")
        params.append(filters["category_id"])
    if filters.get("client_id"):
        clauses.append("t.client_id = ?")
        params.append(filters["client_id"])
    if filters.get("work_type_id"):
        clauses.append("t.work_type_id = ?")
        params.append(filters["work_type_id"])
    if filters.get("account_id"):
        clauses.append("t.account_id = ?")
        params.append(filters["account_id"])
    if filters.get("accounting_type"):
        clauses.append("t.accounting_type = ?")
        params.append(filters["accounting_type"])
    if filters.get("evidence_status"):
        clauses.append("t.evidence_status = ?")
        params.append(filters["evidence_status"])
    if filters.get("keyword"):
        keyword = filters["keyword"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("t.description LIKE ? ESCAPE '\\'")
        params.append(f"%{keyword}%")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


_JOIN_SQL = """
    LEFT JOIN categories c ON t.category_id = c.id
    LEFT JOIN clients cl ON t.client_id = cl.id
    LEFT JOIN work_types w ON t.work_type_id = w.id
    LEFT JOIN chart_of_accounts a ON t.account_id = a.id
"""


def insert_transaction(data: dict) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO transactions (
                transaction_date, transaction_time, description, transaction_type,
                amount, balance, category_id, client_id, work_type_id,
                account_id, accounting_type,
                vat_status, evidence_status, memo, source_type, created_at, updated_at
            ) VALUES (
                :transaction_date, :transaction_time, :description, :transaction_type,
                :amount, :balance, :category_id, :client_id, :work_type_id,
                :account_id, :accounting_type,
                :vat_status, :evidence_status, :memo, :source_type, :created_at, :updated_at
            )
            """,
            data,
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_all_transactions() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def count_transactions() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    finally:
        conn.close()


def delete_transaction(transaction_id: int) -> None:
    delete_transactions([transaction_id])


# SQLite 버전에 따라 한 문장에 넣을 수 있는 ? 개수 제한이 999개인 경우가 있어 나눠서 처리한다.
_ID_CHUNK_SIZE = 500


def _chunks(ids: list[int]) -> list[list[int]]:
    return [ids[i:i + _ID_CHUNK_SIZE] for i in range(0, len(ids), _ID_CHUNK_SIZE)]


def find_expenses_by_amount(amount: int, date_from: str, date_to: str) -> list[dict]:
    """금액이 정확히 같은 출금 거래를 기간 내에서 찾는다 (카드 명세서 ↔ 카드결 출금 맞춰보기용)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT t.*, cl.name AS client_name, a.name AS account_name
            FROM transactions t
            LEFT JOIN clients cl ON t.client_id = cl.id
            LEFT JOIN chart_of_accounts a ON t.account_id = a.id
            WHERE t.transaction_type = 'expense' AND t.amount = ?
              AND t.transaction_date BETWEEN ? AND ?
            ORDER BY t.transaction_date, t.id
            """,
            (amount, date_from, date_to),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_accounting_classification(
    transaction_id: int, accounting_type: str, account_id: int | None, updated_at: str, vat_status: str | None = None
) -> None:
    """회계구분/계정과목을 바꾼다. vat_status를 주면 부가세 여부도 함께 바꾼다."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE transactions SET accounting_type = ?, account_id = ?, "
            "vat_status = COALESCE(?, vat_status), updated_at = ? WHERE id = ?",
            (accounting_type, account_id, vat_status, updated_at, transaction_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_unknown_vat_transactions() -> list[dict]:
    """부가세 여부가 아직 '불명'인 모든 거래 (부가세 정리 화면의 추천 확인용)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT t.*, cl.name AS client_name, a.name AS account_name
            FROM transactions t
            LEFT JOIN clients cl ON t.client_id = cl.id
            LEFT JOIN chart_of_accounts a ON t.account_id = a.id
            WHERE t.vat_status = '불명'
            ORDER BY t.transaction_date, t.transaction_time, t.id
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_decided_vat_history() -> list[dict]:
    """부가세 여부를 이미 정한(불명이 아닌) 거래들. 오래된 것부터 - 뒤에 나온 값이 최근 결정이다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT description, client_id, vat_status FROM transactions "
            "WHERE vat_status <> '불명' ORDER BY updated_at, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_vat_relevant_rows(start_date: str, end_date: str) -> list[dict]:
    """부가세 집계용: 기간 내 '과세' 거래와, 아직 '불명'인 매출·비용 거래의 최소 정보만 가져온다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT transaction_type, accounting_type, vat_status, amount
            FROM transactions
            WHERE transaction_date BETWEEN ? AND ?
              AND (vat_status = '과세' OR (vat_status = '불명' AND accounting_type IN ('매출', '비용')))
            """,
            (start_date, end_date),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_vat_statuses(updates: list[dict]) -> int:
    """여러 거래의 부가세 여부만 한 번에 바꾼다 (다른 값은 건드리지 않음). updates: [{id, vat_status, updated_at}]"""
    conn = get_connection()
    try:
        cursor = conn.executemany(
            "UPDATE transactions SET vat_status = :vat_status, updated_at = :updated_at WHERE id = :id",
            updates,
        )
        conn.commit()
        return cursor.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_transaction_types(transaction_ids: list[int]) -> set[str]:
    """선택한 거래들의 수입/지출 구분 종류 (카테고리 일괄 변경 가능 여부 확인용)."""
    conn = get_connection()
    try:
        types: set[str] = set()
        for chunk in _chunks(transaction_ids):
            placeholders = ",".join("?" for _ in chunk)
            types |= {
                r[0] for r in conn.execute(
                    f"SELECT DISTINCT transaction_type FROM transactions WHERE id IN ({placeholders})", chunk
                )
            }
        return types
    finally:
        conn.close()


# 여러 거래를 한꺼번에 바꿀 수 있는 분류 항목 (금액·날짜·거래내용 같은 원본 값은 제외)
BULK_EDITABLE_COLUMNS = (
    "category_id", "client_id", "work_type_id", "account_id", "accounting_type", "vat_status", "evidence_status",
)


def bulk_update_fields(transaction_ids: list[int], changes: dict, updated_at: str) -> int:
    """여러 거래의 분류 항목을 한 DB 트랜잭션으로 같은 값으로 바꾼다. 바뀐 건수를 반환한다."""
    columns = [c for c in changes if c in BULK_EDITABLE_COLUMNS]
    if not columns:
        return 0
    set_sql = ", ".join(f"{c} = ?" for c in columns) + ", updated_at = ?"
    values = [changes[c] for c in columns] + [updated_at]
    conn = get_connection()
    try:
        updated = 0
        for chunk in _chunks(transaction_ids):
            placeholders = ",".join("?" for _ in chunk)
            cursor = conn.execute(f"UPDATE transactions SET {set_sql} WHERE id IN ({placeholders})", values + chunk)
            updated += cursor.rowcount
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_existing_transactions(transaction_ids: list[int]) -> int:
    conn = get_connection()
    try:
        total = 0
        for chunk in _chunks(transaction_ids):
            placeholders = ",".join("?" for _ in chunk)
            total += conn.execute(
                f"SELECT COUNT(*) FROM transactions WHERE id IN ({placeholders})", chunk
            ).fetchone()[0]
        return total
    finally:
        conn.close()


def delete_transactions(transaction_ids: list[int]) -> int:
    """여러 거래를 한 번의 DB 트랜잭션으로 삭제하고 실제 삭제된 건수를 반환한다.

    OCR 검토 화면에서 저장된 거래는 ocr_raw_lines.linked_transaction_id가 가리키고
    있어서(문서에 아직 검토 안 끝난 줄이 남아 있으면 그 행도 남아 있음), 먼저
    그 연결을 끊지 않으면 외래키 제약 때문에 삭제가 실패한다.
    중간에 오류가 나면 전부 되돌려서 일부만 지워지는 일이 없게 한다.
    """
    conn = get_connection()
    try:
        deleted = 0
        for chunk in _chunks(transaction_ids):
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(
                f"UPDATE ocr_raw_lines SET linked_transaction_id = NULL "
                f"WHERE linked_transaction_id IN ({placeholders})",
                chunk,
            )
            # 카드 명세서와 연결된 카드결 출금을 지우는 경우에도 같은 이유로 연결을 먼저 끊는다.
            conn.execute(
                f"UPDATE card_statements SET settlement_transaction_id = NULL "
                f"WHERE settlement_transaction_id IN ({placeholders})",
                chunk,
            )
            cursor = conn.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", chunk)
            deleted += cursor.rowcount
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_transactions(filters: dict | None = None, limit: int | None = None) -> list[dict]:
    """카테고리/거래처/업무유형/계정과목 이름까지 JOIN하여 조회한다.

    기본 정렬: 거래일자 내림차순 -> 거래시간 내림차순 -> id 내림차순.
    limit을 주면 DB 쿼리 단계에서 앞의 N건만 가져온다 (예: 대시보드 최근 거래).
    """
    where_sql, params = _build_filter_clause(filters)
    conn = get_connection()
    try:
        query = f"""
            SELECT
                t.*,
                c.name AS category_name,
                cl.name AS client_name,
                w.name AS work_type_name,
                a.name AS account_name
            FROM transactions t
            {_JOIN_SQL}
            {where_sql}
            ORDER BY t.transaction_date DESC, t.transaction_time DESC, t.id DESC
        """
        if limit is not None:
            query += " LIMIT ?"
            params = [*params, limit]
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_transaction_summary(filters: dict | None = None) -> dict:
    """현재 필터 조건 기준 조회건수/총수입/총지출/수입건수/지출건수를 DB에서 집계한다."""
    where_sql, params = _build_filter_clause(filters)
    conn = get_connection()
    try:
        query = f"""
            SELECT
                COUNT(*) AS count,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'income' THEN t.amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'expense' THEN t.amount ELSE 0 END), 0) AS total_expense,
                COUNT(CASE WHEN t.transaction_type = 'income' THEN 1 END) AS income_count,
                COUNT(CASE WHEN t.transaction_type = 'expense' THEN 1 END) AS expense_count
            FROM transactions t
            {where_sql}
        """
        row = conn.execute(query, params).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_accounting_type_summary(filters: dict | None = None) -> dict:
    """회계구분(매출/비용) 기준 합계를 집계한다.

    transaction_type(입금/출금)과는 별개의 개념이다 - 예를 들어 대표자
    가수금 입금은 transaction_type='income'이지만 accounting_type은
    '비매출입금'일 수 있다.
    """
    where_sql, params = _build_filter_clause(filters)
    conn = get_connection()
    try:
        query = f"""
            SELECT
                COALESCE(SUM(CASE WHEN t.accounting_type = '매출' THEN t.amount ELSE 0 END), 0) AS total_revenue,
                COALESCE(SUM(CASE WHEN t.accounting_type = '비용' THEN t.amount ELSE 0 END), 0) AS total_cost
            FROM transactions t
            {where_sql}
        """
        row = conn.execute(query, params).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_transaction_by_id(transaction_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            f"""
            SELECT
                t.*,
                c.name AS category_name,
                cl.name AS client_name,
                w.name AS work_type_name,
                a.name AS account_name
            FROM transactions t
            {_JOIN_SQL}
            WHERE t.id = ?
            """,
            (transaction_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_transaction(transaction_id: int, data: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE transactions SET
                transaction_date = :transaction_date,
                transaction_time = :transaction_time,
                description = :description,
                transaction_type = :transaction_type,
                amount = :amount,
                balance = :balance,
                category_id = :category_id,
                client_id = :client_id,
                work_type_id = :work_type_id,
                account_id = :account_id,
                accounting_type = :accounting_type,
                vat_status = :vat_status,
                evidence_status = :evidence_status,
                memo = :memo,
                updated_at = :updated_at
            WHERE id = :id
            """,
            {**data, "id": transaction_id},
        )
        conn.commit()
    finally:
        conn.close()


def find_potential_duplicates(
    transaction_date: str,
    amount: int,
    balance: int | None,
    transaction_time: str | None = None,
    description: str | None = None,
    transaction_type: str | None = None,
) -> list[dict]:
    """중복 감지(10단계)를 위한 후보 조회.

    날짜+금액(+가능하면 잔액)이 같은 기존 거래를 찾아 반환한다.
    idx_transactions_dedup(transaction_date, amount, balance) 인덱스를 탄다.
    실제 '강한 중복'/'부분 중복' 판정은 service 계층에서 이 후보들을 놓고
    시간/거래내용/구분까지 비교해 판단한다 (여기서는 단순 후보 조회만 한다).
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                t.*,
                c.name AS category_name,
                cl.name AS client_name,
                w.name AS work_type_name,
                a.name AS account_name
            FROM transactions t
            """
            + _JOIN_SQL
            + """
            WHERE t.transaction_date = ? AND t.amount = ?
            """,
            (transaction_date, amount),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

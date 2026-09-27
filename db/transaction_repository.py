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
"""


def insert_transaction(data: dict) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO transactions (
                transaction_date, transaction_time, description, transaction_type,
                amount, balance, category_id, client_id, work_type_id,
                vat_status, evidence_status, memo, source_type, created_at, updated_at
            ) VALUES (
                :transaction_date, :transaction_time, :description, :transaction_type,
                :amount, :balance, :category_id, :client_id, :work_type_id,
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
    conn = get_connection()
    try:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        conn.commit()
    finally:
        conn.close()


def get_transactions(filters: dict | None = None) -> list[dict]:
    """카테고리/거래처/업무유형 이름까지 JOIN하여 조회한다.

    기본 정렬: 거래일자 내림차순 -> 거래시간 내림차순 -> id 내림차순.
    """
    where_sql, params = _build_filter_clause(filters)
    conn = get_connection()
    try:
        query = f"""
            SELECT
                t.*,
                c.name AS category_name,
                cl.name AS client_name,
                w.name AS work_type_name
            FROM transactions t
            {_JOIN_SQL}
            {where_sql}
            ORDER BY t.transaction_date DESC, t.transaction_time DESC, t.id DESC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_transaction_summary(filters: dict | None = None) -> dict:
    """현재 필터 조건 기준 조회건수/총수입/총지출을 DB에서 집계한다."""
    where_sql, params = _build_filter_clause(filters)
    conn = get_connection()
    try:
        query = f"""
            SELECT
                COUNT(*) AS count,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'income' THEN t.amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'expense' THEN t.amount ELSE 0 END), 0) AS total_expense
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
                w.name AS work_type_name
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

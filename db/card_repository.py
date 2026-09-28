"""법인카드 명세서(card_statements) / 카드 사용내역(card_transactions) 접근 계층."""
from db.database import get_connection

_LINE_JOIN_SQL = """
    FROM card_transactions ct
    LEFT JOIN categories c ON ct.category_id = c.id
    LEFT JOIN chart_of_accounts a ON ct.account_id = a.id
"""


def insert_statement_with_lines(statement: dict, lines: list[dict]) -> int:
    """명세서와 사용내역을 한 DB 트랜잭션으로 저장한다 (중간 실패 시 전부 되돌림)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO card_statements (card_name, period_start, period_end, billed_total, memo, created_at)
            VALUES (:card_name, :period_start, :period_end, :billed_total, :memo, :created_at)
            """,
            statement,
        )
        statement_id = cursor.lastrowid
        conn.executemany(
            """
            INSERT INTO card_transactions (
                statement_id, use_date, merchant, amount, category_id, account_id,
                accounting_type, vat_status, memo, created_at, updated_at
            ) VALUES (
                :statement_id, :use_date, :merchant, :amount, :category_id, :account_id,
                :accounting_type, :vat_status, :memo, :created_at, :updated_at
            )
            """,
            [{**line, "statement_id": statement_id} for line in lines],
        )
        conn.commit()
        return statement_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_statements() -> list[dict]:
    """명세서 목록 (최근 이용기간 순). 사용내역 건수/합계와 연결된 통장 출금 정보를 함께 조회한다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                s.*,
                (SELECT COUNT(*) FROM card_transactions ct WHERE ct.statement_id = s.id) AS line_count,
                (SELECT COALESCE(SUM(ct.amount), 0) FROM card_transactions ct WHERE ct.statement_id = s.id) AS line_total,
                t.transaction_date AS settlement_date,
                t.amount AS settlement_amount,
                t.description AS settlement_description
            FROM card_statements s
            LEFT JOIN transactions t ON s.settlement_transaction_id = t.id
            ORDER BY s.period_end DESC, s.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_statement_by_id(statement_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM card_statements WHERE id = ?", (statement_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_statement(card_name: str, period_start: str, period_end: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM card_statements WHERE card_name = ? COLLATE NOCASE "
            "AND period_start = ? AND period_end = ?",
            (card_name, period_start, period_end),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_lines(statement_id: int | None = None, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """카드 사용내역 (이용일자 순). 카테고리/계정과목 이름까지 함께 조회한다."""
    clauses, params = [], []
    if statement_id is not None:
        clauses.append("ct.statement_id = ?")
        params.append(statement_id)
    if start_date:
        clauses.append("ct.use_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("ct.use_date <= ?")
        params.append(end_date)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT ct.*, c.name AS category_name, a.name AS account_name
            {_LINE_JOIN_SQL}
            {where_sql}
            ORDER BY ct.use_date, ct.id
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_line_by_id(line_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM card_transactions WHERE id = ?", (line_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_line_classifications(updates: list[dict]) -> None:
    """여러 사용내역의 분류(카테고리/계정과목/회계구분/부가세 여부/메모)를 한 번에 저장한다."""
    conn = get_connection()
    try:
        conn.executemany(
            """
            UPDATE card_transactions SET
                category_id = :category_id, account_id = :account_id,
                accounting_type = :accounting_type, vat_status = :vat_status,
                memo = :memo, updated_at = :updated_at
            WHERE id = :id
            """,
            updates,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_decided_vat_history() -> list[dict]:
    """부가세 여부를 이미 정한 카드 사용내역 (오래된 것부터)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT merchant, vat_status FROM card_transactions WHERE vat_status <> '불명' ORDER BY updated_at, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_vat_statuses(updates: list[dict]) -> int:
    """여러 사용내역의 부가세 여부만 한 번에 바꾼다. updates: [{id, vat_status, updated_at}]"""
    conn = get_connection()
    try:
        cursor = conn.executemany(
            "UPDATE card_transactions SET vat_status = :vat_status, updated_at = :updated_at WHERE id = :id",
            updates,
        )
        conn.commit()
        return cursor.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_settlement(statement_id: int, transaction_id: int | None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE card_statements SET settlement_transaction_id = ? WHERE id = ?",
            (transaction_id, statement_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_linked_transaction_ids() -> set[int]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT settlement_transaction_id FROM card_statements WHERE settlement_transaction_id IS NOT NULL"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def delete_statement(statement_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM card_transactions WHERE statement_id = ?", (statement_id,))
        conn.execute("DELETE FROM card_statements WHERE id = ?", (statement_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_cost_total(start_date: str, end_date: str) -> int:
    """이용일자 기준 기간 내 회계구분 '비용' 카드 사용액 합계 (취소 건은 음수라 자동 차감)."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM card_transactions "
            "WHERE accounting_type = '비용' AND use_date BETWEEN ? AND ?",
            (start_date, end_date),
        ).fetchone()[0]
    finally:
        conn.close()

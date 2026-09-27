"""transactions 테이블에 대한 순수 SQL 접근 계층.

이 모듈은 검증이나 비즈니스 로직을 갖지 않는다.
검증/기본값 처리는 services.transaction_service에서 담당한다.
"""
from db.database import get_connection


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

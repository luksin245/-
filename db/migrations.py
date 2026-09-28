"""기존 DB에 안전하게 컬럼을 추가하는 마이그레이션.

새 테이블은 schema.sql의 CREATE TABLE IF NOT EXISTS로 안전하게 처리되지만,
"기존 테이블에 새 컬럼을 추가"하는 것은 SQLite에 IF NOT EXISTS 구문이
없으므로, 여기서 컬럼 존재 여부를 먼저 확인한 뒤에만 ALTER TABLE을 실행한다.
데이터 손실 없이, 여러 번 실행해도 안전하다.
"""
import sqlite3


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def run_migrations(conn: sqlite3.Connection) -> None:
    """v1.0: transactions 테이블에 account_id/accounting_type 컬럼을 추가한다.

    chart_of_accounts 테이블은 이 함수가 호출되기 전에(schema.sql의
    executescript 단계에서) 이미 생성되어 있어야 한다.
    """
    if not _has_column(conn, "transactions", "account_id"):
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES chart_of_accounts (id)"
        )
    if not _has_column(conn, "transactions", "accounting_type"):
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN accounting_type TEXT NOT NULL DEFAULT '미분류' "
            "CHECK (accounting_type IN ('매출', '비용', '자금이동', '비매출입금', '비비용출금', '미분류'))"
        )

    # 두 컬럼이 (새로 추가되었든 원래 있었든) 이제 확실히 존재하므로 인덱스를 만든다.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions (account_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_accounting_type ON transactions (accounting_type)"
    )

    # v1.0: 자동분류 규칙/OCR 검토 후보에도 계정과목·회계구분 추천값을 저장할 수
    # 있도록 컬럼을 추가한다 (schema.sql 최초 작성 시점에 없었던 DB를 위한 안전장치).
    if not _has_column(conn, "category_rules", "suggested_account_id"):
        conn.execute(
            "ALTER TABLE category_rules ADD COLUMN suggested_account_id INTEGER REFERENCES chart_of_accounts (id)"
        )
    if not _has_column(conn, "category_rules", "suggested_accounting_type"):
        conn.execute(
            "ALTER TABLE category_rules ADD COLUMN suggested_accounting_type TEXT "
            "CHECK (suggested_accounting_type IS NULL OR suggested_accounting_type IN "
            "('매출', '비용', '자금이동', '비매출입금', '비비용출금', '미분류'))"
        )

    if not _has_column(conn, "ocr_raw_lines", "suggested_account_id"):
        conn.execute(
            "ALTER TABLE ocr_raw_lines ADD COLUMN suggested_account_id INTEGER REFERENCES chart_of_accounts (id)"
        )
    if not _has_column(conn, "ocr_raw_lines", "suggested_accounting_type"):
        conn.execute(
            "ALTER TABLE ocr_raw_lines ADD COLUMN suggested_accounting_type TEXT "
            "CHECK (suggested_accounting_type IS NULL OR suggested_accounting_type IN "
            "('매출', '비용', '자금이동', '비매출입금', '비비용출금', '미분류'))"
        )

    conn.commit()

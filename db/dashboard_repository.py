"""대시보드 전용 집계 쿼리.

전체 거래를 pandas로 가져와 매번 다시 계산하지 않고,
SQL의 GROUP BY로 직접 집계하여 거래가 수천~수만 건이 되어도
대시보드 로딩 속도가 크게 느려지지 않도록 한다.

거래처/업무유형/카테고리가 지정되지 않은 거래는 모두 '미분류'로 묶어서
집계한다 (개인 사용 프로그램 특성상 누락 데이터도 눈에 보이게 포함하는
쪽을 기본으로 한다. README "대시보드 사용법" 참고).
"""
from db.database import get_connection

UNCLASSIFIED_LABEL = "미분류"


def get_monthly_trend(start_date: str, end_date: str) -> list[dict]:
    """월(YYYY-MM)별 수입 합계 / 지출 합계."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                substr(transaction_date, 1, 7) AS month,
                COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) AS expense
            FROM transactions
            WHERE transaction_date BETWEEN ? AND ?
            GROUP BY month
            ORDER BY month
            """,
            (start_date, end_date),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_expense_by_category(start_date: str, end_date: str) -> list[dict]:
    """지출 카테고리별 합계 (금액 큰 순). 카테고리 없는 지출은 '미분류'로 묶는다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT COALESCE(c.name, '{UNCLASSIFIED_LABEL}') AS category_name, SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.transaction_type = 'expense' AND t.transaction_date BETWEEN ? AND ?
            GROUP BY category_name
            ORDER BY total DESC
            """,
            (start_date, end_date),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_income_by_work_type(start_date: str, end_date: str) -> list[dict]:
    """업무유형별 수입 합계 (금액 큰 순). 업무유형 없는 수입은 '미분류'로 묶는다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT COALESCE(w.name, '{UNCLASSIFIED_LABEL}') AS work_type_name, SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN work_types w ON t.work_type_id = w.id
            WHERE t.transaction_type = 'income' AND t.transaction_date BETWEEN ? AND ?
            GROUP BY work_type_name
            ORDER BY total DESC
            """,
            (start_date, end_date),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_income_by_client(start_date: str, end_date: str, limit: int = 10) -> list[dict]:
    """거래처별 수입 합계 TOP N (금액 큰 순). 거래처 없는 수입도 '미분류'로 포함한다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT COALESCE(cl.name, '{UNCLASSIFIED_LABEL}') AS client_name, SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN clients cl ON t.client_id = cl.id
            WHERE t.transaction_type = 'income' AND t.transaction_date BETWEEN ? AND ?
            GROUP BY client_name
            ORDER BY total DESC
            LIMIT ?
            """,
            (start_date, end_date, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

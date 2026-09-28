"""자동분류 규칙(category_rules) 접근 계층.

키워드가 거래내용/거래처명에 매칭되면 카테고리/거래처/업무유형/계정과목/회계구분을
"추천"하는 데만 사용한다 - 절대 자동으로 확정하지 않는다.
"""
from db.database import get_connection


def get_rules(status: str = "active") -> list[dict]:
    """기준정보 관리 화면용 목록. status: active/inactive/all."""
    conn = get_connection()
    try:
        query = "SELECT * FROM category_rules WHERE 1=1"
        if status == "active":
            query += " AND is_active = 1"
        elif status == "inactive":
            query += " AND is_active = 0"
        query += " ORDER BY id DESC"
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_active_rules_for_matching() -> list[dict]:
    """OCR/거래등록 화면에서 추천을 계산할 때 쓰는, 활성 규칙 전체(연관 이름 포함)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                r.*,
                c.name AS suggested_category_name,
                cl.name AS suggested_client_name,
                w.name AS suggested_work_type_name,
                a.name AS suggested_account_name
            FROM category_rules r
            LEFT JOIN categories c ON r.suggested_category_id = c.id
            LEFT JOIN clients cl ON r.suggested_client_id = cl.id
            LEFT JOIN work_types w ON r.suggested_work_type_id = w.id
            LEFT JOIN chart_of_accounts a ON r.suggested_account_id = a.id
            WHERE r.is_active = 1
            ORDER BY r.id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_rule_by_id(rule_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM category_rules WHERE id = ?", (rule_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_rule_by_keyword_ci(keyword: str, match_field: str) -> dict | None:
    """대소문자를 구분하지 않고 동일 키워드+매칭필드 조합이 이미 있는지 확인 (중복 등록 방지)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM category_rules WHERE keyword = ? COLLATE NOCASE AND match_field = ?",
            (keyword, match_field),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_rule(data: dict) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO category_rules (
                keyword, match_field, suggested_category_id, suggested_client_id,
                suggested_work_type_id, suggested_account_id, suggested_accounting_type,
                hit_count, is_active, created_at
            ) VALUES (
                :keyword, :match_field, :suggested_category_id, :suggested_client_id,
                :suggested_work_type_id, :suggested_account_id, :suggested_accounting_type,
                0, 1, :created_at
            )
            """,
            data,
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_rule(rule_id: int, data: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE category_rules SET
                keyword = :keyword, match_field = :match_field,
                suggested_category_id = :suggested_category_id,
                suggested_client_id = :suggested_client_id,
                suggested_work_type_id = :suggested_work_type_id,
                suggested_account_id = :suggested_account_id,
                suggested_accounting_type = :suggested_accounting_type
            WHERE id = :id
            """,
            {**data, "id": rule_id},
        )
        conn.commit()
    finally:
        conn.close()


def set_rule_active(rule_id: int, is_active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE category_rules SET is_active = ? WHERE id = ?", (1 if is_active else 0, rule_id)
        )
        conn.commit()
    finally:
        conn.close()


def increment_hit_count(rule_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE category_rules SET hit_count = hit_count + 1 WHERE id = ?", (rule_id,)
        )
        conn.commit()
    finally:
        conn.close()

from db.database import get_connection


def get_categories(type_: str | None = None, active_only: bool = True) -> list[dict]:
    conn = get_connection()
    try:
        query = "SELECT * FROM categories WHERE 1=1"
        params: list = []
        if type_:
            query += " AND type = ?"
            params.append(type_)
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY sort_order, id"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_categories_admin(status: str = "active", type_filter: str | None = None) -> list[dict]:
    """기준정보 관리 화면용 목록. status: active/inactive/all."""
    conn = get_connection()
    try:
        query = "SELECT * FROM categories WHERE 1=1"
        params: list = []
        if type_filter:
            query += " AND type = ?"
            params.append(type_filter)
        if status == "active":
            query += " AND is_active = 1"
        elif status == "inactive":
            query += " AND is_active = 0"
        query += " ORDER BY type, sort_order, id"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_category_by_id(category_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_category_by_name_ci(name: str, type_: str) -> dict | None:
    """대소문자를 구분하지 않고 동일 name+type 카테고리를 찾는다 (중복 등록 사전 방지용)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM categories WHERE name = ? COLLATE NOCASE AND type = ?", (name, type_)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_category(name: str, type_: str, sort_order: int = 0) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO categories (name, type, is_default, is_active, sort_order) "
            "VALUES (?, ?, 0, 1, ?)",
            (name, type_, sort_order),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_category(category_id: int, name: str, sort_order: int) -> None:
    """카테고리명과 정렬순서만 수정한다. type(수입/지출)은 이 함수로 바꿀 수 없다."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE categories SET name = ?, sort_order = ? WHERE id = ?",
            (name, sort_order, category_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_category_active(category_id: int, is_active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE categories SET is_active = ? WHERE id = ?", (1 if is_active else 0, category_id)
        )
        conn.commit()
    finally:
        conn.close()


def count_active_categories(type_: str, exclude_id: int | None = None) -> int:
    conn = get_connection()
    try:
        query = "SELECT COUNT(*) FROM categories WHERE type = ? AND is_active = 1"
        params: list = [type_]
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)
        return conn.execute(query, params).fetchone()[0]
    finally:
        conn.close()

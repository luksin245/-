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


def get_category_by_id(category_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

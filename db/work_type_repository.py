from db.database import get_connection


def get_work_types(active_only: bool = True) -> list[dict]:
    conn = get_connection()
    try:
        query = "SELECT * FROM work_types"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY sort_order, id"
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

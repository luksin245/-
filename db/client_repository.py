from db.database import get_connection


def get_clients(active_only: bool = True) -> list[dict]:
    conn = get_connection()
    try:
        query = "SELECT * FROM clients"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name"
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_client_by_name(name: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM clients WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_client(name: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO clients (name, is_active) VALUES (?, 1)", (name,)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

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


def get_clients_admin(status: str = "active", keyword: str | None = None) -> list[dict]:
    """기준정보 관리 화면용 목록. status: active/inactive/all."""
    conn = get_connection()
    try:
        query = "SELECT * FROM clients WHERE 1=1"
        params: list = []
        if status == "active":
            query += " AND is_active = 1"
        elif status == "inactive":
            query += " AND is_active = 0"
        if keyword:
            query += " AND name LIKE ?"
            params.append(f"%{keyword}%")
        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
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


def find_client_by_name_ci(name: str) -> dict | None:
    """대소문자를 구분하지 않고 이름이 일치하는 거래처를 찾는다 (중복 등록 사전 방지용)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM clients WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_client_by_id(client_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_client(
    name: str,
    default_category_id: int | None = None,
    default_work_type_id: int | None = None,
    memo: str | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO clients (name, default_category_id, default_work_type_id, memo, is_active) "
            "VALUES (?, ?, ?, ?, 1)",
            (name, default_category_id, default_work_type_id, memo),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_client(
    client_id: int,
    name: str,
    default_category_id: int | None,
    default_work_type_id: int | None,
    memo: str | None,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE clients SET name = ?, default_category_id = ?, default_work_type_id = ?, memo = ? "
            "WHERE id = ?",
            (name, default_category_id, default_work_type_id, memo, client_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_client_active(client_id: int, is_active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE clients SET is_active = ? WHERE id = ?", (1 if is_active else 0, client_id)
        )
        conn.commit()
    finally:
        conn.close()

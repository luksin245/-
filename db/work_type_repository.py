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


def get_work_types_admin(status: str = "active") -> list[dict]:
    """기준정보 관리 화면용 목록. status: active/inactive/all."""
    conn = get_connection()
    try:
        query = "SELECT * FROM work_types WHERE 1=1"
        if status == "active":
            query += " AND is_active = 1"
        elif status == "inactive":
            query += " AND is_active = 0"
        query += " ORDER BY sort_order, id"
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_work_type_by_id(work_type_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM work_types WHERE id = ?", (work_type_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_work_type_by_name_ci(name: str) -> dict | None:
    """대소문자를 구분하지 않고 이름이 일치하는 업무유형을 찾는다 (중복 등록 사전 방지용)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM work_types WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_work_type(name: str, sort_order: int = 0) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO work_types (name, is_active, sort_order) VALUES (?, 1, ?)",
            (name, sort_order),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_work_type(work_type_id: int, name: str, sort_order: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE work_types SET name = ?, sort_order = ? WHERE id = ?",
            (name, sort_order, work_type_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_work_type_active(work_type_id: int, is_active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE work_types SET is_active = ? WHERE id = ?", (1 if is_active else 0, work_type_id)
        )
        conn.commit()
    finally:
        conn.close()

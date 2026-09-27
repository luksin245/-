"""SQLite 연결 및 초기화를 담당하는 모듈.

UI(views)나 service 계층은 이 모듈을 통해서만 커넥션을 얻는다.
"""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
# FINANCE_DB_PATH 환경변수로 다른 DB 파일을 가리키게 할 수 있다.
# (자동 테스트나 실제 데이터를 건드리지 않는 UI 점검용도로 사용)
DB_PATH = Path(os.environ.get("FINANCE_DB_PATH", str(DATA_DIR / "finance.db")))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """DB 파일과 테이블이 없으면 생성하고, 기본 카테고리/업무유형을 채운다.

    여러 번 호출해도 안전하다 (CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE).
    """
    conn = get_connection()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()

    from db import seed_data
    seed_data.seed_defaults()

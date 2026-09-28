"""DB 백업/복구를 위한 파일 시스템 + SQLite backup API 접근 계층.

백업 폴더는 항상 현재 DB_PATH(테스트 시에는 FINANCE_DB_PATH로 오버라이드된 임시
경로)의 부모 폴더 기준으로 계산한다 - 그래야 테스트가 실제 data/backups/를
절대 건드리지 않는다.
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from db import database


def get_backup_dir() -> Path:
    backup_dir = database.DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def create_backup_file(prefix: str = "finance_backup") -> Path:
    """SQLite의 온라인 backup API를 사용해 현재 DB의 일관된 스냅샷을 만든다.

    단순 파일 복사와 달리, DB가 사용 중이더라도 안전하게 일관된 상태의
    복사본을 생성한다.
    """
    backup_dir = get_backup_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = backup_dir / f"{prefix}_{timestamp}.db"

    database.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(database.DB_PATH)
    dst = sqlite3.connect(backup_path)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()
    return backup_path


def list_backup_files() -> list[Path]:
    backup_dir = get_backup_dir()
    return sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def restore_from_file(backup_path: Path) -> None:
    """backup_path의 내용을 현재 DB 경로로 원자적으로 교체한다.

    선택한 백업을 먼저 임시 파일로 안전하게(backup API로) 복사한 뒤
    os.replace()로 한 번에 교체하므로, 복사 도중 어떤 문제가 생기더라도
    기존 DB 파일은 전혀 손상되지 않는다 (os.replace 이전까지는 원본을
    건드리지 않기 때문).
    """
    db_path = database.DB_PATH
    tmp_path = db_path.parent / f".{db_path.name}.restoring.tmp"
    if tmp_path.exists():
        tmp_path.unlink()

    src = sqlite3.connect(backup_path)
    tmp = sqlite3.connect(tmp_path)
    try:
        with tmp:
            src.backup(tmp)
    finally:
        src.close()
        tmp.close()

    os.replace(tmp_path, db_path)

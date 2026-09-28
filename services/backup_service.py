from datetime import datetime

from db import backup_repository as repo
from db import database
from utils.validators import ValidationError


def create_backup() -> dict:
    path = repo.create_backup_file(prefix="finance_backup")
    stat = path.stat()
    return {
        "filename": path.name,
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def list_backups() -> list[dict]:
    files = repo.list_backup_files()
    return [
        {
            "filename": p.name,
            "size_bytes": p.stat().st_size,
            "created_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        }
        for p in files
    ]


def restore_backup(filename: str) -> dict:
    """선택한 백업으로 복구한다.

    복구 직전 현재 DB를 pre_restore_* 이름으로 반드시 먼저 백업하고,
    그 다음에만 실제 교체를 수행한다. 교체는 원자적으로 처리되어
    (backup_repository.restore_from_file 참고) 중간 실패 시에도
    기존 DB가 손상되지 않는다.
    """
    backup_dir = repo.get_backup_dir()
    backup_path = backup_dir / filename
    if not filename or not backup_path.exists() or not backup_path.is_file():
        raise ValidationError("선택한 백업 파일을 찾을 수 없습니다.")

    pre_restore_path = repo.create_backup_file(prefix="pre_restore")
    repo.restore_from_file(backup_path)

    # 복구된 파일이 예전 버전(스키마 추가 전)일 수 있으므로, 새 테이블/인덱스가
    # 안전하게(CREATE ... IF NOT EXISTS) 반영되도록 다시 적용한다.
    database.init_db()

    return {
        "restored_from": filename,
        "pre_restore_backup": pre_restore_path.name,
    }


def get_db_info() -> dict:
    backups = list_backups()
    return {
        "db_path": str(database.DB_PATH),
        "backup_dir": str(repo.get_backup_dir()),
        "last_backup_time": backups[0]["created_at"] if backups else None,
    }

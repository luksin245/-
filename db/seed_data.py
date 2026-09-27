"""프로그램 최초 실행 시 채워 넣을 기본 카테고리 / 업무유형 정의.

INSERT OR IGNORE + UNIQUE 제약조건을 사용하므로 여러 번 실행해도
중복 데이터가 생기지 않는다.
"""
from db.database import get_connection

INCOME_CATEGORIES = [
    "기업자문",
    "급여관리",
    "노동사건",
    "직장내괴롭힘 조사",
    "컨설팅",
    "강의료",
    "상담료",
    "기타",
]

EXPENSE_CATEGORIES = [
    "광고선전비",
    "지급수수료",
    "교통비",
    "식비",
    "접대비",
    "사무용품비",
    "통신비",
    "임차료",
    "인건비",
    "외주비",
    "세금/공과금",
    "교육비",
    "도서구입비",
    "기타",
]

WORK_TYPES = [
    "기업자문",
    "급여관리",
    "노동사건",
    "직장내괴롭힘 조사",
    "컨설팅",
    "강의",
    "상담",
    "기타",
]


def seed_defaults() -> None:
    conn = get_connection()
    try:
        for order, name in enumerate(INCOME_CATEGORIES):
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, type, is_default, is_active, sort_order) "
                "VALUES (?, 'income', 1, 1, ?)",
                (name, order),
            )
        for order, name in enumerate(EXPENSE_CATEGORIES):
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, type, is_default, is_active, sort_order) "
                "VALUES (?, 'expense', 1, 1, ?)",
                (name, order),
            )
        for order, name in enumerate(WORK_TYPES):
            conn.execute(
                "INSERT OR IGNORE INTO work_types (name, is_active, sort_order) VALUES (?, 1, ?)",
                (name, order),
            )
        conn.commit()
    finally:
        conn.close()

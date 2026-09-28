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

# 계정과목(chart of accounts) 기본값. 손익 항목과 재무상태표 성격 항목이 섞여
# 있는 일반적인 법인 계정과목 예시이며, 사용자가 기준정보 관리에서 자유롭게
# 추가/수정/비활성화할 수 있다.
CHART_OF_ACCOUNTS = [
    "매출",
    "급여",
    "지급수수료",
    "여비교통비",
    "차량유지비",
    "접대비",
    "복리후생비",
    "광고선전비",
    "통신비",
    "임차료",
    "소모품비",
    "도서인쇄비",
    "교육훈련비",
    "세금과공과",
    "보험료",
    "외주용역비",
    "미수금",
    "미지급금",
    "선급금",
    "예수금",
    "가수금",
    "가지급금",
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
        for order, name in enumerate(CHART_OF_ACCOUNTS):
            conn.execute(
                "INSERT OR IGNORE INTO chart_of_accounts (name, is_active, sort_order) VALUES (?, 1, ?)",
                (name, order),
            )
        conn.commit()
    finally:
        conn.close()

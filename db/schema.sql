PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    is_default INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (name, type)
);

CREATE TABLE IF NOT EXISTS work_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- 계정과목(chart of accounts). 업무유형과는 별개의 분류축이며,
-- work_types와 동일한 구조(이름/활성상태/정렬순서)를 사용한다.
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    default_category_id INTEGER REFERENCES categories (id),
    default_work_type_id INTEGER REFERENCES work_types (id),
    memo TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- 모든 금액(amount, balance)은 KRW 원 단위 INTEGER로 저장한다. float 사용 금지.
--
-- transaction_type(수입/지출)은 통장의 입금/출금 방향을 뜻할 뿐,
-- 매출/비용 같은 회계상 성격과는 다른 개념이다 (법인 통장은 대표자 가수금
-- 입금, 자금이동 등 매출이 아닌 입금도 있을 수 있다).
-- 회계상 성격은 별도의 accounting_type(회계구분) 컬럼으로 관리한다.
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_date TEXT NOT NULL,
    transaction_time TEXT,
    description TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    amount INTEGER NOT NULL CHECK (amount > 0),
    balance INTEGER,
    category_id INTEGER REFERENCES categories (id),
    client_id INTEGER REFERENCES clients (id),
    work_type_id INTEGER REFERENCES work_types (id),
    account_id INTEGER REFERENCES chart_of_accounts (id),
    accounting_type TEXT NOT NULL DEFAULT '미분류'
        CHECK (accounting_type IN ('매출', '비용', '자금이동', '비매출입금', '비비용출금', '미분류')),
    vat_status TEXT NOT NULL DEFAULT '불명' CHECK (vat_status IN ('과세', '면세', '불명', '해당없음')),
    evidence_status TEXT NOT NULL DEFAULT '확인필요' CHECK (evidence_status IN ('있음', '없음', '확인필요')),
    memo TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual' CHECK (source_type IN ('manual', 'ocr', 'csv_import')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_client ON transactions (client_id);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions (category_id);
CREATE INDEX IF NOT EXISTS idx_transactions_dedup ON transactions (transaction_date, amount, balance);
-- 3단계(대시보드) 추가: 거래처 필터와 동일한 이유로 업무유형 필터/집계도 자주 사용됨
CREATE INDEX IF NOT EXISTS idx_transactions_work_type ON transactions (work_type_id);
-- 대시보드의 KPI/월별추이/카테고리·업무유형 집계는 대부분
-- "기간 + 수입|지출 구분"으로 필터링하므로 복합 인덱스로 함께 최적화한다.
CREATE INDEX IF NOT EXISTS idx_transactions_type_date ON transactions (transaction_type, transaction_date);
-- v1.0 추가: 계정과목(account_id)/회계구분(accounting_type) 인덱스는 두 컬럼이
-- 기존 DB에도 안전하게 추가된 뒤에만 만들 수 있으므로, 여기가 아니라
-- db/migrations.py에서 컬럼을 추가한 직후에 생성한다 (기존 DB에서는 이 스크립트가
-- 실행되는 시점에 아직 컬럼이 없어 CREATE INDEX가 실패할 수 있기 때문).

-- 자동분류 규칙: 거래내용/거래처 키워드로 카테고리/거래처/업무유형을 "추천"만 한다
-- (자동 확정하지 않음).
CREATE TABLE IF NOT EXISTS category_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    match_field TEXT NOT NULL DEFAULT 'description' CHECK (match_field IN ('description', 'client_name')),
    suggested_category_id INTEGER REFERENCES categories (id),
    suggested_client_id INTEGER REFERENCES clients (id),
    suggested_work_type_id INTEGER REFERENCES work_types (id),
    suggested_account_id INTEGER REFERENCES chart_of_accounts (id),
    suggested_accounting_type TEXT
        CHECK (suggested_accounting_type IS NULL OR suggested_accounting_type IN
            ('매출', '비용', '자금이동', '비매출입금', '비비용출금', '미분류')),
    suggested_vat_status TEXT
        CHECK (suggested_vat_status IS NULL OR suggested_vat_status IN ('과세', '면세', '불명', '해당없음')),
    hit_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- OCR 업로드 문서 + 검토 전 임시 거래 후보.
-- OCR 결과는 절대 transactions에 바로 저장되지 않고, 사용자가 검토/확정한
-- 뒤에만 transaction_service를 통해 transactions로 옮겨진다.
CREATE TABLE IF NOT EXISTS ocr_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('png', 'jpg', 'jpeg', 'pdf')),
    uploaded_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'ocr_done', 'reviewed', 'confirmed'))
);

CREATE TABLE IF NOT EXISTS ocr_raw_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES ocr_documents (id),
    line_no INTEGER NOT NULL,
    raw_date TEXT,
    raw_time TEXT,
    raw_description TEXT,
    raw_income INTEGER,
    raw_expense INTEGER,
    raw_balance INTEGER,
    confidence REAL,
    status TEXT NOT NULL DEFAULT '확인필요' CHECK (status IN ('정상', '확인필요', '중복의심')),
    suggested_category_id INTEGER REFERENCES categories (id),
    suggested_client_id INTEGER REFERENCES clients (id),
    suggested_work_type_id INTEGER REFERENCES work_types (id),
    suggested_account_id INTEGER REFERENCES chart_of_accounts (id),
    suggested_accounting_type TEXT
        CHECK (suggested_accounting_type IS NULL OR suggested_accounting_type IN
            ('매출', '비용', '자금이동', '비매출입금', '비비용출금', '미분류')),
    suggested_vat_status TEXT
        CHECK (suggested_vat_status IS NULL OR suggested_vat_status IN ('과세', '면세', '불명', '해당없음')),
    is_confirmed INTEGER NOT NULL DEFAULT 0,
    linked_transaction_id INTEGER REFERENCES transactions (id)
);

CREATE INDEX IF NOT EXISTS idx_ocr_raw_lines_document ON ocr_raw_lines (document_id);

-- 법인카드 명세서(월별) + 카드 사용내역.
-- 카드 사용내역은 통장 거래(transactions)와 분리해서 저장한다. 통장에는 한 달치 카드값이
-- "카드결" 출금 한 건으로만 찍히므로, 카드 사용 건을 transactions에 넣으면 지출이 두 번
-- 잡히고 통장 기준 총지출/잔액도 맞지 않게 된다. 카드 사용 건은 회계구분 기준 총비용에만
-- 반영하고, 통장의 카드결 출금은 명세서와 연결(settlement_transaction_id)해서 맞춰본다.
CREATE TABLE IF NOT EXISTS card_statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_name TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    billed_total INTEGER NOT NULL,
    settlement_transaction_id INTEGER REFERENCES transactions (id),
    memo TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id INTEGER NOT NULL REFERENCES card_statements (id),
    use_date TEXT NOT NULL,
    merchant TEXT NOT NULL,
    -- 청구금액(원). 취소/환불 건은 음수로 저장한다.
    amount INTEGER NOT NULL CHECK (amount <> 0),
    category_id INTEGER REFERENCES categories (id),
    account_id INTEGER REFERENCES chart_of_accounts (id),
    accounting_type TEXT NOT NULL DEFAULT '미분류'
        CHECK (accounting_type IN ('매출', '비용', '자금이동', '비매출입금', '비비용출금', '미분류')),
    -- 부가세 여부. '과세'면 청구금액에 부가세 10%가 포함된 것으로 보고 공급가액/부가세를 나눠 보여준다.
    vat_status TEXT NOT NULL DEFAULT '불명' CHECK (vat_status IN ('과세', '면세', '불명', '해당없음')),
    memo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_card_transactions_statement ON card_transactions (statement_id);
CREATE INDEX IF NOT EXISTS idx_card_transactions_date ON card_transactions (use_date);

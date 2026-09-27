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

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    default_category_id INTEGER REFERENCES categories (id),
    default_work_type_id INTEGER REFERENCES work_types (id),
    memo TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- 모든 금액(amount, balance)은 KRW 원 단위 INTEGER로 저장한다. float 사용 금지.
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

"""법인카드 명세서 / 사용내역 비즈니스 로직.

- 카드 사용내역은 통장 거래와 분리해서 저장한다 (통장에는 카드값이 '카드결' 출금 한 건으로만
  찍히므로, 같은 돈이 두 번 지출로 잡히지 않게 하기 위함).
- 명세서의 총합계(청구금액)와 사용내역 합계가 1원이라도 다르면 저장하지 않는다. OCR이나
  입력 실수로 금액이 틀린 채 저장되는 것을 막는 핵심 안전장치다.
- 통장의 카드결 출금과의 연결(맞춰보기)과 그 출금의 회계구분 변경은 사용자가 버튼을
  눌렀을 때만 수행한다 (자동 확정 없음).
"""
from datetime import date, datetime, timedelta

from db import account_repository, card_repository, category_repository
from db import transaction_repository as tx_repo
from services import category_rule_service
from services.transaction_service import ACCOUNTING_TYPE_OPTIONS
from utils.validators import ValidationError

DEFAULT_CARD_NAME = "신한카드 법인"
DEFAULT_LINE_ACCOUNTING_TYPE = "미분류"
# 이용기간이 끝난 뒤 이 기간 안에 빠져나간 같은 금액의 출금을 카드값 결제 후보로 본다.
SETTLEMENT_SEARCH_DAYS = 60
SETTLEMENT_ACCOUNTING_TYPE = "비비용출금"
SETTLEMENT_ACCOUNT_NAME = "미지급금"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_iso_date(value, field_label: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValidationError(f"{field_label} 형식이 올바르지 않습니다 (예: 2026-08-07).")


def _validate_category(category_id: int | None, unchanged: bool) -> None:
    if category_id is None:
        return
    category = category_repository.get_category_by_id(category_id)
    if category is None:
        raise ValidationError("존재하지 않는 카테고리입니다.")
    if category["type"] != "expense":
        raise ValidationError("카드 사용내역에는 지출 카테고리만 지정할 수 있습니다.")
    if not unchanged and not category["is_active"]:
        raise ValidationError(f"비활성화된 카테고리입니다: {category['name']}")


def _validate_account(account_id: int | None, unchanged: bool) -> None:
    if account_id is None:
        return
    account = account_repository.get_account_by_id(account_id)
    if account is None:
        raise ValidationError("존재하지 않는 계정과목입니다.")
    if not unchanged and not account["is_active"]:
        raise ValidationError(f"비활성화된 계정과목입니다: {account['name']}")


def _validate_accounting_type(accounting_type: str) -> None:
    if accounting_type not in ACCOUNTING_TYPE_OPTIONS:
        raise ValidationError("회계구분 값이 올바르지 않습니다.")


def normalize_lines(lines: list[dict]) -> list[dict]:
    """입력된 사용내역을 검증/정리한다. 문제가 있으면 몇 번째 줄인지 알려주는 오류를 낸다."""
    normalized = []
    for idx, line in enumerate(lines, start=1):
        prefix = f"{idx}번째 줄: "
        try:
            merchant = (line.get("merchant") or "").strip()
            if not merchant:
                raise ValidationError("가맹점명은 필수입니다.")
            amount = line.get("amount")
            if amount is None or isinstance(amount, bool) or int(amount) != amount:
                raise ValidationError("청구금액은 원 단위 정수여야 합니다.")
            amount = int(amount)
            if amount == 0:
                raise ValidationError("청구금액은 0원일 수 없습니다 (취소·환불은 음수로 입력).")
            accounting_type = line.get("accounting_type") or DEFAULT_LINE_ACCOUNTING_TYPE
            _validate_accounting_type(accounting_type)
            _validate_category(line.get("category_id"), unchanged=False)
            _validate_account(line.get("account_id"), unchanged=False)
            normalized.append(
                {
                    "use_date": _parse_iso_date(line.get("use_date"), "이용일자"),
                    "merchant": merchant,
                    "amount": amount,
                    "category_id": line.get("category_id"),
                    "account_id": line.get("account_id"),
                    "accounting_type": accounting_type,
                    "memo": (line.get("memo") or "").strip() or None,
                }
            )
        except ValidationError as e:
            raise ValidationError(prefix + str(e))
    return normalized


def create_statement(
    card_name: str,
    period_start,
    period_end,
    billed_total: int,
    lines: list[dict],
    memo: str | None = None,
) -> int:
    card_name = (card_name or "").strip()
    if not card_name:
        raise ValidationError("카드 이름은 필수입니다.")
    start = _parse_iso_date(period_start, "이용기간 시작일")
    end = _parse_iso_date(period_end, "이용기간 종료일")
    if start > end:
        raise ValidationError("이용기간 종료일이 시작일보다 빠릅니다.")
    if billed_total is None or isinstance(billed_total, bool) or int(billed_total) != billed_total:
        raise ValidationError("명세서 총합계는 원 단위 정수여야 합니다.")
    if not lines:
        raise ValidationError("카드 사용내역을 한 줄 이상 입력해주세요.")

    normalized = normalize_lines(lines)
    line_total = sum(line["amount"] for line in normalized)
    if line_total != billed_total:
        diff = billed_total - line_total
        raise ValidationError(
            f"사용내역 합계({line_total:,}원)가 명세서 총합계({billed_total:,}원)와 {abs(diff):,}원 다릅니다. "
            "금액을 다시 확인하거나, 빠진 항목(연회비·수수료·취소 건 등)이 없는지 확인해주세요."
        )

    if card_repository.find_statement(card_name, start, end):
        raise ValidationError(f"'{card_name}' {start} ~ {end} 명세서는 이미 등록되어 있습니다.")

    now = _now()
    statement = {
        "card_name": card_name,
        "period_start": start,
        "period_end": end,
        "billed_total": int(billed_total),
        "memo": (memo or "").strip() or None,
        "created_at": now,
    }
    return card_repository.insert_statement_with_lines(
        statement, [{**line, "created_at": now, "updated_at": now} for line in normalized]
    )


def list_statements() -> list[dict]:
    return card_repository.get_statements()


def get_statement(statement_id: int) -> dict | None:
    return card_repository.get_statement_by_id(statement_id)


def get_lines(statement_id: int | None = None, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    return card_repository.get_lines(statement_id, start_date, end_date)


def update_classifications(statement_id: int, updates: list[dict]) -> None:
    """명세서에 속한 사용내역들의 분류를 한꺼번에 저장한다.

    원래 저장돼 있던 카테고리/계정과목을 그대로 두는 경우에는 그 항목이 나중에
    비활성화됐더라도 허용한다 (다른 화면들과 같은 원칙).
    """
    now = _now()
    prepared = []
    for update in updates:
        original = card_repository.get_line_by_id(update["id"])
        if original is None or original["statement_id"] != statement_id:
            raise ValidationError("이 명세서에 속하지 않은 사용내역입니다. 화면을 새로고침해주세요.")
        accounting_type = update.get("accounting_type") or DEFAULT_LINE_ACCOUNTING_TYPE
        _validate_accounting_type(accounting_type)
        _validate_category(update.get("category_id"), unchanged=update.get("category_id") == original["category_id"])
        _validate_account(update.get("account_id"), unchanged=update.get("account_id") == original["account_id"])
        prepared.append(
            {
                "id": update["id"],
                "category_id": update.get("category_id"),
                "account_id": update.get("account_id"),
                "accounting_type": accounting_type,
                "memo": (update.get("memo") or "").strip() or None,
                "updated_at": now,
            }
        )
    card_repository.update_line_classifications(prepared)


def suggest_for_merchant(merchant: str) -> dict:
    """자동분류 규칙으로 가맹점명에 대한 추천값을 돌려준다 (없으면 빈 dict).

    카드 사용내역에 맞지 않는 추천(수입 카테고리, 비활성 항목)은 걸러낸다.
    """
    suggestion = category_rule_service.suggest_for(merchant, None)
    if not suggestion:
        return {}
    result = {}
    if suggestion.get("category_id"):
        category = category_repository.get_category_by_id(suggestion["category_id"])
        if category and category["type"] == "expense" and category["is_active"]:
            result["category_id"] = category["id"]
    if suggestion.get("account_id"):
        account = account_repository.get_account_by_id(suggestion["account_id"])
        if account and account["is_active"]:
            result["account_id"] = account["id"]
    if suggestion.get("accounting_type"):
        result["accounting_type"] = suggestion["accounting_type"]
    return result


def find_settlement_candidates(statement_id: int) -> list[dict]:
    """명세서 총합계와 금액이 정확히 같은 통장 출금을 찾는다 (이용기간 종료 후 60일 이내).

    다른 명세서에 이미 연결된 출금에는 linked_elsewhere=True를 붙여 구분한다.
    """
    statement = card_repository.get_statement_by_id(statement_id)
    if statement is None or statement["billed_total"] <= 0:
        return []
    period_end = date.fromisoformat(statement["period_end"])
    date_from = (period_end + timedelta(days=1)).isoformat()
    date_to = (period_end + timedelta(days=SETTLEMENT_SEARCH_DAYS)).isoformat()
    linked = card_repository.get_linked_transaction_ids()
    candidates = tx_repo.find_expenses_by_amount(statement["billed_total"], date_from, date_to)
    for tx in candidates:
        tx["linked_elsewhere"] = tx["id"] in linked and tx["id"] != statement["settlement_transaction_id"]
    return candidates


def link_settlement(statement_id: int, transaction_id: int, reclassify: bool = True) -> None:
    """명세서를 통장의 카드값 결제 출금과 연결한다.

    reclassify=True면 그 출금을 회계구분 '비비용출금' / 계정과목 '미지급금'으로 바꾼다 -
    실제 비용은 카드 사용내역 쪽에서 잡히므로, 결제 출금까지 비용으로 두면 두 번 계산된다.
    """
    statement = card_repository.get_statement_by_id(statement_id)
    if statement is None:
        raise ValidationError("존재하지 않는 명세서입니다.")
    tx = tx_repo.get_transaction_by_id(transaction_id)
    if tx is None:
        raise ValidationError("존재하지 않는 통장 거래입니다.")
    if tx["transaction_type"] != "expense":
        raise ValidationError("카드값 결제는 통장 출금 거래와만 연결할 수 있습니다.")
    if tx["amount"] != statement["billed_total"]:
        raise ValidationError(
            f"금액이 다릅니다 (통장 출금 {tx['amount']:,}원 / 명세서 {statement['billed_total']:,}원)."
        )
    linked = card_repository.get_linked_transaction_ids()
    if transaction_id in linked and transaction_id != statement["settlement_transaction_id"]:
        raise ValidationError("이 출금은 이미 다른 카드 명세서와 연결되어 있습니다.")

    card_repository.set_settlement(statement_id, transaction_id)

    if reclassify:
        account = account_repository.find_account_by_name_ci(SETTLEMENT_ACCOUNT_NAME)
        account_id = account["id"] if account and account["is_active"] else tx["account_id"]
        tx_repo.set_accounting_classification(transaction_id, SETTLEMENT_ACCOUNTING_TYPE, account_id, _now())


def unlink_settlement(statement_id: int) -> None:
    """연결만 해제한다. 통장 출금의 회계구분은 되돌리지 않는다 (필요하면 거래내역에서 직접 수정)."""
    if card_repository.get_statement_by_id(statement_id) is None:
        raise ValidationError("존재하지 않는 명세서입니다.")
    card_repository.set_settlement(statement_id, None)


def delete_statement(statement_id: int) -> None:
    """명세서와 그 사용내역을 삭제한다. 연결돼 있던 통장 출금 자체는 지우지 않는다."""
    if card_repository.get_statement_by_id(statement_id) is None:
        raise ValidationError("존재하지 않는 명세서입니다.")
    card_repository.delete_statement(statement_id)


def get_card_cost_total(start_date: str, end_date: str) -> int:
    return card_repository.get_cost_total(start_date, end_date)


# ---------------------------------------------------------------------
# 엑셀/CSV 불러오기 (AI 등으로 만든 파일 -> 입력 표 채우기용. 저장은 하지 않는다)
# ---------------------------------------------------------------------
IMPORT_REQUIRED_COLUMNS = ("이용일자", "가맹점명", "청구금액")
IMPORT_OPTIONAL_COLUMNS = ("카테고리", "회계구분", "계정과목", "메모")
# 같은 뜻으로 흔히 쓰는 열 이름. '이용금액'은 해외 결제에서 외화 금액이라 일부러 받지 않는다.
_COLUMN_ALIASES = {
    "이용일": "이용일자", "이용 일자": "이용일자", "거래일자": "이용일자", "일자": "이용일자", "날짜": "이용일자",
    "가맹점": "가맹점명", "가맹점 명": "가맹점명", "사용처": "가맹점명",
    "청구 금액": "청구금액", "청구금액(원)": "청구금액", "금액": "청구금액", "금액(원)": "청구금액",
}
# 명세서의 소계·합계 줄(이용일자 없이 가맹점명 칸에만 글자가 있는 줄)은 사용내역이 아니므로 건너뛴다.
_SUBTOTAL_MARKERS = ("합계", "소계", "일시불", "할부")


def _import_date(value, row_no: int) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().split(" ")[0].rstrip(".")
    for sep in (".", "/"):
        text = text.replace(sep, "-")
    parts = text.split("-")
    try:
        if len(parts) == 3:
            year, month, day = (int(p) for p in parts)
            if year < 100:
                year += 2000
            return date(year, month, day)
    except ValueError:
        pass
    raise ValidationError(f"{row_no}행: 이용일자 '{value}'를 읽을 수 없습니다 (예: 2026-08-07).")


def _import_amount(value, row_no: int) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{row_no}행: 청구금액 '{value}'를 읽을 수 없습니다.")
    if isinstance(value, (int, float)):
        if float(value) != int(value):
            raise ValidationError(f"{row_no}행: 청구금액 {value}은(는) 원 단위 정수가 아닙니다. 원화 청구금액을 넣어주세요.")
        return int(value)
    text = str(value).replace(",", "").replace("원", "").replace(" ", "").strip()
    if text.lstrip("-").isdigit():
        return int(text)
    raise ValidationError(f"{row_no}행: 청구금액 '{value}'를 읽을 수 없습니다 (숫자만, 예: 27000).")


def _read_table(file_bytes: bytes, filename: str):
    import io

    import pandas as pd

    name = filename.lower()
    if name.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, dtype=object)
    if name.endswith(".csv"):
        for encoding in ("utf-8-sig", "cp949"):
            try:
                return pd.read_csv(io.BytesIO(file_bytes), dtype=object, encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValidationError("CSV 파일의 글자 인코딩을 읽을 수 없습니다. 엑셀(.xlsx)로 저장해서 올려주세요.")
    raise ValidationError("엑셀(.xlsx) 또는 CSV(.csv) 파일만 불러올 수 있습니다.")


def parse_lines_file(file_bytes: bytes, filename: str) -> dict:
    """엑셀/CSV 파일에서 카드 사용내역을 읽는다. 저장하지 않고 입력 표에 채울 값만 돌려준다.

    이용일자·청구금액을 읽을 수 없으면 추정하지 않고 몇 행인지 알려주는 오류를 낸다.
    반환값: {"rows": [...], "skipped": ["총합계", ...]}
    """
    import pandas as pd

    df = _read_table(file_bytes, filename)
    df.columns = [_COLUMN_ALIASES.get(str(c).strip(), str(c).strip()) for c in df.columns]
    missing = [c for c in IMPORT_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValidationError(
            f"필수 열이 없습니다: {', '.join(missing)}. 첫 줄(제목 줄)에 이용일자, 가맹점명, 청구금액이 있어야 합니다."
        )

    def cell(row, column):
        value = row.get(column) if column in df.columns else None
        if value is None or (not isinstance(value, str) and pd.isna(value)):
            return None
        return value.strip() if isinstance(value, str) else value

    rows, skipped = [], []
    for idx, row in df.iterrows():
        row_no = idx + 2  # 엑셀 기준 행 번호 (1행은 제목 줄)
        raw_date, merchant, raw_amount = cell(row, "이용일자"), cell(row, "가맹점명"), cell(row, "청구금액")
        if raw_date is None and merchant is None and raw_amount is None:
            continue
        if raw_date is None and merchant and any(m in str(merchant) for m in _SUBTOTAL_MARKERS):
            skipped.append(str(merchant))
            continue
        if raw_date is None:
            raise ValidationError(f"{row_no}행: 이용일자가 비어 있습니다.")
        if merchant is None:
            raise ValidationError(f"{row_no}행: 가맹점명이 비어 있습니다.")
        if raw_amount is None:
            raise ValidationError(f"{row_no}행: 청구금액이 비어 있습니다.")
        accounting_type = cell(row, "회계구분")
        if accounting_type is not None and accounting_type not in ACCOUNTING_TYPE_OPTIONS:
            raise ValidationError(
                f"{row_no}행: 회계구분 '{accounting_type}'은(는) 쓸 수 없습니다 ({', '.join(ACCOUNTING_TYPE_OPTIONS)} 중 하나)."
            )
        rows.append(
            {
                "이용일자": _import_date(raw_date, row_no),
                "가맹점명": str(merchant),
                "청구금액": _import_amount(raw_amount, row_no),
                "카테고리": cell(row, "카테고리"),
                "회계구분": accounting_type,
                "계정과목": cell(row, "계정과목"),
                "메모": None if cell(row, "메모") is None else str(cell(row, "메모")),
            }
        )
    if not rows:
        raise ValidationError("불러올 사용내역이 없습니다. 2행부터 사용내역을 한 줄씩 넣어주세요.")
    return {"rows": rows, "skipped": skipped}


def build_import_template() -> bytes:
    """불러오기용 빈 양식 엑셀. 첫 시트는 제목 줄만, 둘째 시트에 작성 방법을 적는다."""
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "사용내역"
    ws.append(list(IMPORT_REQUIRED_COLUMNS + IMPORT_OPTIONAL_COLUMNS))
    for col, width in zip("ABCDEFG", (12, 32, 14, 14, 10, 14, 24)):
        ws.column_dimensions[col].width = width

    guide = wb.create_sheet("작성방법")
    for line in (
        ["필수: 이용일자, 가맹점명, 청구금액 / 나머지 열은 비워도 됩니다."],
        ["이용일자: 2026-08-07 형식"],
        ["청구금액: 원 단위 숫자만 (해외 결제는 원화 청구금액, 취소·환불은 음수)"],
        ["소계·합계 줄(일시불, 카드별 소계, 총합계 등)은 넣지 마세요."],
        [f"회계구분: {', '.join(ACCOUNTING_TYPE_OPTIONS)} 중 하나 (비워두면 미분류)"],
        ["예시) 2026-08-07 | 주식회사 아성다이소 | 27000"],
    ):
        guide.append(line)
    guide.column_dimensions["A"].width = 80

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

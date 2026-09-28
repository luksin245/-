"""부가세 정리: 부가세 여부 추천, 한꺼번에 적용, 기간별 예상 부가세 집계.

원칙
- 통장/카드 금액은 절대 바꾸지 않는다. '과세'(부가세 10% 포함)로 표시된 건만 공급가액과
  부가세를 나눠서 보여주고 집계한다.
- 금액만 보고 확정하지 않는다. 자동분류 규칙에 부가세 여부가 있으면 그 값을, 없으면
  회계구분이 매출·비용이고 금액이 11로 나누어떨어질 때만 '과세'를 "추천"한다.
  실제 저장은 사용자가 화면에서 확인하고 버튼을 눌렀을 때만 한다.
- 예상 부가세는 참고용이다. 실제 신고는 홈택스의 세금계산서·카드 자료로 세무사가 한다
  (접대비 등 공제받지 못하는 매입세액은 여기서 구분하지 않는다).
"""
from datetime import date, datetime, timedelta

from db import card_repository
from db import transaction_repository as tx_repo
from services import category_rule_service
from services.transaction_service import DEFAULT_VAT_STATUS, VAT_STATUS_OPTIONS
from utils.validators import ValidationError
from utils.vat import VAT_INCLUDED_STATUS, looks_vat_included, split_vat, vat_of

# 금액(11의 배수)만으로 '과세'를 추천하는 회계구분. 이자·가수금·자금이동·카드값 결제 등은
# 부가세와 무관하므로 금액이 11로 나누어떨어져도 추천하지 않는다.
AMOUNT_SUGGEST_ACCOUNTING_TYPES = ("매출", "비용")
REASON_RULE = "자동분류 규칙"
REASON_AMOUNT = "금액이 11로 나누어떨어짐"

PERIOD_PRESETS = ["이번 분기", "지난 분기", "올해", "직접 선택"]


def get_period_range(preset: str, custom_start=None, custom_end=None, today: date | None = None) -> tuple[date, date]:
    """부가세는 분기 단위로 보는 경우가 많아 분기 기준 빠른 선택을 제공한다 (종료일은 분기 말일)."""
    today = today or date.today()
    quarter_start = date(today.year, (today.month - 1) // 3 * 3 + 1, 1)
    if preset == "이번 분기":
        start = quarter_start
    elif preset == "지난 분기":
        start = (quarter_start - timedelta(days=1)).replace(day=1)
        start = date(start.year, (start.month - 1) // 3 * 3 + 1, 1)
    elif preset == "올해":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    elif preset == "직접 선택":
        if custom_start is None or custom_end is None:
            raise ValidationError("시작일과 종료일을 모두 선택해주세요.")
        if custom_end < custom_start:
            raise ValidationError("종료일은 시작일보다 빠를 수 없습니다.")
        return custom_start, custom_end
    else:
        raise ValidationError(f"알 수 없는 기간 옵션입니다: {preset}")
    next_quarter = date(start.year + (start.month + 3 > 12), (start.month + 2) % 12 + 1, 1)
    return start, next_quarter - timedelta(days=1)


def suggest_vat_status(amount: int, accounting_type: str | None, rule_vat_status: str | None = None) -> dict | None:
    """부가세 여부 추천값 {"vat_status", "reason"}. 추천할 근거가 없으면 None."""
    if rule_vat_status in VAT_STATUS_OPTIONS and rule_vat_status != DEFAULT_VAT_STATUS:
        return {"vat_status": rule_vat_status, "reason": REASON_RULE}
    if accounting_type in AMOUNT_SUGGEST_ACCOUNTING_TYPES and looks_vat_included(amount):
        return {"vat_status": VAT_INCLUDED_STATUS, "reason": REASON_AMOUNT}
    return None


def split_for_display(amount: int, vat_status: str) -> tuple[int | None, int | None]:
    """'과세'면 (공급가액, 부가세), 아니면 (None, None)."""
    if vat_status != VAT_INCLUDED_STATUS:
        return None, None
    return split_vat(amount)


def _rule_vat(rules: list[dict], description: str | None, client_name: str | None) -> str | None:
    suggestion = category_rule_service.suggest_for(description, client_name, rules=rules)
    return suggestion.get("vat_status") if suggestion else None


def get_bank_review(start_date: str, end_date: str) -> dict:
    """기간 내 부가세 여부가 '불명'인 통장 거래와 각 거래의 추천값.

    반환: {"rows": [거래 dict + suggested_vat_status/suggest_reason], "unclassified_count": 회계구분 미분류 건수}
    """
    rules = category_rule_service.load_active_rules()
    rows = tx_repo.get_unknown_vat_transactions(start_date, end_date)
    for row in rows:
        suggestion = suggest_vat_status(
            row["amount"], row["accounting_type"], _rule_vat(rules, row["description"], row["client_name"])
        )
        row["suggested_vat_status"] = suggestion["vat_status"] if suggestion else None
        row["suggest_reason"] = suggestion["reason"] if suggestion else ""
    unclassified = sum(1 for r in rows if r["accounting_type"] == "미분류" and r["suggested_vat_status"] is None)
    return {"rows": rows, "unclassified_count": unclassified}


def get_card_review(start_date: str, end_date: str) -> dict:
    """기간 내(이용일자 기준) 부가세 여부가 '불명'인 카드 사용내역과 추천값."""
    rules = category_rule_service.load_active_rules()
    rows = [l for l in card_repository.get_lines(start_date=start_date, end_date=end_date) if l["vat_status"] == DEFAULT_VAT_STATUS]
    for row in rows:
        suggestion = suggest_vat_status(row["amount"], row["accounting_type"], _rule_vat(rules, row["merchant"], None))
        row["suggested_vat_status"] = suggestion["vat_status"] if suggestion else None
        row["suggest_reason"] = suggestion["reason"] if suggestion else ""
    unclassified = sum(1 for r in rows if r["accounting_type"] == "미분류" and r["suggested_vat_status"] is None)
    return {"rows": rows, "unclassified_count": unclassified}


def _prepare_updates(updates: list[dict]) -> list[dict]:
    now = datetime.now().isoformat(timespec="seconds")
    prepared = []
    for update in updates:
        vat_status = update.get("vat_status")
        if vat_status not in VAT_STATUS_OPTIONS:
            raise ValidationError(f"부가세 여부 값이 올바르지 않습니다: {vat_status}")
        if vat_status == DEFAULT_VAT_STATUS:
            continue  # '불명' 그대로 둔 줄은 저장할 것이 없다
        prepared.append({"id": int(update["id"]), "vat_status": vat_status, "updated_at": now})
    return prepared


def apply_bank_vat(updates: list[dict]) -> int:
    """통장 거래들의 부가세 여부를 저장한다 ('불명'으로 둔 줄은 건너뜀). 저장한 건수를 반환."""
    prepared = _prepare_updates(updates)
    return tx_repo.set_vat_statuses(prepared) if prepared else 0


def apply_card_vat(updates: list[dict]) -> int:
    prepared = _prepare_updates(updates)
    return card_repository.set_vat_statuses(prepared) if prepared else 0


def get_summary(start_date: str, end_date: str) -> dict:
    """기간 내 예상 부가세(참고용)와 공급가액 기준 매출·비용 조정액.

    - 매출세액: '과세'인 통장 입금의 부가세
    - 매입세액: '과세'인 통장 출금 + '과세'인 카드 사용내역(이용일자 기준, 취소는 음수)의 부가세
    - revenue_vat / cost_vat: 회계구분 매출 / 비용인 '과세' 건의 부가세 (총매출·총비용에서 빼면 공급가액 기준)
    - unknown_count: 부가세 여부가 아직 '불명'인 매출·비용 건수 (계산에서 빠진 건)
    """
    sales_vat = purchase_vat_bank = revenue_vat = cost_vat = 0
    sales_count = purchase_count = unknown_count = 0
    for row in tx_repo.get_vat_relevant_rows(start_date, end_date):
        if row["vat_status"] != VAT_INCLUDED_STATUS:
            unknown_count += 1
            continue
        vat = vat_of(row["amount"], row["vat_status"])
        if row["transaction_type"] == "income":
            sales_vat += vat
            sales_count += 1
        else:
            purchase_vat_bank += vat
            purchase_count += 1
        if row["accounting_type"] == "매출":
            revenue_vat += vat
        elif row["accounting_type"] == "비용":
            cost_vat += vat

    purchase_vat_card = 0
    for line in card_repository.get_lines(start_date=start_date, end_date=end_date):
        if line["vat_status"] == VAT_INCLUDED_STATUS:
            vat = vat_of(line["amount"], line["vat_status"])
            purchase_vat_card += vat
            purchase_count += 1
            if line["accounting_type"] == "비용":
                cost_vat += vat
        elif line["vat_status"] == DEFAULT_VAT_STATUS and line["accounting_type"] == "비용":
            unknown_count += 1

    purchase_vat = purchase_vat_bank + purchase_vat_card
    return {
        "sales_vat": sales_vat,
        "purchase_vat_bank": purchase_vat_bank,
        "purchase_vat_card": purchase_vat_card,
        "purchase_vat": purchase_vat,
        "estimated_payable": sales_vat - purchase_vat,
        "sales_count": sales_count,
        "purchase_count": purchase_count,
        "revenue_vat": revenue_vat,
        "cost_vat": cost_vat,
        "unknown_count": unknown_count,
    }

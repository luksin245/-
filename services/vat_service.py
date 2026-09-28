"""부가세 정리: 부가세 여부 추천, 한꺼번에 적용, 기간별 예상 부가세 집계.

원칙
- 통장/카드 금액은 절대 바꾸지 않는다. '과세'(부가세 10% 포함)로 표시된 건만 공급가액과
  부가세를 나눠서 보여주고 집계한다.
- 추천만 하고 확정하지 않는다. 실제 저장은 사용자가 화면에서 확인하고 버튼을 눌렀을 때만 한다.
  추천 순서: 자동분류 규칙 > 예전에 같은 거래(거래처·거래내용·가맹점)를 저장한 값 >
  부가세 없는 거래(이자·세금·가수금·카드값 결제 등) '해당없음' > 통장은 금액이 11의 배수면 '과세',
  카드는 국내 결제면 '과세'(소매가격은 부가세가 포함돼 있어도 11의 배수가 아닌 경우가 많음).
- 같은 거래처/가맹점끼리 묶어서 보여줘 한 번에 정할 수 있게 한다.
- 예상 부가세는 참고용이다. 실제 신고는 홈택스의 세금계산서·카드 자료로 세무사가 한다
  (접대비 등 공제받지 못하는 매입세액은 여기서 구분하지 않는다).
"""
import unicodedata
from datetime import date, datetime, timedelta

from db import card_repository
from db import transaction_repository as tx_repo
from services import category_rule_service
from services.transaction_service import DEFAULT_VAT_STATUS, VAT_STATUS_OPTIONS
from utils.validators import ValidationError
from utils.vat import VAT_INCLUDED_STATUS, looks_vat_included, split_vat, vat_of

NOT_APPLICABLE_STATUS = "해당없음"
# 거래내용/가맹점명에 이 단어가 있으면 부가세와 무관한 돈의 이동으로 보고 '해당없음'을 추천한다.
NO_VAT_KEYWORDS = (
    "이자", "가수금", "가지급금", "카드결", "국세", "지방세", "세무서", "부가세", "부가가치세", "원천세",
    "법인세", "환급", "급여", "상여", "국민연금", "건강보험", "고용보험", "산재보험", "대출", "연회비",
)
# 이 회계구분은 매출·비용이 아닌 돈의 이동이라 부가세가 없다.
NO_VAT_ACCOUNTING_TYPES = ("자금이동", "비매출입금")
REASON_RULE = "자동분류 규칙"
REASON_HISTORY = "예전에 같은 거래를 이렇게 저장함"
REASON_KEYWORD = "부가세 없는 거래 ('{keyword}')"
REASON_ACCOUNTING = "회계구분이 '{accounting_type}'"
REASON_AMOUNT = "금액이 11로 나누어떨어짐 (공급가액 + 10%)"
REASON_CARD_DOMESTIC = "국내 카드 결제 (대부분 부가세 포함)"
REASON_CARD_FOREIGN = "해외 결제로 보임 (국내 부가세 없음)"

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


def normalize_key(text: str | None) -> str:
    """띄어쓰기·대소문자·전각문자 차이를 무시하고 비교하기 위한 키.

    예) '노무법인 돋움' == '노무법인돋움', 'ＣＭＳ사용료'(은행 PDF의 전각 글자) == 'CMS사용료'
    """
    return "".join(unicodedata.normalize("NFKC", text or "").split()).lower()


def counterpart_text(description: str | None) -> str:
    """통장 거래내용에서 앞의 적요(FB자금, BZ뱅크, 타행IB 등)를 뺀 상대방 부분.

    같은 거래처라도 이체 방법에 따라 적요가 달라지므로('BZ뱅크 노무법인돋움' / 'FB자동 노무법인돋움')
    묶음과 과거 기록 비교는 이 부분으로 한다. 한 단어뿐이면 그대로 쓴다.
    """
    parts = (description or "").split()
    return " ".join(parts[1:]) if len(parts) >= 2 else (description or "").strip()


def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text or "")


def _usable(status: str | None) -> bool:
    return status in VAT_STATUS_OPTIONS and status != DEFAULT_VAT_STATUS


def load_context() -> dict:
    """여러 건을 추천할 때 한 번만 읽어두는 자료 (규칙, 예전에 정한 부가세 여부)."""
    by_text: dict[str, str] = {}
    by_client: dict[int, str] = {}
    for row in tx_repo.get_decided_vat_history():  # 오래된 것부터 -> 최근 결정이 덮어씀
        by_text[normalize_key(row["description"])] = row["vat_status"]
        by_text[normalize_key(counterpart_text(row["description"]))] = row["vat_status"]
        if row["client_id"] is not None:
            by_client[row["client_id"]] = row["vat_status"]
    card_by_merchant = {normalize_key(r["merchant"]): r["vat_status"] for r in card_repository.get_decided_vat_history()}
    return {
        "rules": category_rule_service.load_active_rules(),
        "bank_by_text": by_text,
        "bank_by_client": by_client,
        "card_by_merchant": card_by_merchant,
    }


def _no_vat_keyword(text: str | None) -> str | None:
    key = normalize_key(text)
    return next((k for k in NO_VAT_KEYWORDS if k in key), None)


def suggest_vat_status(
    amount: int,
    accounting_type: str | None,
    rule_vat_status: str | None = None,
    history_vat_status: str | None = None,
    text: str | None = None,
    kind: str = "bank",
) -> dict | None:
    """부가세 여부 추천값 {"vat_status", "reason"}. 추천할 근거가 없으면 None.

    kind='bank'이면 금액이 11의 배수일 때 '과세', kind='card'면 국내 결제를 '과세'로 본다.
    """
    if _usable(rule_vat_status):
        return {"vat_status": rule_vat_status, "reason": REASON_RULE}
    if _usable(history_vat_status):
        return {"vat_status": history_vat_status, "reason": REASON_HISTORY}
    keyword = _no_vat_keyword(text)
    if keyword:
        return {"vat_status": NOT_APPLICABLE_STATUS, "reason": REASON_KEYWORD.format(keyword=keyword)}
    if accounting_type in NO_VAT_ACCOUNTING_TYPES:
        return {"vat_status": NOT_APPLICABLE_STATUS, "reason": REASON_ACCOUNTING.format(accounting_type=accounting_type)}
    if kind == "card":
        if text and not _has_hangul(text):
            return {"vat_status": NOT_APPLICABLE_STATUS, "reason": REASON_CARD_FOREIGN}
        return {"vat_status": VAT_INCLUDED_STATUS, "reason": REASON_CARD_DOMESTIC}
    if looks_vat_included(amount):
        return {"vat_status": VAT_INCLUDED_STATUS, "reason": REASON_AMOUNT}
    return None


def _rule_vat(ctx: dict, description: str | None, client_name: str | None) -> str | None:
    suggestion = category_rule_service.suggest_for(description, client_name, rules=ctx["rules"])
    return suggestion.get("vat_status") if suggestion else None


def suggest_for_bank(
    ctx: dict, description: str | None, amount: int, accounting_type: str | None,
    client_id: int | None = None, client_name: str | None = None,
) -> dict | None:
    history = ctx["bank_by_client"].get(client_id) if client_id is not None else None
    history = history or ctx["bank_by_text"].get(normalize_key(description)) \
        or ctx["bank_by_text"].get(normalize_key(counterpart_text(description)))
    return suggest_vat_status(
        amount, accounting_type, _rule_vat(ctx, description, client_name), history, text=description, kind="bank"
    )


def suggest_for_card(ctx: dict, merchant: str | None, amount: int, accounting_type: str | None) -> dict | None:
    return suggest_vat_status(
        amount, accounting_type, _rule_vat(ctx, merchant, None),
        ctx["card_by_merchant"].get(normalize_key(merchant)), text=merchant, kind="card",
    )


def split_for_display(amount: int, vat_status: str) -> tuple[int | None, int | None]:
    """'과세'면 (공급가액, 부가세), 아니면 (None, None)."""
    if vat_status != VAT_INCLUDED_STATUS:
        return None, None
    return split_vat(amount)


def _group(rows: list[dict], label_of, direction_of) -> list[dict]:
    """같은 상대방(+입출금 방향, +추천값)끼리 묶는다. 묶음 하나를 정하면 그 안의 거래 전부에 적용된다."""
    groups: dict[tuple, dict] = {}
    for row in rows:
        label = label_of(row)
        key = (normalize_key(label), direction_of(row), row["suggested_vat_status"])
        group = groups.setdefault(
            key,
            {
                "label": label,
                "direction": direction_of(row),
                "suggested_vat_status": row["suggested_vat_status"],
                "reason": row["suggest_reason"],
                "ids": [],
                "rows": [],
                "total": 0,
            },
        )
        group["ids"].append(row["id"])
        group["rows"].append(row)
        group["total"] += row["amount"]
    result = list(groups.values())
    for group in result:
        dates = sorted(r["_date"] for r in group["rows"])
        group["count"] = len(group["ids"])
        group["period"] = dates[0] if dates[0] == dates[-1] else f"{dates[0]} ~ {dates[-1]}"
    # 추천이 없는(직접 정해야 하는) 묶음을 먼저, 그다음 건수가 많은 순
    result.sort(key=lambda g: (g["suggested_vat_status"] is not None, -g["count"], g["label"]))
    return result


def _bank_label(row: dict) -> str:
    """묶음 이름: 거래처 > (적요 자체가 '이자'·'국세'·'카드결' 같은 경우) 적요 > 상대방 부분."""
    if row["client_name"]:
        return row["client_name"]
    parts = (row["description"] or "").split()
    if len(parts) >= 2 and _no_vat_keyword(parts[0]):
        return parts[0]  # '이자 06.20~09.18', '이자 06.09~06.19' -> '이자' 한 묶음
    return counterpart_text(row["description"]) or row["description"]


def get_bank_review() -> dict:
    """부가세 여부가 아직 '불명'인 통장 거래 전체를 상대방별로 묶어 추천값과 함께 돌려준다.

    반환: {"groups": [...], "row_count": 전체 건수, "suggested_count": 추천이 있는 건수}
    """
    ctx = load_context()
    rows = tx_repo.get_unknown_vat_transactions()
    for row in rows:
        suggestion = suggest_for_bank(
            ctx, row["description"], row["amount"], row["accounting_type"], row["client_id"], row["client_name"]
        )
        row["suggested_vat_status"] = suggestion["vat_status"] if suggestion else None
        row["suggest_reason"] = suggestion["reason"] if suggestion else ""
        row["_date"] = row["transaction_date"]
    groups = _group(
        rows,
        label_of=_bank_label,
        direction_of=lambda r: "입금" if r["transaction_type"] == "income" else "출금",
    )
    return {
        "groups": groups,
        "row_count": len(rows),
        "suggested_count": sum(1 for r in rows if r["suggested_vat_status"]),
    }


def get_card_review() -> dict:
    """부가세 여부가 아직 '불명'인 카드 사용내역 전체를 가맹점별로 묶어 추천값과 함께 돌려준다."""
    ctx = load_context()
    rows = [l for l in card_repository.get_lines() if l["vat_status"] == DEFAULT_VAT_STATUS]
    for row in rows:
        suggestion = suggest_for_card(ctx, row["merchant"], row["amount"], row["accounting_type"])
        row["suggested_vat_status"] = suggestion["vat_status"] if suggestion else None
        row["suggest_reason"] = suggestion["reason"] if suggestion else ""
        row["_date"] = row["use_date"]
    groups = _group(rows, label_of=lambda r: r["merchant"], direction_of=lambda r: "카드")
    return {
        "groups": groups,
        "row_count": len(rows),
        "suggested_count": sum(1 for r in rows if r["suggested_vat_status"]),
    }


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

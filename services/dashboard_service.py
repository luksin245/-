"""대시보드 기간 계산 + 집계 호출.

UI(views/dashboard_view.py)는 이 모듈의 함수만 호출한다.
실제 SQL 집계는 db.dashboard_repository / db.transaction_repository가 담당한다.
"""
from datetime import date, timedelta

from db import dashboard_repository as dash_repo
from db import transaction_repository as tx_repo

PERIOD_PRESETS = ["이번 달", "지난달", "최근 3개월", "올해", "직접 선택"]

RECENT_TRANSACTIONS_LIMIT = 10
TOP_CLIENTS_LIMIT = 10


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _shift_months(d: date, months: int) -> date:
    """d를 '1일' 기준으로 삼아 months개월 이동한 달의 1일을 반환한다."""
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    return date(year, month0 + 1, 1)


def get_period_range(
    preset: str,
    custom_start: date | None = None,
    custom_end: date | None = None,
    today: date | None = None,
) -> tuple[date, date]:
    """빠른 선택 옵션 또는 직접 선택 값을 (시작일, 종료일)로 변환한다.

    today를 인자로 받을 수 있게 해서 테스트에서 특정 날짜 기준으로
    검증할 수 있도록 한다 (기본값은 실제 오늘 날짜).
    """
    today = today or date.today()

    if preset == "이번 달":
        return _month_start(today), today
    if preset == "지난달":
        this_month_start = _month_start(today)
        last_month_end = this_month_start - timedelta(days=1)
        return _month_start(last_month_end), last_month_end
    if preset == "최근 3개월":
        return _shift_months(_month_start(today), -2), today
    if preset == "올해":
        return date(today.year, 1, 1), today
    if preset == "직접 선택":
        if custom_start is None or custom_end is None:
            raise ValueError("시작일과 종료일을 모두 선택해주세요.")
        if custom_end < custom_start:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
        return custom_start, custom_end

    raise ValueError(f"알 수 없는 기간 옵션입니다: {preset}")


def get_previous_period(start: date, end: date) -> tuple[date, date]:
    """비교 기준: 선택 기간과 동일한 일수만큼의 직전 기간.

    예) 9/1~9/27(27일)을 조회하면 직전 기간은 8/5~8/31(27일)이 된다.
    프리셋(이번 달/지난달/최근 3개월/올해/직접 선택) 어떤 경우에도
    같은 규칙 하나로 일관되게 적용한다.
    """
    length_days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length_days - 1)
    return prev_start, prev_end


def _with_net_amount(summary: dict) -> dict:
    summary["net_amount"] = summary["total_income"] - summary["total_expense"]
    return summary


def get_dashboard_data(start: date, end: date) -> dict:
    start_str, end_str = start.isoformat(), end.isoformat()
    filters = {"start_date": start_str, "end_date": end_str}

    summary = _with_net_amount(tx_repo.get_transaction_summary(filters))
    accounting_summary = tx_repo.get_accounting_type_summary(filters)

    prev_start, prev_end = get_previous_period(start, end)
    prev_filters = {"start_date": prev_start.isoformat(), "end_date": prev_end.isoformat()}
    prev_summary = _with_net_amount(tx_repo.get_transaction_summary(prev_filters))

    return {
        "summary": summary,
        "accounting_summary": accounting_summary,
        "prev_summary": prev_summary,
        "prev_period": (prev_start, prev_end),
        "monthly_trend": dash_repo.get_monthly_trend(start_str, end_str),
        "expense_by_category": dash_repo.get_expense_by_category(start_str, end_str),
        "income_by_work_type": dash_repo.get_income_by_work_type(start_str, end_str),
        "income_by_client": dash_repo.get_income_by_client(start_str, end_str, limit=TOP_CLIENTS_LIMIT),
        "recent_transactions": tx_repo.get_transactions(filters, limit=RECENT_TRANSACTIONS_LIMIT),
    }


def calc_average(total: int, count: int) -> int | None:
    """count가 0이면 평균을 낼 수 없으므로 None (화면에서는 '-'로 표시)."""
    if count <= 0:
        return None
    return round(total / count)


def calc_percent_change(current: int, previous: int) -> float | None:
    """previous가 0이면 퍼센트 비교가 무의미하므로 None을 반환한다 (화면에서는 비교 생략)."""
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100

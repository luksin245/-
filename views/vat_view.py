from datetime import date

import pandas as pd
import streamlit as st

from services import transaction_service, vat_service
from utils.formatting import format_amount
from utils.validators import ValidationError
from utils.vat import split_vat

st.title("🧾 부가세 정리")
st.caption(
    "통장·카드 금액은 그대로 두고, 부가세 여부가 '과세'(금액에 부가세 10% 포함)인 건만 공급가액과 부가세로 나눠 "
    "계산합니다. 아래 예상 부가세는 **참고용**입니다 - 실제 신고는 홈택스의 세금계산서·카드 자료로 세무사가 하며, "
    "접대비처럼 공제받지 못하는 매입세액도 여기서는 구분하지 않습니다."
)

TYPE_LABELS = {"income": "입금", "expense": "출금"}
VAT_OPTIONS = transaction_service.VAT_STATUS_OPTIONS
UNKNOWN = transaction_service.DEFAULT_VAT_STATUS

st.session_state.setdefault("vat_version", 0)
if msg := st.session_state.pop("vat_msg", None):
    st.success(msg)

# ---------- 기간 ----------
col_preset, col_start, col_end = st.columns([2, 1, 1])
with col_preset:
    preset = st.radio("기간", vat_service.PERIOD_PRESETS, horizontal=True, key="vat_preset")
custom_start = custom_end = None
if preset == "직접 선택":
    with col_start:
        custom_start = st.date_input("시작일", value=date.today().replace(day=1), key="vat_start")
    with col_end:
        custom_end = st.date_input("종료일", value=date.today(), key="vat_end")
try:
    start, end = vat_service.get_period_range(preset, custom_start, custom_end)
except ValidationError as e:
    st.error(str(e))
    st.stop()
start_str, end_str = start.isoformat(), end.isoformat()
st.caption(f"조회 기간: {start_str} ~ {end_str}")

# ---------- 예상 부가세 ----------
summary = vat_service.get_summary(start_str, end_str)
m1, m2, m3 = st.columns(3)
m1.metric("매출세액 (받은 부가세)", f"{format_amount(summary['sales_vat'])}원", help=f"'과세' 입금 {summary['sales_count']}건")
m2.metric(
    "매입세액 (낸 부가세)",
    f"{format_amount(summary['purchase_vat'])}원",
    help=f"통장 {format_amount(summary['purchase_vat_bank'])}원 + 법인카드 {format_amount(summary['purchase_vat_card'])}원",
)
payable = summary["estimated_payable"]
m3.metric(
    "예상 납부세액 (참고용)" if payable >= 0 else "예상 환급세액 (참고용)",
    f"{format_amount(abs(payable))}원",
    help="매출세액 - 매입세액",
)
st.caption(
    f"매입세액 = 통장 {format_amount(summary['purchase_vat_bank'])}원 + 법인카드 "
    f"{format_amount(summary['purchase_vat_card'])}원 (카드는 이용일자 기준)"
)
if summary["unknown_count"]:
    st.warning(
        f"부가세 여부가 아직 '불명'인 매출·비용 {summary['unknown_count']:,}건은 위 계산에서 빠져 있습니다. "
        "아래에서 확인해 정리하면 더 정확해집니다."
    )

st.divider()


def _review_table(rows: list[dict], columns: dict, key: str) -> pd.DataFrame:
    """추천값을 미리 채운 편집 표. '부가세' 열만 바꿀 수 있다."""
    table = pd.DataFrame(
        [
            {
                "id": r["id"],
                **{label: getter(r) for label, getter in columns.items()},
                "부가세": r["suggested_vat_status"] or UNKNOWN,
                "추천 근거": r["suggest_reason"],
                "과세일 때 부가세": f"{format_amount(split_vat(r['amount'])[1])}원",
            }
            for r in rows
        ]
    )
    shown = list(columns) + ["부가세", "추천 근거", "과세일 때 부가세"]
    return st.data_editor(
        table,
        column_order=shown,
        column_config={
            "부가세": st.column_config.SelectboxColumn(
                "부가세", options=VAT_OPTIONS, required=True,
                help="'과세' = 금액에 부가세 10% 포함. '불명'으로 두면 저장하지 않습니다.",
            ),
        },
        disabled=[c for c in shown if c != "부가세"],
        hide_index=True,
        use_container_width=True,
        key=f"{key}_{st.session_state['vat_version']}",
    )


def _review_section(title: str, review: dict, columns: dict, key: str, apply_fn, unclassified_hint: str) -> None:
    st.subheader(title)
    rows = review["rows"]
    if not rows:
        st.success("이 기간에 부가세 여부가 '불명'인 항목이 없습니다.")
        return
    suggested = [r for r in rows if r["suggested_vat_status"]]
    only_suggested = st.checkbox(
        f"추천이 있는 항목만 보기 ({len(suggested):,}건 / 전체 '불명' {len(rows):,}건)",
        value=bool(suggested),
        key=f"{key}_only_suggested",
    )
    shown_rows = suggested if only_suggested else rows
    if not shown_rows:
        st.info("추천할 수 있는 항목이 없습니다. 체크를 풀면 전체 '불명' 항목을 직접 정할 수 있습니다.")
    else:
        st.caption(
            "추천값이 '부가세' 칸에 미리 채워져 있습니다. 확인하고 틀린 것은 바꾼 뒤 저장하세요. "
            "'불명'으로 둔 줄은 저장하지 않습니다."
        )
        # 보기 범위가 바뀌면 표의 줄 구성이 달라지므로 key를 바꿔 이전 편집이 엉뚱한 줄에 남지 않게 한다.
        edited = _review_table(shown_rows, columns, f"{key}_{int(only_suggested)}")
        to_save = [
            {"id": int(r["id"]), "vat_status": r["부가세"]}
            for r in edited.to_dict("records")
            if r["부가세"] and r["부가세"] != UNKNOWN
        ]
        if st.button(f"💾 부가세 여부 저장 ({len(to_save):,}건)", type="primary", disabled=not to_save, key=f"{key}_save"):
            try:
                saved = apply_fn(to_save)
                st.session_state["vat_msg"] = f"{title.split('. ', 1)[-1]}: {saved:,}건의 부가세 여부를 저장했습니다."
                st.session_state["vat_version"] += 1
                st.rerun()
            except ValidationError as e:
                st.error(str(e))
    if review["unclassified_count"]:
        st.caption(unclassified_hint.format(n=review["unclassified_count"]))


_review_section(
    "1. 통장 거래",
    vat_service.get_bank_review(start_str, end_str),
    {
        "거래일자": lambda r: r["transaction_date"],
        "거래내용": lambda r: r["description"],
        "거래처": lambda r: r["client_name"] or "",
        "구분": lambda r: TYPE_LABELS[r["transaction_type"]],
        "금액": lambda r: f"{format_amount(r['amount'])}원",
        "회계구분": lambda r: r["accounting_type"],
    },
    "vat_bank",
    vat_service.apply_bank_vat,
    "회계구분이 '미분류'인 거래 {n:,}건은 금액만 보고 추천하지 않습니다 (이자·가수금 같은 입금도 11로 나누어떨어질 수 "
    "있기 때문). 거래내역에서 회계구분을 매출/비용으로 정하면 추천됩니다.",
)

st.divider()

_review_section(
    "2. 법인카드 사용내역",
    vat_service.get_card_review(start_str, end_str),
    {
        "이용일자": lambda r: r["use_date"],
        "가맹점명": lambda r: r["merchant"],
        "청구금액": lambda r: f"{format_amount(r['amount'])}원",
        "회계구분": lambda r: r["accounting_type"],
    },
    "vat_card",
    vat_service.apply_card_vat,
    "회계구분이 '미분류'인 카드 사용내역 {n:,}건은 금액만 보고 추천하지 않습니다. 법인카드 화면에서 회계구분을 정하면 추천됩니다.",
)

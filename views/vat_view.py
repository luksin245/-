from datetime import date

import pandas as pd
import streamlit as st

from services import transaction_service, vat_service
from utils.formatting import format_amount
from utils.validators import ValidationError

st.title("🧾 부가세 정리")
st.caption(
    "통장·카드 금액은 그대로 두고, 부가세 여부가 '과세'(금액에 부가세 10% 포함)인 건만 공급가액과 부가세로 나눠 "
    "계산합니다. 아래 예상 부가세는 **참고용**입니다 - 실제 신고는 홈택스의 세금계산서·카드 자료로 세무사가 하며, "
    "접대비처럼 공제받지 못하는 매입세액도 여기서는 구분하지 않습니다."
)

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
        f"이 기간에 부가세 여부가 아직 '불명'인 매출·비용 {summary['unknown_count']:,}건은 위 계산에서 빠져 있습니다. "
        "아래에서 정리하면 더 정확해집니다."
    )

st.divider()


def _review_section(title: str, review: dict, key: str, apply_fn, name_label: str) -> None:
    """상대방(거래처·가맹점)별 묶음 표. 묶음마다 부가세 여부를 한 번만 정하면 그 안의 거래 전부에 저장된다."""
    st.subheader(title)
    groups = review["groups"]
    if not groups:
        st.success("부가세 여부가 '불명'인 항목이 없습니다.")
        return

    no_suggestion = [g for g in groups if not g["suggested_vat_status"]]
    st.caption(
        f"기간과 상관없이 아직 '불명'인 {review['row_count']:,}건을 {len(groups):,}개 묶음으로 모았습니다. "
        "추천값이 미리 채워져 있으니 **틀린 묶음만 바꾸고 저장 버튼을 한 번** 누르면 됩니다. "
        "한 번 정한 거래처·가맹점은 다음부터 같은 값으로 추천됩니다."
    )
    if no_suggestion:
        st.info(
            f"추천할 근거가 없는 묶음 {len(no_suggestion):,}개가 표 맨 위에 있습니다. "
            "직접 고르거나, 모르면 '불명'으로 두세요 ('불명'은 저장하지 않습니다)."
        )

    table = pd.DataFrame(
        [
            {
                name_label: g["label"],
                "구분": g["direction"],
                "건수": g["count"],
                "합계": f"{format_amount(g['total'])}원",
                "기간": g["period"],
                "부가세": g["suggested_vat_status"] or UNKNOWN,
                "추천 근거": g["reason"] or "-",
            }
            for g in groups
        ]
    )
    columns = [name_label, "구분", "건수", "합계", "기간", "부가세", "추천 근거"]
    if key == "vat_card":
        columns.remove("구분")
    edited = st.data_editor(
        table,
        column_order=columns,
        column_config={
            "부가세": st.column_config.SelectboxColumn(
                "부가세", options=VAT_OPTIONS, required=True,
                help="'과세' = 금액에 부가세 10% 포함. '해당없음' = 부가세와 무관한 돈(이자·세금·가수금 등).",
            ),
        },
        disabled=[c for c in columns if c != "부가세"],
        hide_index=True,
        use_container_width=True,
        key=f"{key}_groups_{st.session_state['vat_version']}",
    )

    to_save = []
    for group, status in zip(groups, edited["부가세"].tolist()):
        if status and status != UNKNOWN:
            to_save.extend({"id": i, "vat_status": status} for i in group["ids"])

    if st.button(
        f"💾 이대로 한꺼번에 저장 ({len(to_save):,}건)", type="primary", disabled=not to_save, key=f"{key}_save"
    ):
        try:
            saved = apply_fn(to_save)
            st.session_state["vat_msg"] = f"{title.split('. ', 1)[-1]}: {saved:,}건의 부가세 여부를 저장했습니다."
            st.session_state["vat_version"] += 1
            st.rerun()
        except ValidationError as e:
            st.error(str(e))

    with st.expander("묶음 안의 거래 하나하나 보기"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        name_label: g["label"],
                        "날짜": r["_date"],
                        "내용": r.get("description") or r.get("merchant"),
                        "금액": f"{format_amount(r['amount'])}원",
                        "회계구분": r["accounting_type"],
                        "추천": g["suggested_vat_status"] or "-",
                    }
                    for g in groups
                    for r in g["rows"]
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.caption("묶음 안에서 한 건만 다르게 정하려면 거래내역(또는 법인카드) 화면에서 그 거래만 수정하세요.")


_review_section("1. 통장 거래", vat_service.get_bank_review(), "vat_bank", vat_service.apply_bank_vat, "거래처/내용")

st.divider()

_review_section("2. 법인카드 사용내역", vat_service.get_card_review(), "vat_card", vat_service.apply_card_vat, "가맹점")

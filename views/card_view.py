from datetime import date, timedelta

import pandas as pd
import streamlit as st

from services import account_service, card_service, category_service, transaction_service
from utils.formatting import format_amount, parse_amount
from utils.validators import ValidationError

st.title("💳 법인카드")
st.caption(
    "카드사 명세서의 사용내역을 등록하고, 통장에 찍힌 카드값 결제(예: '카드결 신한카드법인') 출금과 "
    "맞춰봅니다. 카드 사용내역은 통장 거래와 따로 저장되어 통장 기준 총수입·총지출·잔액에는 섞이지 않고, "
    "회계구분이 '비용'인 건만 대시보드 총비용에 더해집니다."
)

if msg := st.session_state.pop("card_msg", None):
    st.success(msg)

ACCOUNTING_OPTIONS = transaction_service.ACCOUNTING_TYPE_OPTIONS
HEADER_KEYS = ("card_name", "card_start", "card_end", "card_total")
st.session_state.setdefault("card_entry_version", 0)
st.session_state.setdefault("card_detail_version", 0)
# 저장 성공 후에는 위젯이 만들어지기 전(여기)에서 입력칸을 비워야 기본값으로 돌아간다.
if st.session_state.pop("card_reset_header", False):
    for key in HEADER_KEYS:
        st.session_state.pop(key, None)


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _empty_entry_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "이용일자": pd.Series([], dtype="datetime64[ns]"),
            "가맹점명": pd.Series([], dtype="object"),
            "청구금액": pd.Series([], dtype="Int64"),
            "카테고리": pd.Series([], dtype="object"),
            "회계구분": pd.Series([], dtype="object"),
            "계정과목": pd.Series([], dtype="object"),
            "메모": pd.Series([], dtype="object"),
        }
    )


# 선택지는 활성 항목만. 이름→id 변환은 비활성 포함 전체로 (과거 명세서 분류 표시용).
active_expense_categories = category_service.get_expense_categories()
all_expense_categories = category_service.list_categories_admin(status="all", type_filter="expense")
category_name_to_id = {c["name"]: c["id"] for c in all_expense_categories}
category_id_to_name = {c["id"]: c["name"] for c in all_expense_categories}
active_accounts = account_service.get_accounts()
all_accounts = account_service.list_accounts_admin(status="all")
account_name_to_id = {a["name"]: a["id"] for a in all_accounts}
account_id_to_name = {a["id"]: a["name"] for a in all_accounts}


def _class_column_config(category_options: list[str], account_options: list[str]) -> dict:
    return {
        "카테고리": st.column_config.SelectboxColumn("카테고리", options=category_options),
        "회계구분": st.column_config.SelectboxColumn(
            "회계구분", options=ACCOUNTING_OPTIONS, default=card_service.DEFAULT_LINE_ACCOUNTING_TYPE,
            help="카드로 산 물건·서비스는 보통 '비용'입니다. 대표자 개인 사용분 등 확실하지 않으면 '미분류'로 두세요.",
        ),
        "계정과목": st.column_config.SelectboxColumn("계정과목", options=account_options),
        "메모": st.column_config.TextColumn("메모"),
    }


def _row_value(row, column):
    value = row.get(column)
    return None if _is_blank(value) else value


# =====================================================================
# 1. 명세서 등록
# =====================================================================
st.subheader("1. 카드 명세서 등록")
st.caption(
    "카드사 명세서를 보면서 사용내역을 한 줄씩 입력하세요 (표에 마우스를 올리면 오른쪽 위에 나오는 + 버튼으로 줄 추가, "
    "엑셀에서 복사해 붙여넣기도 됩니다). "
    "취소·환불 건은 음수로 입력합니다. 입력 합계가 명세서 총합계와 정확히 같아야 저장됩니다."
)

version = st.session_state["card_entry_version"]
if "card_entry_base" not in st.session_state:
    st.session_state["card_entry_base"] = _empty_entry_df()

last_month_end = date.today().replace(day=1) - timedelta(days=1)
col_card, col_start, col_end, col_total = st.columns([2, 1, 1, 1])
st.session_state.setdefault("card_name", card_service.DEFAULT_CARD_NAME)
st.session_state.setdefault("card_start", last_month_end.replace(day=1))
st.session_state.setdefault("card_end", last_month_end)
st.session_state.setdefault("card_total", "")
with col_card:
    card_name = st.text_input("카드 이름", key="card_name")
with col_start:
    period_start = st.date_input("이용기간 시작", key="card_start")
with col_end:
    period_end = st.date_input("이용기간 종료", key="card_end")
with col_total:
    billed_total_text = st.text_input("명세서 총합계(원)", key="card_total", placeholder="예: 86,757")

entry_config = {
    "이용일자": st.column_config.DateColumn("이용일자", format="YYYY-MM-DD"),
    "가맹점명": st.column_config.TextColumn("가맹점명"),
    "청구금액": st.column_config.NumberColumn("청구금액(원)", step=1, format="%d"),
    **_class_column_config(
        [c["name"] for c in active_expense_categories], [a["name"] for a in active_accounts]
    ),
}
entry_df = st.data_editor(
    st.session_state["card_entry_base"],
    num_rows="dynamic",
    column_config=entry_config,
    hide_index=True,
    use_container_width=True,
    key=f"card_entry_{version}",
)

filled_rows = [
    r for r in entry_df.to_dict("records")
    if not (_is_blank(r.get("이용일자")) and _is_blank(r.get("가맹점명")) and _is_blank(r.get("청구금액")))
]
entry_total = sum(int(r["청구금액"]) for r in filled_rows if not _is_blank(r.get("청구금액")))

billed_total = None
if billed_total_text.strip():
    try:
        billed_total = parse_amount(billed_total_text)
    except ValueError as e:
        st.error(str(e))

check_col, info_col = st.columns([1, 2])
with check_col:
    st.metric("입력 합계", f"{format_amount(entry_total)}원", help=f"{len(filled_rows)}건")
with info_col:
    if billed_total is None:
        st.info("명세서 맨 아래 '총합계' 금액을 입력하면 입력 합계와 맞는지 바로 확인합니다.")
    elif billed_total == entry_total:
        st.success(f"명세서 총합계 {format_amount(billed_total)}원과 일치합니다.")
    else:
        st.warning(
            f"명세서 총합계 {format_amount(billed_total)}원과 {format_amount(abs(billed_total - entry_total))}원 차이가 납니다. "
            "금액을 다시 확인하거나 빠진 항목(연회비·수수료·취소 건 등)이 없는지 확인해주세요."
        )

btn_suggest, btn_save = st.columns(2)
with btn_suggest:
    if st.button("✨ 자동분류 규칙으로 빈 칸 채우기", use_container_width=True, disabled=not filled_rows):
        filled = entry_df.copy()
        for idx, row in filled.iterrows():
            merchant = _row_value(row, "가맹점명")
            if not merchant:
                continue
            suggestion = card_service.suggest_for_merchant(str(merchant))
            if suggestion.get("category_id") and _is_blank(row.get("카테고리")):
                filled.at[idx, "카테고리"] = category_id_to_name[suggestion["category_id"]]
            if suggestion.get("account_id") and _is_blank(row.get("계정과목")):
                filled.at[idx, "계정과목"] = account_id_to_name[suggestion["account_id"]]
            if suggestion.get("accounting_type") and (
                _is_blank(row.get("회계구분")) or row.get("회계구분") == card_service.DEFAULT_LINE_ACCOUNTING_TYPE
            ):
                filled.at[idx, "회계구분"] = suggestion["accounting_type"]
        st.session_state["card_entry_base"] = filled
        st.session_state["card_entry_version"] += 1
        st.rerun()
    st.caption("기준정보 관리 → 자동분류 규칙에 등록한 키워드로 추천값만 채웁니다. 저장 전에 확인·수정하세요.")

with btn_save:
    if st.button("💾 명세서 저장", type="primary", use_container_width=True, disabled=not filled_rows):
        try:
            if billed_total is None:
                raise ValidationError("명세서 총합계를 입력해주세요.")
            lines = [
                {
                    "use_date": pd.Timestamp(r["이용일자"]).date() if not _is_blank(r.get("이용일자")) else None,
                    "merchant": "" if _is_blank(r.get("가맹점명")) else str(r["가맹점명"]),
                    "amount": None if _is_blank(r.get("청구금액")) else int(r["청구금액"]),
                    "category_id": category_name_to_id.get(_row_value(r, "카테고리")),
                    "account_id": account_name_to_id.get(_row_value(r, "계정과목")),
                    "accounting_type": _row_value(r, "회계구분") or card_service.DEFAULT_LINE_ACCOUNTING_TYPE,
                    "memo": _row_value(r, "메모"),
                }
                for r in filled_rows
            ]
            card_service.create_statement(card_name, period_start, period_end, billed_total, lines)
            st.session_state["card_entry_base"] = _empty_entry_df()
            st.session_state["card_entry_version"] += 1
            st.session_state["card_reset_header"] = True
            st.session_state["card_msg"] = (
                f"'{card_name.strip()}' {period_start} ~ {period_end} 명세서({len(lines)}건, "
                f"{format_amount(billed_total)}원)를 저장했습니다. 아래에서 통장 카드값 결제와 맞춰보세요."
            )
            st.rerun()
        except ValidationError as e:
            st.error(str(e))

st.divider()

# =====================================================================
# 2. 등록된 명세서
# =====================================================================
st.subheader("2. 등록된 명세서")

statements = card_service.list_statements()
if not statements:
    st.info("아직 등록된 카드 명세서가 없습니다.")
    st.stop()


def _settlement_label(s: dict) -> str:
    if s["settlement_transaction_id"] is None:
        return "미연결"
    return f"연결됨 ({s['settlement_date']} 출금)"


st.dataframe(
    pd.DataFrame(
        [
            {
                "카드": s["card_name"],
                "이용기간": f"{s['period_start']} ~ {s['period_end']}",
                "총합계": f"{format_amount(s['billed_total'])}원",
                "건수": f"{s['line_count']}건",
                "통장 카드값 결제": _settlement_label(s),
            }
            for s in statements
        ]
    ),
    hide_index=True,
    use_container_width=True,
)

selected_idx = st.selectbox(
    "자세히 볼 명세서",
    options=list(range(len(statements))),
    format_func=lambda i: f"{statements[i]['card_name']} · {statements[i]['period_start']} ~ {statements[i]['period_end']} · "
    f"{format_amount(statements[i]['billed_total'])}원",
    key=f"card_statement_select_{st.session_state['card_detail_version']}",
)
statement = statements[selected_idx]
sid = statement["id"]

# ---------- 사용내역 분류 ----------
st.markdown("#### 사용내역 분류")
lines = card_service.get_lines(statement_id=sid)
used_category_names = {category_id_to_name[l["category_id"]] for l in lines if l["category_id"] in category_id_to_name}
used_account_names = {account_id_to_name[l["account_id"]] for l in lines if l["account_id"] in account_id_to_name}
category_options = [c["name"] for c in active_expense_categories]
category_options += sorted(n for n in used_category_names if n not in category_options)
account_options = [a["name"] for a in active_accounts]
account_options += sorted(n for n in used_account_names if n not in account_options)

cls_df = pd.DataFrame(
    [
        {
            "id": l["id"],
            "이용일자": l["use_date"],
            "가맹점명": l["merchant"],
            "청구금액": f"{format_amount(l['amount'])}원",
            "카테고리": category_id_to_name.get(l["category_id"]),
            "회계구분": l["accounting_type"],
            "계정과목": account_id_to_name.get(l["account_id"]),
            "메모": l["memo"] or "",
        }
        for l in lines
    ]
)
edited_cls = st.data_editor(
    cls_df,
    column_order=["이용일자", "가맹점명", "청구금액", "카테고리", "회계구분", "계정과목", "메모"],
    column_config=_class_column_config(category_options, account_options),
    disabled=["이용일자", "가맹점명", "청구금액"],
    hide_index=True,
    use_container_width=True,
    key=f"card_cls_{sid}_{st.session_state['card_detail_version']}",
)
if st.button("분류 저장", key=f"card_cls_save_{sid}"):
    try:
        card_service.update_classifications(
            sid,
            [
                {
                    "id": int(r["id"]),
                    "category_id": category_name_to_id.get(_row_value(r, "카테고리")),
                    "account_id": account_name_to_id.get(_row_value(r, "계정과목")),
                    "accounting_type": _row_value(r, "회계구분") or card_service.DEFAULT_LINE_ACCOUNTING_TYPE,
                    "memo": _row_value(r, "메모"),
                }
                for r in edited_cls.to_dict("records")
            ],
        )
        st.session_state["card_msg"] = "사용내역 분류를 저장했습니다."
        st.session_state["card_detail_version"] += 1
        st.rerun()
    except ValidationError as e:
        st.error(str(e))

# ---------- 통장 카드값 결제 맞춰보기 ----------
st.markdown("#### 통장 카드값 결제 맞춰보기")
if statement["settlement_transaction_id"] is not None:
    st.success(
        f"통장 출금과 연결되어 있습니다: {statement['settlement_date']} · {statement['settlement_description']} · "
        f"{format_amount(statement['settlement_amount'])}원"
    )
    if st.button("연결 해제", key=f"card_unlink_{sid}"):
        card_service.unlink_settlement(sid)
        st.session_state["card_msg"] = (
            "연결을 해제했습니다. 통장 출금의 회계구분은 그대로 남아 있으니 필요하면 거래내역에서 직접 수정하세요."
        )
        st.rerun()
else:
    candidates = card_service.find_settlement_candidates(sid)
    if not candidates:
        st.info(
            f"명세서 총합계({format_amount(statement['billed_total'])}원)와 같은 금액의 통장 출금이 "
            f"이용기간 종료 후 {card_service.SETTLEMENT_SEARCH_DAYS}일 안에 없습니다. "
            "통장 거래를 먼저 등록했는지(통장 가져오기), 명세서 총합계가 맞는지 확인해주세요."
        )
    else:
        cand_idx = st.selectbox(
            "금액이 같은 통장 출금",
            options=list(range(len(candidates))),
            format_func=lambda i: f"{candidates[i]['transaction_date']} · {candidates[i]['description']} · "
            f"{format_amount(candidates[i]['amount'])}원"
            + (" (다른 명세서에 이미 연결됨)" if candidates[i]["linked_elsewhere"] else ""),
            key=f"card_cand_{sid}",
        )
        reclassify = st.checkbox(
            f"이 출금을 회계구분 '{card_service.SETTLEMENT_ACCOUNTING_TYPE}' / 계정과목 "
            f"'{card_service.SETTLEMENT_ACCOUNT_NAME}'으로 변경 (권장)",
            value=True,
            key=f"card_reclassify_{sid}",
            help="카드로 쓴 돈은 위 사용내역에서 비용으로 잡히므로, 카드값을 갚은 통장 출금까지 비용으로 두면 두 번 계산됩니다.",
        )
        if st.button("이 출금과 연결", type="primary", key=f"card_link_{sid}"):
            try:
                card_service.link_settlement(sid, candidates[cand_idx]["id"], reclassify=reclassify)
                st.session_state["card_msg"] = "통장 카드값 결제 출금과 연결했습니다."
                st.rerun()
            except ValidationError as e:
                st.error(str(e))


# ---------- 명세서 삭제 ----------
@st.dialog("카드 명세서 삭제")
def open_delete_statement_dialog(s: dict) -> None:
    st.warning(
        f"{s['card_name']} {s['period_start']} ~ {s['period_end']} 명세서와 사용내역 {s['line_count']}건을 삭제하시겠습니까?\n\n"
        "연결돼 있던 통장 출금 자체는 지워지지 않습니다."
    )
    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button("삭제", type="primary", key="confirm_delete_statement", use_container_width=True):
            card_service.delete_statement(s["id"])
            st.session_state["card_msg"] = "명세서를 삭제했습니다."
            st.session_state["card_detail_version"] += 1
            st.rerun()
    with col_cancel:
        if st.button("취소", key="cancel_delete_statement", use_container_width=True):
            st.rerun()


st.markdown("#### 명세서 삭제")
if st.button("🗑️ 이 명세서 삭제", key=f"card_delete_{sid}"):
    open_delete_statement_dialog(statement)

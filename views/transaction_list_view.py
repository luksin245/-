from datetime import date
from datetime import time as dtime

import pandas as pd
import streamlit as st

from services import category_service, client_service, transaction_service, work_type_service
from utils.formatting import format_amount, parse_amount
from utils.validators import ValidationError

st.title("📋 거래내역")

TYPE_LABELS = {"income": "수입", "expense": "지출"}
TYPE_LABELS_REV = {"수입": "income", "지출": "expense"}

FILTER_KEYS = [
    "list_start_date",
    "list_end_date",
    "list_type",
    "list_category",
    "list_client",
    "list_work_type",
    "list_evidence",
    "list_keyword",
]

# 저장/수정/삭제 직후 rerun으로 다이얼로그가 닫힌 뒤에도 결과 메시지를 보여주기 위한 처리
if st.session_state.pop("list_edit_success", False):
    st.success("거래내역이 수정되었습니다.")
if st.session_state.pop("list_delete_success", False):
    st.success("거래내역이 삭제되었습니다.")

if st.session_state.pop("reset_filters", False):
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)

# 다이얼로그(수정/삭제) 내부에서 rerun()으로 넘어온 "선택 초기화" 요청은
# 여기 최상단에서, 위젯이 다시 만들어지기 전에 처리해야 확실히 반영된다.
if st.session_state.pop("clear_selection", False):
    st.session_state["list_select_key_suffix"] = st.session_state.get("list_select_key_suffix", 0) + 1
st.session_state.setdefault("list_select_key_suffix", 0)

st.session_state.setdefault("list_start_date", None)
st.session_state.setdefault("list_end_date", None)
st.session_state.setdefault("list_type", "전체")
st.session_state.setdefault("list_category", "전체")
st.session_state.setdefault("list_client", "전체")
st.session_state.setdefault("list_work_type", "전체")
st.session_state.setdefault("list_evidence", "전체")
st.session_state.setdefault("list_keyword", "")

income_categories = category_service.get_income_categories()
expense_categories = category_service.get_expense_categories()
all_categories = income_categories + expense_categories
all_clients = client_service.get_clients()
all_work_types = work_type_service.get_work_types()

category_label_to_id: dict[str, int] = {}
category_options = ["전체"]
for c in all_categories:
    label = f"{c['name']} ({TYPE_LABELS[c['type']]})"
    category_label_to_id[label] = c["id"]
    category_options.append(label)

client_name_to_id = {c["name"]: c["id"] for c in all_clients}
client_options = ["전체"] + list(client_name_to_id.keys())

work_type_name_to_id = {w["name"]: w["id"] for w in all_work_types}
work_type_options = ["전체"] + list(work_type_name_to_id.keys())

evidence_options = ["전체"] + transaction_service.EVIDENCE_STATUS_OPTIONS

st.subheader("검색 / 필터")

row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
with row1_col1:
    start_date = st.date_input("시작일", key="list_start_date")
with row1_col2:
    end_date = st.date_input("종료일", key="list_end_date")
with row1_col3:
    type_choice = st.selectbox("수입/지출", ["전체", "수입", "지출"], key="list_type")
with row1_col4:
    category_choice = st.selectbox("카테고리", category_options, key="list_category")

row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
with row2_col1:
    client_choice = st.selectbox("거래처", client_options, key="list_client")
with row2_col2:
    work_type_choice = st.selectbox("업무유형", work_type_options, key="list_work_type")
with row2_col3:
    evidence_choice = st.selectbox("증빙 여부", evidence_options, key="list_evidence")
with row2_col4:
    keyword = st.text_input("거래내용 검색", key="list_keyword", placeholder="예: KT")

if st.button("필터 초기화"):
    st.session_state["reset_filters"] = True
    st.rerun()

filters: dict = {}
if start_date:
    filters["start_date"] = start_date.isoformat()
if end_date:
    filters["end_date"] = end_date.isoformat()
if type_choice != "전체":
    filters["transaction_type"] = TYPE_LABELS_REV[type_choice]
if category_choice != "전체":
    filters["category_id"] = category_label_to_id[category_choice]
if client_choice != "전체":
    filters["client_id"] = client_name_to_id[client_choice]
if work_type_choice != "전체":
    filters["work_type_id"] = work_type_name_to_id[work_type_choice]
if evidence_choice != "전체":
    filters["evidence_status"] = evidence_choice
if keyword and keyword.strip():
    filters["keyword"] = keyword.strip()

transactions = transaction_service.list_transactions(filters)
summary = transaction_service.get_summary(filters)

st.subheader("검색 결과 요약")
sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
sum_col1.metric("조회 건수", f"{summary['count']:,}건")
sum_col2.metric("총수입", f"{format_amount(summary['total_income'])}원")
sum_col3.metric("총지출", f"{format_amount(summary['total_expense'])}원")
sum_col4.metric("순금액", f"{format_amount(summary['net_amount'])}원")

st.divider()
st.subheader("거래 목록")


@st.dialog("거래 수정")
def open_edit_dialog(tx: dict) -> None:
    tx_id = tx["id"]

    trade_date = st.date_input(
        "거래일자 *", value=date.fromisoformat(tx["transaction_date"]), key=f"edit_date_{tx_id}"
    )

    existing_time = dtime.fromisoformat(tx["transaction_time"]) if tx["transaction_time"] else None
    has_time = st.checkbox("거래시간 입력", value=existing_time is not None, key=f"edit_has_time_{tx_id}")
    trade_time = None
    if has_time:
        time_value = st.time_input("거래시간", value=existing_time or dtime(0, 0), key=f"edit_time_{tx_id}")
        trade_time = time_value.strftime("%H:%M:%S")

    type_options = ["수입", "지출"]
    type_label = st.radio(
        "수입/지출 *",
        type_options,
        index=type_options.index(TYPE_LABELS[tx["transaction_type"]]),
        horizontal=True,
        key=f"edit_type_{tx_id}",
    )
    transaction_type = TYPE_LABELS_REV[type_label]

    description = st.text_input("거래내용 *", value=tx["description"], key=f"edit_desc_{tx_id}")
    amount_text = st.text_input(
        "금액 *", value=format_amount(tx["amount"]), key=f"edit_amount_{tx_id}"
    )
    balance_text = st.text_input(
        "잔액",
        value=format_amount(tx["balance"]) if tx["balance"] is not None else "",
        key=f"edit_balance_{tx_id}",
    )

    # 수입/지출 유형에 맞는 카테고리만 선택지로 제공한다.
    # 유형이 바뀌어 기존 카테고리가 새 목록에 없으면 자동으로 "(선택 안함)"으로 비운다.
    categories = income_categories if transaction_type == "income" else expense_categories
    category_names = [c["name"] for c in categories]
    category_select_options = ["(선택 안함)"] + category_names
    default_category = tx["category_name"] if tx["category_name"] in category_names else "(선택 안함)"
    category_choice = st.selectbox(
        "카테고리",
        category_select_options,
        index=category_select_options.index(default_category),
        key=f"edit_category_{tx_id}_{transaction_type}",
    )

    client_names = [c["name"] for c in all_clients]
    client_select_options = ["(선택 안함)"] + client_names
    default_client = tx["client_name"] if tx["client_name"] in client_names else "(선택 안함)"
    client_choice = st.selectbox(
        "거래처",
        client_select_options,
        index=client_select_options.index(default_client),
        key=f"edit_client_{tx_id}",
    )

    work_type_names = [w["name"] for w in all_work_types]
    work_type_select_options = ["(선택 안함)"] + work_type_names
    default_work_type = tx["work_type_name"] if tx["work_type_name"] in work_type_names else "(선택 안함)"
    work_type_choice = st.selectbox(
        "업무유형",
        work_type_select_options,
        index=work_type_select_options.index(default_work_type),
        key=f"edit_work_type_{tx_id}",
    )

    vat_status = st.selectbox(
        "부가세 여부",
        transaction_service.VAT_STATUS_OPTIONS,
        index=transaction_service.VAT_STATUS_OPTIONS.index(tx["vat_status"]),
        key=f"edit_vat_{tx_id}",
    )
    evidence_status = st.selectbox(
        "증빙 여부",
        transaction_service.EVIDENCE_STATUS_OPTIONS,
        index=transaction_service.EVIDENCE_STATUS_OPTIONS.index(tx["evidence_status"]),
        key=f"edit_evidence_{tx_id}",
    )
    memo = st.text_area("메모", value=tx["memo"] or "", key=f"edit_memo_{tx_id}")

    st.caption("* 표시 항목은 필수입니다.")

    if st.button("저장", type="primary", key=f"edit_submit_{tx_id}"):
        try:
            amount = parse_amount(amount_text)
            balance = parse_amount(balance_text) if balance_text and balance_text.strip() else None

            category_id = None
            if category_choice != "(선택 안함)":
                category_id = next(c["id"] for c in categories if c["name"] == category_choice)

            client_id = None
            if client_choice != "(선택 안함)":
                client_id = next(c["id"] for c in all_clients if c["name"] == client_choice)

            work_type_id = None
            if work_type_choice != "(선택 안함)":
                work_type_id = next(w["id"] for w in all_work_types if w["name"] == work_type_choice)

            transaction_service.update_transaction(
                transaction_id=tx_id,
                transaction_date=str(trade_date),
                transaction_type=transaction_type,
                description=description,
                amount=amount,
                transaction_time=trade_time,
                balance=balance,
                category_id=category_id,
                client_id=client_id,
                work_type_id=work_type_id,
                vat_status=vat_status,
                evidence_status=evidence_status,
                memo=memo.strip() if memo else None,
            )
            st.session_state["list_edit_success"] = True
            # 수정 후 목록 순서/내용이 바뀔 수 있으므로 선택 상태를 비워
            # 엉뚱한 거래가 선택된 채로 남지 않게 한다.
            st.session_state["clear_selection"] = True
            st.rerun()
        except (ValidationError, ValueError) as e:
            st.error(str(e))


@st.dialog("거래 삭제 확인")
def open_delete_dialog(tx: dict) -> None:
    subject = tx["client_name"] or tx["description"]
    st.warning(
        f"{tx['transaction_date']} / {subject} / {format_amount(tx['amount'])}원 거래를 삭제하시겠습니까?"
    )
    st.caption(f"거래내용: {tx['description']}")

    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button("삭제", type="primary", key=f"confirm_delete_{tx['id']}", use_container_width=True):
            transaction_service.delete_transaction(tx["id"])
            st.session_state["list_delete_success"] = True
            # 삭제로 목록이 한 칸씩 당겨지면서 같은 인덱스가 다른 거래를
            # 가리킬 수 있으므로 선택 상태를 비운다.
            st.session_state["clear_selection"] = True
            st.rerun()
    with col_cancel:
        if st.button("취소", key=f"cancel_delete_{tx['id']}", use_container_width=True):
            st.rerun()


if not transactions:
    st.info("조건에 해당하는 거래내역이 없습니다.")
else:
    df = pd.DataFrame(transactions)
    df["구분"] = df["transaction_type"].map(TYPE_LABELS)
    df["금액"] = df["amount"].apply(lambda v: f"{format_amount(v)}원")
    df["카테고리"] = df["category_name"].fillna("")
    df["거래처"] = df["client_name"].fillna("")
    df["업무유형"] = df["work_type_name"].fillna("")
    df["부가세"] = df["vat_status"]
    df["증빙"] = df["evidence_status"]
    df["메모"] = df["memo"].fillna("")
    df["거래일자"] = df["transaction_date"]
    df["거래시간"] = df["transaction_time"].fillna("")
    df["거래내용"] = df["description"]

    display_columns = [
        "거래일자", "거래시간", "거래내용", "구분", "금액",
        "카테고리", "거래처", "업무유형", "부가세", "증빙", "메모",
    ]

    st.dataframe(
        df,
        column_order=display_columns,
        hide_index=True,
        use_container_width=True,
    )

    st.caption("아래에서 수정 또는 삭제할 거래를 선택하세요.")

    def _format_tx_option(i: int | None) -> str:
        if i is None:
            return "(선택 안함)"
        tx = transactions[i]
        return (
            f"{tx['transaction_date']} · {tx['description']} · "
            f"{TYPE_LABELS[tx['transaction_type']]} {format_amount(tx['amount'])}원"
        )

    selected_idx = st.selectbox(
        "수정 또는 삭제할 거래 선택",
        options=list(range(len(transactions))),
        format_func=_format_tx_option,
        index=None,
        placeholder="(선택 안함)",
        key=f"list_selected_idx_{st.session_state['list_select_key_suffix']}",
    )
    selected_tx = transactions[selected_idx] if selected_idx is not None else None

    col_edit, col_delete = st.columns(2)
    with col_edit:
        if st.button("✏️ 선택한 거래 수정", disabled=selected_tx is None, use_container_width=True):
            open_edit_dialog(selected_tx)
    with col_delete:
        if st.button("🗑️ 선택한 거래 삭제", disabled=selected_tx is None, use_container_width=True):
            open_delete_dialog(selected_tx)

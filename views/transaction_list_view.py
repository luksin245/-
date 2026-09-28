from datetime import date
from datetime import time as dtime

import pandas as pd
import streamlit as st

from services import (
    account_service,
    category_service,
    client_service,
    export_service,
    transaction_service,
    work_type_service,
)
from utils.formatting import format_amount, parse_amount
from utils.validators import ValidationError
from utils.vat import vat_of

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
    "list_accounting_type",
    "list_evidence",
    "list_keyword",
]

# 저장/수정/삭제 직후 rerun으로 다이얼로그가 닫힌 뒤에도 결과 메시지를 보여주기 위한 처리
if st.session_state.pop("list_edit_success", False):
    st.success("거래내역이 수정되었습니다.")
if (bulk_edited := st.session_state.pop("list_bulk_edit_result", None)) is not None:
    st.success(f"{bulk_edited:,}건의 거래를 한꺼번에 수정했습니다.")
if bulk_result := st.session_state.pop("list_bulk_delete_result", None):
    st.success(
        f"{bulk_result['deleted']:,}건을 삭제했습니다. 삭제 직전 데이터는 "
        f"'{bulk_result['backup_filename']}'(으)로 자동 백업되었습니다 "
        "(잘못 지웠다면 설정 → 백업 목록 / 복구에서 되돌릴 수 있습니다)."
    )

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
st.session_state.setdefault("list_accounting_type", "전체")
st.session_state.setdefault("list_evidence", "전체")
st.session_state.setdefault("list_keyword", "")

# 거래등록/거래수정 화면의 "선택 가능한" 기준정보는 활성 항목만 대상으로 한다.
income_categories = category_service.get_income_categories()
expense_categories = category_service.get_expense_categories()
all_clients = client_service.get_clients()
all_work_types = work_type_service.get_work_types()
all_accounts = account_service.get_accounts()

# 필터는 "과거 거래를 찾아보는" 용도이므로 비활성 기준정보도 포함해서 보여준다
# (예: 지금은 비활성화된 거래처로 옛날 거래를 검색하고 싶을 수 있다).
filter_categories = category_service.list_categories_admin(status="all")
filter_clients = client_service.list_clients_admin(status="all")
filter_work_types = work_type_service.list_work_types_admin(status="all")


def _status_suffix(row: dict) -> str:
    return "" if row["is_active"] else " (비활성)"


category_label_to_id: dict[str, int] = {}
category_options = ["전체"]
for c in filter_categories:
    label = f"{c['name']} ({TYPE_LABELS[c['type']]}){_status_suffix(c)}"
    category_label_to_id[label] = c["id"]
    category_options.append(label)

client_label_to_id: dict[str, int] = {}
client_options = ["전체"]
for c in filter_clients:
    label = f"{c['name']}{_status_suffix(c)}"
    client_label_to_id[label] = c["id"]
    client_options.append(label)

work_type_label_to_id: dict[str, int] = {}
work_type_options = ["전체"]
for w in filter_work_types:
    label = f"{w['name']}{_status_suffix(w)}"
    work_type_label_to_id[label] = w["id"]
    work_type_options.append(label)

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

accounting_type_options = ["전체"] + transaction_service.ACCOUNTING_TYPE_OPTIONS
row3_col1, _, _, _ = st.columns(4)
with row3_col1:
    accounting_type_choice = st.selectbox(
        "회계구분", accounting_type_options, key="list_accounting_type",
        help="입금/출금(통장 방향)과는 다른 개념입니다. 매출/비용으로 분류된 거래만 좁혀볼 때 사용하세요.",
    )

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
    filters["client_id"] = client_label_to_id[client_choice]
if work_type_choice != "전체":
    filters["work_type_id"] = work_type_label_to_id[work_type_choice]
if accounting_type_choice != "전체":
    filters["accounting_type"] = accounting_type_choice
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

st.caption("아래 다운로드 버튼은 현재 적용된 검색/필터 결과만 대상으로 합니다.")
export_col1, export_col2, export_col3 = st.columns(3)
export_filename_stamp = date.today().isoformat()
with export_col1:
    st.download_button(
        "⬇️ CSV 다운로드",
        data=export_service.export_general_csv(filters),
        file_name=f"거래내역_{export_filename_stamp}.csv",
        mime="text/csv",
        use_container_width=True,
    )
with export_col2:
    st.download_button(
        "⬇️ Excel 다운로드",
        data=export_service.export_general_excel(filters),
        file_name=f"거래내역_{export_filename_stamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with export_col3:
    st.download_button(
        "⬇️ 세무사 전달용 Excel",
        data=export_service.export_tax_excel(filters),
        file_name=f"세무사전달용_{export_filename_stamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

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

    # 수입/지출 유형에 맞는 "활성" 카테고리만 선택지로 제공한다.
    # 유형이 바뀌어 기존 카테고리가 새 목록에 없으면 자동으로 "(선택 안함)"으로 비운다.
    # 단, 유형을 바꾸지 않았고 기존 카테고리가 비활성 상태라면, 그 값이 목록에서
    # 사라지지 않도록 "(비활성)" 표시를 붙여 선택지에 포함시킨다.
    categories = income_categories if transaction_type == "income" else expense_categories
    if (
        tx["transaction_type"] == transaction_type
        and tx["category_id"] is not None
        and tx["category_id"] not in {c["id"] for c in categories}
    ):
        inactive_category = category_service.get_category(tx["category_id"])
        if inactive_category:
            categories = categories + [inactive_category]

    category_name_options = {
        c["name"] if c["is_active"] else f"{c['name']} (비활성)": c for c in categories
    }
    category_select_options = ["(선택 안함)"] + list(category_name_options.keys())
    default_category = next(
        (label for label, c in category_name_options.items() if c["id"] == tx["category_id"]),
        "(선택 안함)",
    )
    category_choice = st.selectbox(
        "카테고리",
        category_select_options,
        index=category_select_options.index(default_category),
        key=f"edit_category_{tx_id}_{transaction_type}",
    )

    clients_for_edit = list(all_clients)
    if tx["client_id"] is not None and tx["client_id"] not in {c["id"] for c in clients_for_edit}:
        inactive_client = client_service.get_client(tx["client_id"])
        if inactive_client:
            clients_for_edit = clients_for_edit + [inactive_client]
    client_name_options = {
        c["name"] if c["is_active"] else f"{c['name']} (비활성)": c for c in clients_for_edit
    }
    client_select_options = ["(선택 안함)"] + list(client_name_options.keys())
    default_client = next(
        (label for label, c in client_name_options.items() if c["id"] == tx["client_id"]),
        "(선택 안함)",
    )
    client_choice = st.selectbox(
        "거래처",
        client_select_options,
        index=client_select_options.index(default_client),
        key=f"edit_client_{tx_id}",
    )

    work_types_for_edit = list(all_work_types)
    if tx["work_type_id"] is not None and tx["work_type_id"] not in {w["id"] for w in work_types_for_edit}:
        inactive_work_type = work_type_service.get_work_type(tx["work_type_id"])
        if inactive_work_type:
            work_types_for_edit = work_types_for_edit + [inactive_work_type]
    work_type_name_options = {
        w["name"] if w["is_active"] else f"{w['name']} (비활성)": w for w in work_types_for_edit
    }
    work_type_select_options = ["(선택 안함)"] + list(work_type_name_options.keys())
    default_work_type = next(
        (label for label, w in work_type_name_options.items() if w["id"] == tx["work_type_id"]),
        "(선택 안함)",
    )
    work_type_choice = st.selectbox(
        "업무유형",
        work_type_select_options,
        index=work_type_select_options.index(default_work_type),
        key=f"edit_work_type_{tx_id}",
    )

    accounting_type = st.selectbox(
        "회계구분",
        transaction_service.ACCOUNTING_TYPE_OPTIONS,
        index=transaction_service.ACCOUNTING_TYPE_OPTIONS.index(tx["accounting_type"]),
        key=f"edit_accounting_type_{tx_id}",
        help="입금/출금(통장 방향)과는 다른 개념입니다. 매출/비용 여부가 명확하지 않으면 '미분류'로 두세요.",
    )

    accounts_for_edit = list(all_accounts)
    if tx["account_id"] is not None and tx["account_id"] not in {a["id"] for a in accounts_for_edit}:
        inactive_account = account_service.get_account(tx["account_id"])
        if inactive_account:
            accounts_for_edit = accounts_for_edit + [inactive_account]
    account_name_options = {
        a["name"] if a["is_active"] else f"{a['name']} (비활성)": a for a in accounts_for_edit
    }
    account_select_options = ["(선택 안함)"] + list(account_name_options.keys())
    default_account = next(
        (label for label, a in account_name_options.items() if a["id"] == tx["account_id"]),
        "(선택 안함)",
    )
    account_choice = st.selectbox(
        "계정과목",
        account_select_options,
        index=account_select_options.index(default_account),
        key=f"edit_account_{tx_id}",
    )

    vat_status = st.selectbox(
        "부가세 여부",
        transaction_service.VAT_STATUS_OPTIONS,
        index=transaction_service.VAT_STATUS_OPTIONS.index(tx["vat_status"]),
        key=f"edit_vat_{tx_id}",
        help="'과세' = 금액에 부가세 10%가 포함됨. 부가세 정리 화면에서 여러 건을 한꺼번에 정할 수도 있습니다.",
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
                category_id = category_name_options[category_choice]["id"]

            client_id = None
            if client_choice != "(선택 안함)":
                client_id = client_name_options[client_choice]["id"]

            work_type_id = None
            if work_type_choice != "(선택 안함)":
                work_type_id = work_type_name_options[work_type_choice]["id"]

            account_id = None
            if account_choice != "(선택 안함)":
                account_id = account_name_options[account_choice]["id"]

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
                account_id=account_id,
                accounting_type=accounting_type,
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


KEEP = "(변경 안 함)"
CLEAR = "(비우기)"


@st.dialog("선택한 거래 한꺼번에 수정")
def open_bulk_edit_dialog(selected: list[dict]) -> None:
    """여러 거래의 분류 항목만 같은 값으로 바꾼다. '(변경 안 함)'으로 둔 항목은 그대로 둔다."""
    st.info(
        f"체크한 {len(selected):,}건의 분류를 한꺼번에 바꿉니다. 바꿀 항목만 고르고 나머지는 "
        f"'{KEEP}'으로 두세요. 날짜·금액·거래내용은 한 건씩 수정해야 합니다 (1건만 체크)."
    )

    def pick(label: str, names: list[str], key: str, clearable: bool = True, help_text: str | None = None) -> str:
        options = [KEEP] + ([CLEAR] if clearable else []) + names
        # 저장 후(선택 초기화 시) 다음에 열 때는 다시 '(변경 안 함)'부터 시작하도록 key에 번호를 붙인다.
        return st.selectbox(label, options, key=f"{key}_{st.session_state['list_select_key_suffix']}", help=help_text)

    types = {t["transaction_type"] for t in selected}
    category_choice = KEEP
    cats = income_categories if types == {"income"} else expense_categories
    if len(types) == 1:
        category_choice = pick(f"카테고리 ({TYPE_LABELS[next(iter(types))]})", [c["name"] for c in cats], "bulk_category")
    else:
        st.caption("수입과 지출이 섞여 있어 카테고리는 바꿀 수 없습니다.")
    client_choice = pick("거래처", [c["name"] for c in all_clients], "bulk_client")
    work_type_choice = pick("업무유형", [w["name"] for w in all_work_types], "bulk_work_type")
    accounting_choice = pick(
        "회계구분", transaction_service.ACCOUNTING_TYPE_OPTIONS, "bulk_accounting_type", clearable=False,
        help_text="입금/출금(통장 방향)과는 다른 개념입니다.",
    )
    account_choice = pick("계정과목", [a["name"] for a in all_accounts], "bulk_account")
    vat_choice = pick("부가세 여부", transaction_service.VAT_STATUS_OPTIONS, "bulk_vat", clearable=False)
    evidence_choice = pick("증빙 여부", transaction_service.EVIDENCE_STATUS_OPTIONS, "bulk_evidence", clearable=False)

    def to_id(choice: str, items: list[dict]):
        return None if choice == CLEAR else next(i["id"] for i in items if i["name"] == choice)

    changes: dict = {}
    if category_choice != KEEP:
        changes["category_id"] = to_id(category_choice, cats)
    if client_choice != KEEP:
        changes["client_id"] = to_id(client_choice, all_clients)
    if work_type_choice != KEEP:
        changes["work_type_id"] = to_id(work_type_choice, all_work_types)
    if account_choice != KEEP:
        changes["account_id"] = to_id(account_choice, all_accounts)
    if accounting_choice != KEEP:
        changes["accounting_type"] = accounting_choice
    if vat_choice != KEEP:
        changes["vat_status"] = vat_choice
    if evidence_choice != KEEP:
        changes["evidence_status"] = evidence_choice

    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button(
            f"{len(selected):,}건 저장", type="primary", disabled=not changes, key="confirm_bulk_edit",
            use_container_width=True,
        ):
            try:
                updated = transaction_service.bulk_update_transactions([t["id"] for t in selected], changes)
                st.session_state["list_bulk_edit_result"] = updated
                st.session_state["clear_selection"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))
    with col_cancel:
        if st.button("취소", key="cancel_bulk_edit", use_container_width=True):
            st.rerun()


@st.dialog("선택한 거래 삭제 확인")
def open_bulk_delete_dialog(selected: list[dict]) -> None:
    income_total = sum(t["amount"] for t in selected if t["transaction_type"] == "income")
    expense_total = sum(t["amount"] for t in selected if t["transaction_type"] == "expense")
    dates = sorted(t["transaction_date"] for t in selected)

    st.warning(f"선택한 {len(selected):,}건의 거래를 삭제하시겠습니까?")
    st.write(f"- 기간: {dates[0]} ~ {dates[-1]}")
    st.write(f"- 수입 합계: {format_amount(income_total)}원")
    st.write(f"- 지출 합계: {format_amount(expense_total)}원")
    st.info(
        "삭제 직전에 현재 데이터 전체를 자동으로 백업합니다. 잘못 지웠다면 "
        "설정 → 백업 목록 / 복구에서 삭제 전 상태로 되돌릴 수 있습니다."
    )

    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button("삭제", type="primary", key="confirm_bulk_delete", use_container_width=True):
            try:
                result = transaction_service.delete_transactions([t["id"] for t in selected])
                st.session_state["list_bulk_delete_result"] = result
                st.session_state["clear_selection"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))
    with col_cancel:
        if st.button("취소", key="cancel_bulk_delete", use_container_width=True):
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
    df["회계구분"] = df["accounting_type"]
    df["계정과목"] = df["account_name"].fillna("")
    df["부가세"] = df["vat_status"]
    df["부가세액"] = [
        f"{format_amount(vat_of(a, s))}원" if s == "과세" else "" for a, s in zip(df["amount"], df["vat_status"])
    ]
    df["증빙"] = df["evidence_status"]
    df["메모"] = df["memo"].fillna("")
    df["거래일자"] = df["transaction_date"]
    df["거래시간"] = df["transaction_time"].fillna("")
    df["거래내용"] = df["description"]

    display_columns = [
        "거래일자", "거래시간", "거래내용", "구분", "금액",
        "카테고리", "거래처", "업무유형", "회계구분", "계정과목", "부가세", "부가세액", "증빙", "메모",
    ]

    # 선택 상태는 "지금 화면에 보이는 목록"에만 유효해야 한다. 필터가 바뀌어 목록이
    # 달라졌는데 예전 체크 상태가 엉뚱한 거래에 남아 있으면 잘못 지울 수 있으므로,
    # 목록 구성(거래 id들)이 바뀌면 위젯 key를 바꿔 체크 상태를 초기화한다.
    select_suffix = st.session_state["list_select_key_suffix"]
    list_signature = hash(tuple(t["id"] for t in transactions))

    st.caption(
        "표 왼쪽 '선택' 칸을 체크한 뒤 아래 버튼을 누르세요. 1건을 체크하면 모든 항목을 수정할 수 있고, "
        "여러 건을 체크하면 회계구분·계정과목·부가세 같은 분류를 한꺼번에 바꿀 수 있습니다."
    )
    select_all = st.checkbox(
        f"현재 검색 결과 전체 선택 ({len(transactions):,}건)",
        key=f"list_select_all_{select_suffix}_{list_signature}",
    )
    table_df = df[["id"] + display_columns].copy()
    table_df.insert(0, "선택", select_all)

    edited_df = st.data_editor(
        table_df,
        column_order=["선택"] + display_columns,
        column_config={"선택": st.column_config.CheckboxColumn("선택", default=False)},
        disabled=display_columns,
        hide_index=True,
        use_container_width=True,
        key=f"list_editor_{select_suffix}_{list_signature}_{int(select_all)}",
    )
    checked_ids = set(edited_df.loc[edited_df["선택"].astype(bool), "id"].tolist())
    checked_transactions = [t for t in transactions if t["id"] in checked_ids]

    col_edit, col_delete = st.columns(2)
    with col_edit:
        edit_label = (
            "✏️ 선택한 거래 수정" if len(checked_transactions) <= 1
            else f"✏️ 선택한 {len(checked_transactions):,}건 한꺼번에 수정"
        )
        if st.button(edit_label, disabled=not checked_transactions, key="edit_checked_btn", use_container_width=True):
            if len(checked_transactions) == 1:
                open_edit_dialog(checked_transactions[0])
            else:
                open_bulk_edit_dialog(checked_transactions)
    with col_delete:
        if st.button(
            f"🗑️ 선택한 {len(checked_transactions):,}건 삭제",
            disabled=not checked_transactions,
            key="bulk_delete_btn",
            use_container_width=True,
        ):
            open_bulk_delete_dialog(checked_transactions)

import time
from datetime import date

import streamlit as st

from services import category_service, client_service, transaction_service, work_type_service
from utils.formatting import parse_amount
from utils.validators import ValidationError

st.title("📝 거래등록")

# 저장 직후 rerun으로 폼이 초기화된 뒤에도 성공 메시지를 보여주기 위한 처리
if st.session_state.get("show_save_success"):
    st.success("거래내역이 저장되었습니다.")
    del st.session_state["show_save_success"]

if "form_key_suffix" not in st.session_state:
    st.session_state.form_key_suffix = 0

suffix = st.session_state.form_key_suffix


def field_key(name: str) -> str:
    # 저장 성공 시 suffix를 증가시켜 위젯 key를 바꾸면
    # 모든 입력값이 기본값으로 초기화된 새 위젯이 된다 (폼 리셋 효과).
    return f"{name}_{suffix}"


income_categories = category_service.get_income_categories()
expense_categories = category_service.get_expense_categories()
work_types = work_type_service.get_work_types()
clients = client_service.get_clients()

col1, col2 = st.columns(2)

with col1:
    trade_date = st.date_input("거래일자 *", value=date.today(), key=field_key("date"))

    has_time = st.checkbox("거래시간 입력", value=False, key=field_key("has_time"))
    trade_time = None
    if has_time:
        trade_time_value = st.time_input("거래시간", key=field_key("time"))
        trade_time = trade_time_value.strftime("%H:%M:%S")

    type_label = st.radio("수입/지출 *", ["수입", "지출"], horizontal=True, key=field_key("type"))
    transaction_type = "income" if type_label == "수입" else "expense"

    description = st.text_input(
        "거래내용 *", key=field_key("description"), placeholder="예: OO기업 자문료 입금"
    )

    amount_text = st.text_input(
        "금액 *", key=field_key("amount"), placeholder="예: 500,000"
    )
    balance_text = st.text_input(
        "잔액", key=field_key("balance"), placeholder="예: 12,345,000 (선택)"
    )

with col2:
    categories = income_categories if transaction_type == "income" else expense_categories
    category_options = ["(선택 안함)"] + [c["name"] for c in categories]
    # key에 transaction_type을 포함시켜, 수입/지출 전환 시 이전 선택값이
    # 새 옵션 목록에 없어 발생하는 위젯 오류를 방지하고 선택값도 자동으로 비운다.
    category_choice = st.selectbox(
        "카테고리", category_options, key=field_key(f"category_{transaction_type}")
    )

    client_names = [c["name"] for c in clients]
    client_options = ["(선택 안함)", "+ 새 거래처 입력"] + client_names
    client_choice = st.selectbox("거래처", client_options, key=field_key("client"))
    new_client_name = ""
    if client_choice == "+ 새 거래처 입력":
        new_client_name = st.text_input("새 거래처명", key=field_key("new_client"))

    work_type_options = ["(선택 안함)"] + [w["name"] for w in work_types]
    work_type_choice = st.selectbox("업무유형", work_type_options, key=field_key("work_type"))

    vat_status = st.selectbox(
        "부가세 여부",
        transaction_service.VAT_STATUS_OPTIONS,
        index=transaction_service.VAT_STATUS_OPTIONS.index(transaction_service.DEFAULT_VAT_STATUS),
        key=field_key("vat"),
    )
    evidence_status = st.selectbox(
        "증빙 여부",
        transaction_service.EVIDENCE_STATUS_OPTIONS,
        index=transaction_service.EVIDENCE_STATUS_OPTIONS.index(
            transaction_service.DEFAULT_EVIDENCE_STATUS
        ),
        key=field_key("evidence"),
    )

    memo = st.text_area("메모", key=field_key("memo"))

st.caption("* 표시 항목은 필수입니다.")

submitted = st.button("저장", type="primary", key=field_key("submit"))

if submitted:
    try:
        amount = parse_amount(amount_text)
        balance = parse_amount(balance_text) if balance_text and balance_text.strip() else None

        category_id = None
        if category_choice != "(선택 안함)":
            category_id = next(c["id"] for c in categories if c["name"] == category_choice)

        client_id = None
        if client_choice == "+ 새 거래처 입력":
            if new_client_name and new_client_name.strip():
                client_id = client_service.get_or_create_client(new_client_name)
        elif client_choice != "(선택 안함)":
            client_id = next(c["id"] for c in clients if c["name"] == client_choice)

        work_type_id = None
        if work_type_choice != "(선택 안함)":
            work_type_id = next(w["id"] for w in work_types if w["name"] == work_type_choice)

        # 동일 버튼 연속 클릭으로 인한 중복 저장 방지 (5초 이내 동일 내용 재저장 차단)
        signature = (
            str(trade_date),
            trade_time,
            description.strip() if description else description,
            transaction_type,
            amount,
            balance,
        )
        last_signature = st.session_state.get("last_saved_signature")
        last_saved_at = st.session_state.get("last_saved_at", 0)

        if last_signature == signature and (time.time() - last_saved_at) < 5:
            st.warning("방금 동일한 내용의 거래를 이미 저장했습니다. 중복 저장을 방지하기 위해 다시 저장하지 않았습니다.")
        else:
            transaction_service.create_transaction(
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
                source_type="manual",
            )

            st.session_state["last_saved_signature"] = signature
            st.session_state["last_saved_at"] = time.time()
            st.session_state["show_save_success"] = True
            st.session_state.form_key_suffix += 1
            st.rerun()

    except (ValidationError, ValueError) as e:
        st.error(str(e))

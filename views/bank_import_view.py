from datetime import date
from datetime import time as dtime

import streamlit as st

from services import (
    account_service,
    category_service,
    client_service,
    import_service,
    transaction_service,
    vat_service,
    work_type_service,
)
from services.ocr.base import STATUS_NEEDS_REVIEW, STATUS_OK, STATUS_SUSPECTED_DUPLICATE
from utils.formatting import format_amount, parse_amount
from utils.validators import ValidationError
from utils.vat import split_vat

st.title("🏦 통장 가져오기")
st.caption(
    "통장 거래내역 이미지(PNG/JPG)나 PDF를 업로드하면 OCR로 거래 후보를 추출합니다. "
    "추출된 값은 자동으로 저장되지 않으며, 아래 검토 화면에서 직접 확인/수정한 뒤 저장해야만 "
    "실제 거래로 등록됩니다. 업로드한 원본 파일은 OCR 처리 직후 즉시 삭제되며 보관되지 않습니다."
)

STATUS_BADGE = {
    STATUS_OK: "✅ 정상",
    STATUS_NEEDS_REVIEW: "⚠️ 확인필요",
    STATUS_SUSPECTED_DUPLICATE: "🔁 중복의심",
}

if st.session_state.pop("import_upload_success", False):
    st.success("OCR 처리가 완료되었습니다. 아래에서 검토 후 저장해주세요.")
if st.session_state.pop("import_save_success", False):
    st.success("거래내역이 저장되었습니다.")
if st.session_state.pop("import_discard_success", False):
    st.info("선택한 항목을 제외했습니다.")

st.session_state.setdefault("import_upload_key_suffix", 0)

# ---------- 업로드 ----------
st.subheader("1. 파일 업로드")

uploaded_files = st.file_uploader(
    "통장 거래내역 파일 선택 (PNG/JPG/JPEG/PDF, 여러 개 선택 가능)",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True,
    key=f"import_uploader_{st.session_state['import_upload_key_suffix']}",
)

if st.button("OCR 실행", type="primary", disabled=not uploaded_files):
    errors = []
    for f in uploaded_files:
        try:
            import_service.process_uploaded_file(f.getvalue(), f.name)
        except ValidationError as e:
            errors.append(f"{f.name}: {e}")
    for e in errors:
        st.error(e)
    st.session_state["import_upload_success"] = True
    st.session_state["import_upload_key_suffix"] += 1
    st.rerun()

st.divider()

# ---------- 검토 대상 문서 선택 ----------
st.subheader("2. 검토 대상 선택")

documents = import_service.list_documents()
if not documents:
    st.info("검토 대기 중인 업로드 문서가 없습니다.")
    st.stop()


def _format_doc_option(i: int | None) -> str:
    if i is None:
        return "(선택 안함)"
    d = documents[i]
    return f"{d['file_name']} (업로드: {d['uploaded_at']})"


selected_doc_idx = st.selectbox(
    "검토할 업로드 문서",
    options=list(range(len(documents))),
    format_func=_format_doc_option,
    index=0,
)
selected_doc = documents[selected_doc_idx]

if st.button("🗑️ 이 문서 전체 취소 (모든 후보 삭제)"):
    import_service.discard_document(selected_doc["id"])
    st.session_state["import_discard_success"] = True
    st.rerun()

st.divider()

# ---------- 검토 화면 ----------
st.subheader("3. 거래 후보 검토")
st.caption(
    "'확인필요'/'중복의심' 항목은 자동으로 저장되지 않습니다. 값을 직접 확인/수정한 뒤 "
    "개별적으로 저장하거나, 체크박스로 선택해 '선택한 거래 저장'을 눌러주세요."
)

income_categories = category_service.get_income_categories()
expense_categories = category_service.get_expense_categories()
all_clients = client_service.get_clients()
all_work_types = work_type_service.get_work_types()
all_accounts = account_service.get_accounts()

lines = [l for l in import_service.get_review_lines(selected_doc["id"]) if not l["is_confirmed"]]

if not lines:
    st.info("이 문서는 더 이상 검토할 항목이 없습니다.")
    st.stop()


def _save_review_line(line: dict, values: dict) -> None:
    """검토 화면에서 확정한 값으로 실제 거래를 저장한다.

    입금/출금이 동시에 있거나 둘 다 없으면 절대 저장되지 않는다 - 이 검증은
    services.import_service.confirm_line이 서비스 계층에서 직접 수행한다.
    """
    income_text = values["income_text"]
    expense_text = values["expense_text"]
    income = parse_amount(income_text) if income_text.strip() else None
    expense = parse_amount(expense_text) if expense_text.strip() else None
    balance = parse_amount(values["balance_text"]) if values["balance_text"].strip() else None

    categories = values["categories"]
    category_id = None
    if values["category_choice"] != "(선택 안함)":
        category_id = next(c["id"] for c in categories if c["name"] == values["category_choice"])

    client_id = None
    if values["client_choice"] == "+ 새 거래처 입력":
        if values["new_client_name"] and values["new_client_name"].strip():
            client_id = client_service.get_or_create_client(values["new_client_name"])
    elif values["client_choice"] != "(선택 안함)":
        client_id = next(c["id"] for c in all_clients if c["name"] == values["client_choice"])

    work_type_id = None
    if values["work_type_choice"] != "(선택 안함)":
        work_type_id = next(w["id"] for w in all_work_types if w["name"] == values["work_type_choice"])

    account_id = None
    if values["account_choice"] != "(선택 안함)":
        account_id = next(a["id"] for a in all_accounts if a["name"] == values["account_choice"])

    transaction_data = {
        "transaction_date": values["date"].isoformat(),
        "description": values["description"].strip() if values["description"] else values["description"],
        "transaction_time": values["time"],
        "balance": balance,
        "category_id": category_id,
        "client_id": client_id,
        "work_type_id": work_type_id,
        "account_id": account_id,
        "accounting_type": values["accounting_type"],
        "vat_status": values["vat_status"],
        "evidence_status": values["evidence_status"],
        "memo": values["memo"].strip() if values["memo"] else None,
    }

    import_service.confirm_line(
        line["id"], income, expense, transaction_data, rule_id=values.get("suggestion_rule_id")
    )


selected_line_ids: list[int] = []
normal_line_ids: list[int] = []
line_values: dict[int, dict] = {}

for line in lines:
    line_id = line["id"]
    status = line["status"]
    badge = STATUS_BADGE.get(status, status)
    desc_preview = (line["raw_description"] or "")[:25]

    with st.expander(
        f"{line['line_no']}. {badge}  |  {line['raw_date'] or '날짜 미확인'}  |  {desc_preview}",
        expanded=(status != STATUS_OK),
    ):
        if line["confidence"] is not None:
            st.caption(f"OCR 인식 신뢰도: {line['confidence']:.1f}")

        col_check, col_rest = st.columns([1, 9])
        with col_check:
            checked = st.checkbox("선택", key=f"import_check_{line_id}", label_visibility="collapsed")
        if checked:
            selected_line_ids.append(line_id)

        col1, col2 = st.columns(2)
        with col1:
            parsed_date = date.fromisoformat(line["raw_date"]) if line["raw_date"] else date.today()
            row_date = st.date_input("거래일자 *", value=parsed_date, key=f"import_date_{line_id}")

            existing_time = dtime.fromisoformat(line["raw_time"]) if line["raw_time"] else None
            has_time = st.checkbox(
                "거래시간 입력", value=existing_time is not None, key=f"import_has_time_{line_id}"
            )
            row_time = None
            if has_time:
                time_value = st.time_input(
                    "거래시간", value=existing_time or dtime(0, 0), key=f"import_time_{line_id}"
                )
                row_time = time_value.strftime("%H:%M:%S")

            row_description = st.text_input(
                "거래내용 *", value=line["raw_description"] or "", key=f"import_desc_{line_id}"
            )

            income_text = st.text_input(
                "입금액",
                value=format_amount(line["raw_income"]) if line["raw_income"] is not None else "",
                key=f"import_income_{line_id}",
            )
            expense_text = st.text_input(
                "출금액",
                value=format_amount(line["raw_expense"]) if line["raw_expense"] is not None else "",
                key=f"import_expense_{line_id}",
            )
            balance_text = st.text_input(
                "잔액",
                value=format_amount(line["raw_balance"]) if line["raw_balance"] is not None else "",
                key=f"import_balance_{line_id}",
            )

        with col2:
            client_names = [c["name"] for c in all_clients]
            client_options = ["(선택 안함)", "+ 새 거래처 입력"] + client_names
            default_client_idx = 0
            if line["suggested_client_id"] is not None and line["suggested_client_name"] in client_names:
                default_client_idx = client_options.index(line["suggested_client_name"])
            client_choice = st.selectbox(
                "거래처", client_options, index=default_client_idx, key=f"import_client_{line_id}"
            )
            new_client_name = ""
            if client_choice == "+ 새 거래처 입력":
                new_client_name = st.text_input("새 거래처명", key=f"import_new_client_{line_id}")

            # income/expense 중 어느 쪽이 채워졌는지에 따라 카테고리 후보(수입/지출)를 정한다.
            # 아직 판단 불가(둘 다 없거나 둘 다 있음)면 임시로 지출 카테고리를 보여준다 -
            # 어차피 이 상태에서는 저장 시점에 검증에서 막힌다.
            has_income = bool(income_text.strip())
            has_expense = bool(expense_text.strip())
            category_type = "income" if has_income and not has_expense else "expense"
            categories = income_categories if category_type == "income" else expense_categories
            category_options = ["(선택 안함)"] + [c["name"] for c in categories]
            default_category_idx = 0
            if (
                line["suggested_category_id"] is not None
                and line["suggested_category_name"] in [c["name"] for c in categories]
            ):
                default_category_idx = category_options.index(line["suggested_category_name"])
            category_choice = st.selectbox(
                "카테고리",
                category_options,
                index=default_category_idx,
                key=f"import_category_{line_id}_{category_type}",
            )

            work_type_names = [w["name"] for w in all_work_types]
            work_type_options = ["(선택 안함)"] + work_type_names
            default_wt_idx = 0
            if (
                line["suggested_work_type_id"] is not None
                and line["suggested_work_type_name"] in work_type_names
            ):
                default_wt_idx = work_type_options.index(line["suggested_work_type_name"])
            work_type_choice = st.selectbox(
                "업무유형", work_type_options, index=default_wt_idx, key=f"import_work_type_{line_id}"
            )

            accounting_type_options = transaction_service.ACCOUNTING_TYPE_OPTIONS
            default_acct_type_idx = accounting_type_options.index(
                transaction_service.DEFAULT_ACCOUNTING_TYPE
            )
            if line["suggested_accounting_type"] in accounting_type_options:
                default_acct_type_idx = accounting_type_options.index(line["suggested_accounting_type"])
            accounting_type_choice = st.selectbox(
                "회계구분",
                accounting_type_options,
                index=default_acct_type_idx,
                key=f"import_accounting_type_{line_id}",
                help="입금/출금(통장 방향)과는 다른 개념입니다. 확실하지 않으면 '미분류'로 두세요.",
            )

            account_names = [a["name"] for a in all_accounts]
            account_options = ["(선택 안함)"] + account_names
            default_account_idx = 0
            if line["suggested_account_id"] is not None and line["suggested_account_name"] in account_names:
                default_account_idx = account_options.index(line["suggested_account_name"])
            account_choice = st.selectbox(
                "계정과목", account_options, index=default_account_idx, key=f"import_account_{line_id}"
            )

            # 부가세 여부 추천: 규칙 값 > (회계구분 매출·비용 + 금액이 11의 배수) > 없음('불명').
            # 추천값이 바뀌면(회계구분·금액을 고치면) 위젯 key가 바뀌어 새 추천값으로 다시 채워진다.
            try:
                amount_for_vat = parse_amount(income_text or expense_text) if (has_income or has_expense) else 0
            except ValueError:
                amount_for_vat = 0
            vat_suggestion = vat_service.suggest_vat_status(
                amount_for_vat, accounting_type_choice, line.get("suggested_vat_status")
            )
            vat_options = transaction_service.VAT_STATUS_OPTIONS
            default_vat = vat_suggestion["vat_status"] if vat_suggestion else transaction_service.DEFAULT_VAT_STATUS
            vat_status = st.selectbox(
                "부가세 여부",
                vat_options,
                index=vat_options.index(default_vat),
                key=f"import_vat_{line_id}_{default_vat}",
                help="'과세' = 금액에 부가세 10%가 포함됨. 추천값일 뿐이니 확인 후 저장하세요.",
            )
            if vat_suggestion:
                st.caption(f"부가세 추천: {vat_suggestion['vat_status']} ({vat_suggestion['reason']})")
            if vat_status == "과세" and amount_for_vat:
                supply, vat = split_vat(amount_for_vat)
                st.caption(f"공급가액 {format_amount(supply)}원 + 부가세 {format_amount(vat)}원")
            evidence_status = st.selectbox(
                "증빙 여부",
                transaction_service.EVIDENCE_STATUS_OPTIONS,
                index=transaction_service.EVIDENCE_STATUS_OPTIONS.index(
                    transaction_service.DEFAULT_EVIDENCE_STATUS
                ),
                key=f"import_evidence_{line_id}",
            )
            memo = st.text_area("메모", key=f"import_memo_{line_id}")

        line_values[line_id] = {
            "date": row_date,
            "time": row_time,
            "description": row_description,
            "income_text": income_text,
            "expense_text": expense_text,
            "balance_text": balance_text,
            "category_choice": category_choice,
            "categories": categories,
            "client_choice": client_choice,
            "new_client_name": new_client_name,
            "work_type_choice": work_type_choice,
            "accounting_type": accounting_type_choice,
            "account_choice": account_choice,
            "vat_status": vat_status,
            "evidence_status": evidence_status,
            "memo": memo,
        }

        col_save, col_discard = st.columns(2)
        with col_save:
            row_save_clicked = st.button("💾 이 거래 저장", key=f"import_save_{line_id}")
        with col_discard:
            row_discard_clicked = st.button("🚫 이 항목 제외 (저장 안 함)", key=f"import_discard_{line_id}")

        if row_discard_clicked:
            import_service.discard_line(line_id)
            st.session_state["import_discard_success"] = True
            st.rerun()

        if row_save_clicked:
            try:
                _save_review_line(line, line_values[line_id])
                st.session_state["import_save_success"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    if status == STATUS_OK:
        normal_line_ids.append(line_id)

st.divider()

col_bulk1, col_bulk2 = st.columns(2)
with col_bulk1:
    if st.button(
        f"☑️ 선택한 거래 저장 ({len(selected_line_ids)}건)",
        disabled=not selected_line_ids,
        use_container_width=True,
    ):
        saved = 0
        for line in lines:
            if line["id"] not in selected_line_ids:
                continue
            try:
                _save_review_line(line, line_values[line["id"]])
                saved += 1
            except ValidationError as e:
                st.error(f"{line['line_no']}번 항목: {e}")
        if saved:
            st.session_state["import_save_success"] = True
            st.rerun()

with col_bulk2:
    if st.button(
        f"✅ 정상 거래 전체 저장 ({len(normal_line_ids)}건)",
        disabled=not normal_line_ids,
        use_container_width=True,
        help="OCR 인식 결과가 '정상'으로 표시된 항목만 지금 화면에 표시된 값 그대로 한 번에 저장합니다.",
    ):
        saved = 0
        for line in lines:
            if line["id"] not in normal_line_ids:
                continue
            try:
                _save_review_line(line, line_values[line["id"]])
                saved += 1
            except ValidationError as e:
                st.error(f"{line['line_no']}번 항목: {e}")
        if saved:
            st.session_state["import_save_success"] = True
            st.rerun()

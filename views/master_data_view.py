import pandas as pd
import streamlit as st

from services import (
    account_service,
    category_rule_service,
    category_service,
    client_service,
    transaction_service,
    work_type_service,
)
from utils.validators import ValidationError

st.title("🗂️ 기준정보 관리")
st.caption("거래처 / 카테고리 / 업무유형 / 계정과목을 관리합니다. 삭제 대신 비활성화 방식을 사용하므로 기존 거래내역은 항상 안전하게 유지됩니다.")

TYPE_LABELS = {"income": "수입", "expense": "지출"}
STATUS_OPTIONS = ["활성", "비활성", "전체"]
STATUS_MAP = {"활성": "active", "비활성": "inactive", "전체": "all"}


def _clear_flag(flag_key: str, suffix_key: str) -> None:
    """다이얼로그에서 rerun()으로 넘어온 "선택 초기화" 요청을, 위젯이
    다시 만들어지기 전인 여기(최상단)에서 처리한다."""
    if st.session_state.pop(flag_key, False):
        st.session_state[suffix_key] = st.session_state.get(suffix_key, 0) + 1
    st.session_state.setdefault(suffix_key, 0)


_clear_flag("client_clear_selection", "client_select_suffix")
_clear_flag("category_clear_selection", "category_select_suffix")
_clear_flag("work_type_clear_selection", "work_type_select_suffix")
_clear_flag("account_clear_selection", "account_select_suffix")
_clear_flag("rule_clear_selection", "rule_select_suffix")

if msg := st.session_state.pop("client_msg", None):
    st.success(msg)
if msg := st.session_state.pop("category_msg", None):
    st.success(msg)
if msg := st.session_state.pop("work_type_msg", None):
    st.success(msg)
if msg := st.session_state.pop("account_msg", None):
    st.success(msg)
if msg := st.session_state.pop("rule_msg", None):
    st.success(msg)


# st.tabs는 다이얼로그의 st.rerun() 이후 선택된 탭이 첫 번째로 되돌아가는
# 경우가 있어(프론트엔드 전용 상태이기 때문), session_state로 직접 관리되는
# 라디오 버튼으로 탭을 구현한다 - 이렇게 하면 어떤 동작 후에도 사용자가
# 보던 화면(거래처/카테고리/업무유형/계정과목)에 그대로 머무른다.
st.session_state.setdefault("md_active_tab", "거래처")
active_tab = st.radio(
    "관리 항목", ["거래처", "카테고리", "업무유형", "계정과목", "자동분류 규칙"], horizontal=True, key="md_active_tab"
)


# =====================================================================
# 거래처
# =====================================================================
if active_tab == "거래처":
    st.subheader("거래처 관리")

    combined_categories = category_service.get_income_categories() + category_service.get_expense_categories()
    category_label_to_id = {
        f"{c['name']} ({TYPE_LABELS[c['type']]})": c["id"] for c in combined_categories
    }
    active_work_types = work_type_service.get_work_types()
    work_type_label_to_id = {w["name"]: w["id"] for w in active_work_types}

    @st.dialog("새 거래처 추가")
    def open_add_client_dialog() -> None:
        name = st.text_input("거래처명 *", key="add_client_name")
        category_choice = st.selectbox(
            "기본 카테고리", ["(선택 안함)"] + list(category_label_to_id.keys()), key="add_client_category"
        )
        work_type_choice = st.selectbox(
            "기본 업무유형", ["(선택 안함)"] + list(work_type_label_to_id.keys()), key="add_client_work_type"
        )
        memo = st.text_area("메모", key="add_client_memo")
        st.caption("* 표시 항목은 필수입니다. 기본 카테고리/업무유형은 이후 거래등록 시 추천값으로만 쓰이며, 언제든 다른 값으로 바꿀 수 있습니다.")

        if st.button("추가", type="primary", key="add_client_submit"):
            try:
                category_id = category_label_to_id.get(category_choice)
                work_type_id = work_type_label_to_id.get(work_type_choice)
                client_service.create_client(
                    name, category_id, work_type_id, memo.strip() if memo else None
                )
                st.session_state["client_msg"] = f"'{name.strip()}' 거래처를 추가했습니다."
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("거래처 수정")
    def open_edit_client_dialog(client: dict) -> None:
        st.caption(f"'{client['name']}' 거래처 정보를 수정합니다.")
        name = st.text_input("거래처명 *", value=client["name"], key=f"edit_client_name_{client['id']}")

        cat_options = ["(선택 안함)"] + list(category_label_to_id.keys())
        current_cat_label = next(
            (label for label, cid in category_label_to_id.items() if cid == client["default_category_id"]),
            None,
        )
        if current_cat_label is None and client["default_category_id"] is not None:
            cat = category_service.get_category(client["default_category_id"])
            if cat:
                current_cat_label = f"{cat['name']} ({TYPE_LABELS[cat['type']]}) (비활성)"
                cat_options = cat_options + [current_cat_label]
                category_label_to_id[current_cat_label] = cat["id"]
        category_choice = st.selectbox(
            "기본 카테고리",
            cat_options,
            index=cat_options.index(current_cat_label) if current_cat_label else 0,
            key=f"edit_client_category_{client['id']}",
        )

        wt_options = ["(선택 안함)"] + list(work_type_label_to_id.keys())
        current_wt_label = next(
            (label for label, wid in work_type_label_to_id.items() if wid == client["default_work_type_id"]),
            None,
        )
        if current_wt_label is None and client["default_work_type_id"] is not None:
            wt = work_type_service.get_work_type(client["default_work_type_id"])
            if wt:
                current_wt_label = f"{wt['name']} (비활성)"
                wt_options = wt_options + [current_wt_label]
                work_type_label_to_id[current_wt_label] = wt["id"]
        work_type_choice = st.selectbox(
            "기본 업무유형",
            wt_options,
            index=wt_options.index(current_wt_label) if current_wt_label else 0,
            key=f"edit_client_work_type_{client['id']}",
        )

        memo = st.text_area("메모", value=client["memo"] or "", key=f"edit_client_memo_{client['id']}")
        st.caption("여기서 바꾼 기본값은 추천값 갱신일 뿐이며, 이미 저장된 과거 거래에는 영향을 주지 않습니다.")

        if st.button("저장", type="primary", key=f"edit_client_submit_{client['id']}"):
            try:
                category_id = category_label_to_id.get(category_choice)
                work_type_id = work_type_label_to_id.get(work_type_choice)
                client_service.update_client_info(
                    client["id"], name, category_id, work_type_id, memo.strip() if memo else None
                )
                st.session_state["client_msg"] = f"'{name.strip()}' 거래처 정보를 수정했습니다."
                st.session_state["client_clear_selection"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("거래처 비활성화")
    def open_deactivate_client_dialog(client: dict) -> None:
        st.warning(
            f"'{client['name']}'을(를) 비활성화하시겠습니까?\n\n"
            "기존 거래내역은 유지되며, 신규 거래 등록에서는 선택되지 않습니다."
        )
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("비활성화", type="primary", key=f"confirm_deactivate_client_{client['id']}", use_container_width=True):
                client_service.deactivate_client(client["id"])
                st.session_state["client_msg"] = f"'{client['name']}'을(를) 비활성화했습니다."
                st.session_state["client_clear_selection"] = True
                st.rerun()
        with col_cancel:
            if st.button("취소", key=f"cancel_deactivate_client_{client['id']}", use_container_width=True):
                st.rerun()

    if st.button("+ 새 거래처 추가", key="open_add_client"):
        open_add_client_dialog()

    st.divider()

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        client_status_choice = st.selectbox("상태 필터", STATUS_OPTIONS, index=0, key="client_status_filter")
    with filter_col2:
        client_keyword = st.text_input("거래처명 검색", key="client_keyword_filter", placeholder="예: OO기업")

    clients_admin = client_service.list_clients_admin(
        status=STATUS_MAP[client_status_choice], keyword=client_keyword.strip() or None
    )

    if not clients_admin:
        st.info("조건에 해당하는 거래처가 없습니다.")
    else:
        rows = []
        for c in clients_admin:
            cat = category_service.get_category(c["default_category_id"]) if c["default_category_id"] else None
            wt = work_type_service.get_work_type(c["default_work_type_id"]) if c["default_work_type_id"] else None
            rows.append(
                {
                    "거래처명": c["name"],
                    "기본 카테고리": f"{cat['name']} ({TYPE_LABELS[cat['type']]})" if cat else "",
                    "기본 업무유형": wt["name"] if wt else "",
                    "상태": "활성" if c["is_active"] else "비활성",
                    "메모": c["memo"] or "",
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        st.caption("아래에서 수정 또는 상태를 변경할 거래처를 선택하세요.")

        def _fmt_client_option(i: int | None) -> str:
            if i is None:
                return "(선택 안함)"
            c = clients_admin[i]
            return f"{c['name']} ({'활성' if c['is_active'] else '비활성'})"

        client_selected_idx = st.selectbox(
            "수정 또는 상태변경할 거래처 선택",
            options=list(range(len(clients_admin))),
            format_func=_fmt_client_option,
            index=None,
            placeholder="(선택 안함)",
            key=f"client_selected_idx_{st.session_state['client_select_suffix']}",
        )
        selected_client = clients_admin[client_selected_idx] if client_selected_idx is not None else None

        col_edit, col_toggle = st.columns(2)
        with col_edit:
            if st.button("✏️ 수정", disabled=selected_client is None, key="client_edit_btn", use_container_width=True):
                open_edit_client_dialog(selected_client)
        with col_toggle:
            if selected_client is not None and not selected_client["is_active"]:
                if st.button("♻️ 재활성화", key="client_activate_btn", use_container_width=True):
                    client_service.activate_client(selected_client["id"])
                    st.session_state["client_msg"] = f"'{selected_client['name']}'을(를) 재활성화했습니다."
                    st.session_state["client_clear_selection"] = True
                    st.rerun()
            else:
                if st.button("🚫 비활성화", disabled=selected_client is None, key="client_deactivate_btn", use_container_width=True):
                    open_deactivate_client_dialog(selected_client)


# =====================================================================
# 카테고리
# =====================================================================
elif active_tab == "카테고리":
    st.subheader("카테고리 관리")
    st.caption("카테고리 구분(수입/지출)은 생성 후에는 바꿀 수 없습니다. 잘못 만들었다면 비활성화하고 새로 추가해주세요.")

    @st.dialog("새 카테고리 추가")
    def open_add_category_dialog() -> None:
        name = st.text_input("카테고리명 *", key="add_category_name")
        type_label = st.radio("수입/지출 *", ["수입", "지출"], horizontal=True, key="add_category_type")
        sort_order = st.number_input("정렬순서", min_value=0, step=1, value=0, key="add_category_sort")
        st.caption("* 표시 항목은 필수입니다. 정렬순서가 작을수록 목록/드롭다운에서 먼저 표시됩니다.")

        if st.button("추가", type="primary", key="add_category_submit"):
            try:
                type_ = "income" if type_label == "수입" else "expense"
                category_service.create_category(name, type_, int(sort_order))
                st.session_state["category_msg"] = f"'{name.strip()}' 카테고리를 추가했습니다."
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("카테고리 수정")
    def open_edit_category_dialog(category: dict) -> None:
        st.caption(f"'{category['name']}' 카테고리 정보를 수정합니다.")
        st.text_input("수입/지출 구분", value=TYPE_LABELS[category["type"]], disabled=True)
        st.caption("카테고리 구분은 생성 후 변경할 수 없습니다.")
        name = st.text_input("카테고리명 *", value=category["name"], key=f"edit_category_name_{category['id']}")
        sort_order = st.number_input(
            "정렬순서", min_value=0, step=1, value=category["sort_order"], key=f"edit_category_sort_{category['id']}"
        )

        if st.button("저장", type="primary", key=f"edit_category_submit_{category['id']}"):
            try:
                category_service.update_category_info(category["id"], name, int(sort_order))
                st.session_state["category_msg"] = f"'{name.strip()}' 카테고리 정보를 수정했습니다."
                st.session_state["category_clear_selection"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("카테고리 비활성화")
    def open_deactivate_category_dialog(category: dict) -> None:
        type_label = TYPE_LABELS[category["type"]]
        st.warning(
            f"'{category['name']}' ({type_label}) 카테고리를 비활성화하시겠습니까?\n\n"
            "기존 거래내역은 유지되며, 신규 거래 등록에서는 선택되지 않습니다."
        )
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("비활성화", type="primary", key=f"confirm_deactivate_category_{category['id']}", use_container_width=True):
                try:
                    category_service.deactivate_category(category["id"])
                    st.session_state["category_msg"] = f"'{category['name']}' 카테고리를 비활성화했습니다."
                    st.session_state["category_clear_selection"] = True
                    st.rerun()
                except ValidationError as e:
                    st.error(str(e))
        with col_cancel:
            if st.button("취소", key=f"cancel_deactivate_category_{category['id']}", use_container_width=True):
                st.rerun()

    if st.button("+ 새 카테고리 추가", key="open_add_category"):
        open_add_category_dialog()

    st.divider()

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        category_type_choice = st.selectbox("구분 필터", ["전체", "수입", "지출"], index=0, key="category_type_filter")
    with filter_col2:
        category_status_choice = st.selectbox("상태 필터", STATUS_OPTIONS, index=0, key="category_status_filter")

    type_filter = None
    if category_type_choice == "수입":
        type_filter = "income"
    elif category_type_choice == "지출":
        type_filter = "expense"

    categories_admin = category_service.list_categories_admin(
        status=STATUS_MAP[category_status_choice], type_filter=type_filter
    )

    if not categories_admin:
        st.info("조건에 해당하는 카테고리가 없습니다.")
    else:
        rows = [
            {
                "카테고리명": c["name"],
                "구분": TYPE_LABELS[c["type"]],
                "기본 카테고리 여부": "예" if c["is_default"] else "아니오",
                "상태": "활성" if c["is_active"] else "비활성",
                "정렬순서": c["sort_order"],
            }
            for c in categories_admin
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        st.caption("아래에서 수정 또는 상태를 변경할 카테고리를 선택하세요.")

        def _fmt_category_option(i: int | None) -> str:
            if i is None:
                return "(선택 안함)"
            c = categories_admin[i]
            return f"{c['name']} ({TYPE_LABELS[c['type']]}) · {'활성' if c['is_active'] else '비활성'}"

        category_selected_idx = st.selectbox(
            "수정 또는 상태변경할 카테고리 선택",
            options=list(range(len(categories_admin))),
            format_func=_fmt_category_option,
            index=None,
            placeholder="(선택 안함)",
            key=f"category_selected_idx_{st.session_state['category_select_suffix']}",
        )
        selected_category = categories_admin[category_selected_idx] if category_selected_idx is not None else None

        col_edit, col_toggle = st.columns(2)
        with col_edit:
            if st.button("✏️ 수정", disabled=selected_category is None, key="category_edit_btn", use_container_width=True):
                open_edit_category_dialog(selected_category)
        with col_toggle:
            if selected_category is not None and not selected_category["is_active"]:
                if st.button("♻️ 재활성화", key="category_activate_btn", use_container_width=True):
                    category_service.activate_category(selected_category["id"])
                    st.session_state["category_msg"] = f"'{selected_category['name']}' 카테고리를 재활성화했습니다."
                    st.session_state["category_clear_selection"] = True
                    st.rerun()
            else:
                if st.button("🚫 비활성화", disabled=selected_category is None, key="category_deactivate_btn", use_container_width=True):
                    open_deactivate_category_dialog(selected_category)


# =====================================================================
# 업무유형
# =====================================================================
elif active_tab == "업무유형":
    st.subheader("업무유형 관리")

    @st.dialog("새 업무유형 추가")
    def open_add_work_type_dialog() -> None:
        name = st.text_input("업무유형명 *", key="add_work_type_name")
        sort_order = st.number_input("정렬순서", min_value=0, step=1, value=0, key="add_work_type_sort")
        st.caption("* 표시 항목은 필수입니다.")

        if st.button("추가", type="primary", key="add_work_type_submit"):
            try:
                work_type_service.create_work_type(name, int(sort_order))
                st.session_state["work_type_msg"] = f"'{name.strip()}' 업무유형을 추가했습니다."
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("업무유형 수정")
    def open_edit_work_type_dialog(work_type: dict) -> None:
        st.caption(f"'{work_type['name']}' 업무유형 정보를 수정합니다.")
        name = st.text_input("업무유형명 *", value=work_type["name"], key=f"edit_work_type_name_{work_type['id']}")
        sort_order = st.number_input(
            "정렬순서", min_value=0, step=1, value=work_type["sort_order"], key=f"edit_work_type_sort_{work_type['id']}"
        )
        st.caption("이름을 바꾸면 이 업무유형을 참조하는 과거 거래에도 바뀐 이름이 그대로 표시됩니다.")

        if st.button("저장", type="primary", key=f"edit_work_type_submit_{work_type['id']}"):
            try:
                work_type_service.update_work_type_info(work_type["id"], name, int(sort_order))
                st.session_state["work_type_msg"] = f"'{name.strip()}' 업무유형 정보를 수정했습니다."
                st.session_state["work_type_clear_selection"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("업무유형 비활성화")
    def open_deactivate_work_type_dialog(work_type: dict) -> None:
        st.warning(
            f"'{work_type['name']}'을(를) 비활성화하시겠습니까?\n\n"
            "기존 거래내역은 유지되며, 신규 거래 등록에서는 선택되지 않습니다."
        )
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("비활성화", type="primary", key=f"confirm_deactivate_work_type_{work_type['id']}", use_container_width=True):
                work_type_service.deactivate_work_type(work_type["id"])
                st.session_state["work_type_msg"] = f"'{work_type['name']}'을(를) 비활성화했습니다."
                st.session_state["work_type_clear_selection"] = True
                st.rerun()
        with col_cancel:
            if st.button("취소", key=f"cancel_deactivate_work_type_{work_type['id']}", use_container_width=True):
                st.rerun()

    if st.button("+ 새 업무유형 추가", key="open_add_work_type"):
        open_add_work_type_dialog()

    st.divider()

    work_type_status_choice = st.selectbox("상태 필터", STATUS_OPTIONS, index=0, key="work_type_status_filter")

    work_types_admin = work_type_service.list_work_types_admin(status=STATUS_MAP[work_type_status_choice])

    if not work_types_admin:
        st.info("조건에 해당하는 업무유형이 없습니다.")
    else:
        rows = [
            {
                "업무유형명": w["name"],
                "상태": "활성" if w["is_active"] else "비활성",
                "정렬순서": w["sort_order"],
            }
            for w in work_types_admin
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        st.caption("아래에서 수정 또는 상태를 변경할 업무유형을 선택하세요.")

        def _fmt_work_type_option(i: int | None) -> str:
            if i is None:
                return "(선택 안함)"
            w = work_types_admin[i]
            return f"{w['name']} ({'활성' if w['is_active'] else '비활성'})"

        work_type_selected_idx = st.selectbox(
            "수정 또는 상태변경할 업무유형 선택",
            options=list(range(len(work_types_admin))),
            format_func=_fmt_work_type_option,
            index=None,
            placeholder="(선택 안함)",
            key=f"work_type_selected_idx_{st.session_state['work_type_select_suffix']}",
        )
        selected_work_type = work_types_admin[work_type_selected_idx] if work_type_selected_idx is not None else None

        col_edit, col_toggle = st.columns(2)
        with col_edit:
            if st.button("✏️ 수정", disabled=selected_work_type is None, key="work_type_edit_btn", use_container_width=True):
                open_edit_work_type_dialog(selected_work_type)
        with col_toggle:
            if selected_work_type is not None and not selected_work_type["is_active"]:
                if st.button("♻️ 재활성화", key="work_type_activate_btn", use_container_width=True):
                    work_type_service.activate_work_type(selected_work_type["id"])
                    st.session_state["work_type_msg"] = f"'{selected_work_type['name']}'을(를) 재활성화했습니다."
                    st.session_state["work_type_clear_selection"] = True
                    st.rerun()
            else:
                if st.button("🚫 비활성화", disabled=selected_work_type is None, key="work_type_deactivate_btn", use_container_width=True):
                    open_deactivate_work_type_dialog(selected_work_type)


# =====================================================================
# 계정과목
# =====================================================================
elif active_tab == "계정과목":
    st.subheader("계정과목 관리")
    st.caption("법인 통장 거래를 정리할 때 참고하는 계정과목입니다. 세무사 전달용 Excel에도 함께 표시됩니다.")

    @st.dialog("새 계정과목 추가")
    def open_add_account_dialog() -> None:
        name = st.text_input("계정과목명 *", key="add_account_name")
        sort_order = st.number_input("정렬순서", min_value=0, step=1, value=0, key="add_account_sort")
        st.caption("* 표시 항목은 필수입니다.")

        if st.button("추가", type="primary", key="add_account_submit"):
            try:
                account_service.create_account(name, int(sort_order))
                st.session_state["account_msg"] = f"'{name.strip()}' 계정과목을 추가했습니다."
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("계정과목 수정")
    def open_edit_account_dialog(account: dict) -> None:
        st.caption(f"'{account['name']}' 계정과목 정보를 수정합니다.")
        name = st.text_input("계정과목명 *", value=account["name"], key=f"edit_account_name_{account['id']}")
        sort_order = st.number_input(
            "정렬순서", min_value=0, step=1, value=account["sort_order"], key=f"edit_account_sort_{account['id']}"
        )

        if st.button("저장", type="primary", key=f"edit_account_submit_{account['id']}"):
            try:
                account_service.update_account_info(account["id"], name, int(sort_order))
                st.session_state["account_msg"] = f"'{name.strip()}' 계정과목 정보를 수정했습니다."
                st.session_state["account_clear_selection"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("계정과목 비활성화")
    def open_deactivate_account_dialog(account: dict) -> None:
        st.warning(
            f"'{account['name']}'을(를) 비활성화하시겠습니까?\n\n"
            "기존 거래내역은 유지되며, 신규 거래 등록에서는 선택되지 않습니다."
        )
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("비활성화", type="primary", key=f"confirm_deactivate_account_{account['id']}", use_container_width=True):
                account_service.deactivate_account(account["id"])
                st.session_state["account_msg"] = f"'{account['name']}'을(를) 비활성화했습니다."
                st.session_state["account_clear_selection"] = True
                st.rerun()
        with col_cancel:
            if st.button("취소", key=f"cancel_deactivate_account_{account['id']}", use_container_width=True):
                st.rerun()

    if st.button("+ 새 계정과목 추가", key="open_add_account"):
        open_add_account_dialog()

    st.divider()

    account_status_choice = st.selectbox("상태 필터", STATUS_OPTIONS, index=0, key="account_status_filter")

    accounts_admin = account_service.list_accounts_admin(status=STATUS_MAP[account_status_choice])

    if not accounts_admin:
        st.info("조건에 해당하는 계정과목이 없습니다.")
    else:
        rows = [
            {
                "계정과목명": a["name"],
                "상태": "활성" if a["is_active"] else "비활성",
                "정렬순서": a["sort_order"],
            }
            for a in accounts_admin
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        st.caption("아래에서 수정 또는 상태를 변경할 계정과목을 선택하세요.")

        def _fmt_account_option(i: int | None) -> str:
            if i is None:
                return "(선택 안함)"
            a = accounts_admin[i]
            return f"{a['name']} ({'활성' if a['is_active'] else '비활성'})"

        account_selected_idx = st.selectbox(
            "수정 또는 상태변경할 계정과목 선택",
            options=list(range(len(accounts_admin))),
            format_func=_fmt_account_option,
            index=None,
            placeholder="(선택 안함)",
            key=f"account_selected_idx_{st.session_state['account_select_suffix']}",
        )
        selected_account = accounts_admin[account_selected_idx] if account_selected_idx is not None else None

        col_edit, col_toggle = st.columns(2)
        with col_edit:
            if st.button("✏️ 수정", disabled=selected_account is None, key="account_edit_btn", use_container_width=True):
                open_edit_account_dialog(selected_account)
        with col_toggle:
            if selected_account is not None and not selected_account["is_active"]:
                if st.button("♻️ 재활성화", key="account_activate_btn", use_container_width=True):
                    account_service.activate_account(selected_account["id"])
                    st.session_state["account_msg"] = f"'{selected_account['name']}'을(를) 재활성화했습니다."
                    st.session_state["account_clear_selection"] = True
                    st.rerun()
            else:
                if st.button("🚫 비활성화", disabled=selected_account is None, key="account_deactivate_btn", use_container_width=True):
                    open_deactivate_account_dialog(selected_account)


# =====================================================================
# 자동분류 규칙
# =====================================================================
else:  # 자동분류 규칙
    st.subheader("자동분류 규칙 관리")
    st.caption(
        "키워드가 거래내용/거래처명에 포함되면 카테고리/거래처/업무유형/계정과목/회계구분/부가세 여부를 "
        "'추천'만 해줍니다. 통장 가져오기(OCR) 검토 화면에서 추천값으로 미리 채워질 뿐이며, "
        "언제든 다른 값으로 바꿀 수 있고 자동으로 확정 저장되지는 않습니다."
    )

    combined_categories = category_service.get_income_categories() + category_service.get_expense_categories()
    rule_category_label_to_id = {
        f"{c['name']} ({TYPE_LABELS[c['type']]})": c["id"] for c in combined_categories
    }
    rule_clients = client_service.get_clients()
    rule_client_label_to_id = {c["name"]: c["id"] for c in rule_clients}
    rule_work_types = work_type_service.get_work_types()
    rule_work_type_label_to_id = {w["name"]: w["id"] for w in rule_work_types}
    rule_accounts = account_service.get_accounts()
    rule_account_label_to_id = {a["name"]: a["id"] for a in rule_accounts}
    rule_accounting_type_options = ["(선택 안함)"] + transaction_service.ACCOUNTING_TYPE_OPTIONS
    rule_vat_status_options = ["(선택 안함)"] + transaction_service.VAT_STATUS_OPTIONS
    RULE_VAT_HELP = "'과세'는 금액에 부가세 10%가 포함되어 있다는 뜻입니다 (예: CMS사용료, 인증수수료)."

    def _resolve_rule_names(rule: dict) -> dict:
        category = category_service.get_category(rule["suggested_category_id"]) if rule["suggested_category_id"] else None
        client = client_service.get_client(rule["suggested_client_id"]) if rule["suggested_client_id"] else None
        work_type = work_type_service.get_work_type(rule["suggested_work_type_id"]) if rule["suggested_work_type_id"] else None
        account = account_service.get_account(rule["suggested_account_id"]) if rule["suggested_account_id"] else None
        return {
            "category": f"{category['name']} ({TYPE_LABELS[category['type']]})" if category else "",
            "client": client["name"] if client else "",
            "work_type": work_type["name"] if work_type else "",
            "account": account["name"] if account else "",
            "accounting_type": rule["suggested_accounting_type"] or "",
            "vat_status": rule.get("suggested_vat_status") or "",
        }

    @st.dialog("새 자동분류 규칙 추가")
    def open_add_rule_dialog() -> None:
        keyword = st.text_input("키워드 *", key="add_rule_keyword", placeholder="예: KT, A회사")
        match_field_label = st.radio(
            "매칭 대상 *", ["거래내용", "거래처명"], horizontal=True, key="add_rule_match_field"
        )
        category_choice = st.selectbox(
            "추천 카테고리", ["(선택 안함)"] + list(rule_category_label_to_id.keys()), key="add_rule_category"
        )
        client_choice = st.selectbox(
            "추천 거래처", ["(선택 안함)"] + list(rule_client_label_to_id.keys()), key="add_rule_client"
        )
        work_type_choice = st.selectbox(
            "추천 업무유형", ["(선택 안함)"] + list(rule_work_type_label_to_id.keys()), key="add_rule_work_type"
        )
        account_choice = st.selectbox(
            "추천 계정과목", ["(선택 안함)"] + list(rule_account_label_to_id.keys()), key="add_rule_account"
        )
        accounting_type_choice = st.selectbox(
            "추천 회계구분", rule_accounting_type_options, key="add_rule_accounting_type"
        )
        vat_status_choice = st.selectbox(
            "추천 부가세 여부", rule_vat_status_options, key="add_rule_vat_status", help=RULE_VAT_HELP
        )
        st.caption("* 표시 항목은 필수입니다. 추천 항목은 최소 1개 이상 선택하는 것을 권장합니다.")

        if st.button("추가", type="primary", key="add_rule_submit"):
            try:
                match_field = "description" if match_field_label == "거래내용" else "client_name"
                category_rule_service.create_rule(
                    keyword=keyword,
                    match_field=match_field,
                    suggested_category_id=rule_category_label_to_id.get(category_choice),
                    suggested_client_id=rule_client_label_to_id.get(client_choice),
                    suggested_work_type_id=rule_work_type_label_to_id.get(work_type_choice),
                    suggested_account_id=rule_account_label_to_id.get(account_choice),
                    suggested_accounting_type=(
                        accounting_type_choice if accounting_type_choice != "(선택 안함)" else None
                    ),
                    suggested_vat_status=vat_status_choice if vat_status_choice != "(선택 안함)" else None,
                )
                st.session_state["rule_msg"] = f"'{keyword.strip()}' 규칙을 추가했습니다."
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("자동분류 규칙 수정")
    def open_edit_rule_dialog(rule: dict) -> None:
        st.caption(f"'{rule['keyword']}' 규칙을 수정합니다.")
        keyword = st.text_input("키워드 *", value=rule["keyword"], key=f"edit_rule_keyword_{rule['id']}")
        match_field_options = ["거래내용", "거래처명"]
        current_match_label = "거래내용" if rule["match_field"] == "description" else "거래처명"
        match_field_label = st.radio(
            "매칭 대상 *",
            match_field_options,
            index=match_field_options.index(current_match_label),
            horizontal=True,
            key=f"edit_rule_match_field_{rule['id']}",
        )

        names = _resolve_rule_names(rule)
        category_options = ["(선택 안함)"] + list(rule_category_label_to_id.keys())
        category_choice = st.selectbox(
            "추천 카테고리",
            category_options,
            index=category_options.index(names["category"]) if names["category"] in category_options else 0,
            key=f"edit_rule_category_{rule['id']}",
        )
        client_options = ["(선택 안함)"] + list(rule_client_label_to_id.keys())
        client_choice = st.selectbox(
            "추천 거래처",
            client_options,
            index=client_options.index(names["client"]) if names["client"] in client_options else 0,
            key=f"edit_rule_client_{rule['id']}",
        )
        work_type_options = ["(선택 안함)"] + list(rule_work_type_label_to_id.keys())
        work_type_choice = st.selectbox(
            "추천 업무유형",
            work_type_options,
            index=work_type_options.index(names["work_type"]) if names["work_type"] in work_type_options else 0,
            key=f"edit_rule_work_type_{rule['id']}",
        )
        account_options = ["(선택 안함)"] + list(rule_account_label_to_id.keys())
        account_choice = st.selectbox(
            "추천 계정과목",
            account_options,
            index=account_options.index(names["account"]) if names["account"] in account_options else 0,
            key=f"edit_rule_account_{rule['id']}",
        )
        accounting_type_choice = st.selectbox(
            "추천 회계구분",
            rule_accounting_type_options,
            index=(
                rule_accounting_type_options.index(names["accounting_type"])
                if names["accounting_type"] in rule_accounting_type_options
                else 0
            ),
            key=f"edit_rule_accounting_type_{rule['id']}",
        )
        vat_status_choice = st.selectbox(
            "추천 부가세 여부",
            rule_vat_status_options,
            index=(
                rule_vat_status_options.index(names["vat_status"])
                if names["vat_status"] in rule_vat_status_options
                else 0
            ),
            key=f"edit_rule_vat_status_{rule['id']}",
            help=RULE_VAT_HELP,
        )

        if st.button("저장", type="primary", key=f"edit_rule_submit_{rule['id']}"):
            try:
                match_field = "description" if match_field_label == "거래내용" else "client_name"
                category_rule_service.update_rule_info(
                    rule["id"],
                    keyword=keyword,
                    match_field=match_field,
                    suggested_category_id=rule_category_label_to_id.get(category_choice),
                    suggested_client_id=rule_client_label_to_id.get(client_choice),
                    suggested_work_type_id=rule_work_type_label_to_id.get(work_type_choice),
                    suggested_account_id=rule_account_label_to_id.get(account_choice),
                    suggested_accounting_type=(
                        accounting_type_choice if accounting_type_choice != "(선택 안함)" else None
                    ),
                    suggested_vat_status=vat_status_choice if vat_status_choice != "(선택 안함)" else None,
                )
                st.session_state["rule_msg"] = f"'{keyword.strip()}' 규칙 정보를 수정했습니다."
                st.session_state["rule_clear_selection"] = True
                st.rerun()
            except ValidationError as e:
                st.error(str(e))

    @st.dialog("자동분류 규칙 비활성화")
    def open_deactivate_rule_dialog(rule: dict) -> None:
        st.warning(f"'{rule['keyword']}' 규칙을 비활성화하시겠습니까?\n\n비활성화하면 더 이상 추천에 사용되지 않습니다.")
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("비활성화", type="primary", key=f"confirm_deactivate_rule_{rule['id']}", use_container_width=True):
                category_rule_service.deactivate_rule(rule["id"])
                st.session_state["rule_msg"] = f"'{rule['keyword']}' 규칙을 비활성화했습니다."
                st.session_state["rule_clear_selection"] = True
                st.rerun()
        with col_cancel:
            if st.button("취소", key=f"cancel_deactivate_rule_{rule['id']}", use_container_width=True):
                st.rerun()

    if st.button("+ 새 규칙 추가", key="open_add_rule"):
        open_add_rule_dialog()

    st.divider()

    rule_status_choice = st.selectbox("상태 필터", STATUS_OPTIONS, index=0, key="rule_status_filter")

    rules_admin = category_rule_service.list_rules(status=STATUS_MAP[rule_status_choice])

    if not rules_admin:
        st.info("조건에 해당하는 규칙이 없습니다.")
    else:
        rows = []
        for r in rules_admin:
            names = _resolve_rule_names(r)
            rows.append(
                {
                    "키워드": r["keyword"],
                    "매칭 대상": "거래내용" if r["match_field"] == "description" else "거래처명",
                    "추천 카테고리": names["category"],
                    "추천 거래처": names["client"],
                    "추천 업무유형": names["work_type"],
                    "추천 계정과목": names["account"],
                    "추천 회계구분": names["accounting_type"],
                    "추천 부가세": names["vat_status"],
                    "사용 횟수": r["hit_count"],
                    "상태": "활성" if r["is_active"] else "비활성",
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        st.caption("아래에서 수정 또는 상태를 변경할 규칙을 선택하세요.")

        def _fmt_rule_option(i: int | None) -> str:
            if i is None:
                return "(선택 안함)"
            r = rules_admin[i]
            return f"{r['keyword']} ({'활성' if r['is_active'] else '비활성'})"

        rule_selected_idx = st.selectbox(
            "수정 또는 상태변경할 규칙 선택",
            options=list(range(len(rules_admin))),
            format_func=_fmt_rule_option,
            index=None,
            placeholder="(선택 안함)",
            key=f"rule_selected_idx_{st.session_state['rule_select_suffix']}",
        )
        selected_rule = rules_admin[rule_selected_idx] if rule_selected_idx is not None else None

        col_edit, col_toggle = st.columns(2)
        with col_edit:
            if st.button("✏️ 수정", disabled=selected_rule is None, key="rule_edit_btn", use_container_width=True):
                open_edit_rule_dialog(selected_rule)
        with col_toggle:
            if selected_rule is not None and not selected_rule["is_active"]:
                if st.button("♻️ 재활성화", key="rule_activate_btn", use_container_width=True):
                    category_rule_service.activate_rule(selected_rule["id"])
                    st.session_state["rule_msg"] = f"'{selected_rule['keyword']}' 규칙을 재활성화했습니다."
                    st.session_state["rule_clear_selection"] = True
                    st.rerun()
            else:
                if st.button("🚫 비활성화", disabled=selected_rule is None, key="rule_deactivate_btn", use_container_width=True):
                    open_deactivate_rule_dialog(selected_rule)

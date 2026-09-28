import streamlit as st

from db.database import init_db

st.set_page_config(page_title="사업용 통장 거래관리", layout="wide")


@st.cache_resource
def _init_db_once() -> bool:
    init_db()
    return True


_init_db_once()

pages = [
    st.Page("views/dashboard_view.py", title="대시보드", icon="🏠", default=True),
    st.Page("views/transaction_list_view.py", title="거래내역", icon="📋"),
    st.Page("views/transaction_form_view.py", title="거래등록", icon="📝"),
    st.Page("views/bank_import_view.py", title="통장 가져오기", icon="🏦"),
    st.Page("views/card_view.py", title="법인카드", icon="💳"),
    st.Page("views/master_data_view.py", title="기준정보 관리", icon="🗂️"),
    st.Page("views/settings_view.py", title="설정", icon="⚙️"),
]

nav = st.navigation(pages)
nav.run()

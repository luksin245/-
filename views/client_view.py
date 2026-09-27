import streamlit as st

from services import client_service

st.title("🏢 거래처")
st.info("거래처 등록/수정/삭제 관리 화면은 준비 중입니다. (4단계에서 구현 예정)")

clients = client_service.get_clients()
if clients:
    st.write(f"현재 등록된 거래처: {len(clients)}건")
    st.dataframe(
        [{"거래처명": c["name"]} for c in clients],
        hide_index=True,
        use_container_width=True,
    )
else:
    st.write("아직 등록된 거래처가 없습니다. 거래등록 화면에서 새 거래처를 입력하면 자동으로 등록됩니다.")

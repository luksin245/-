import streamlit as st

from services import transaction_service

st.title("📋 거래내역")
st.info("상세 목록 조회 / 검색 / 필터 / 수정 / 삭제 기능은 준비 중입니다. (2단계에서 구현 예정)")

count = transaction_service.count_transactions()
st.metric("현재까지 저장된 거래 건수", f"{count:,}건")

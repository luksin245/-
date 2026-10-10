"""취업규칙 검토 웹 화면.

실행: python -m streamlit run app.py
"""

import io

import pandas as pd
import streamlit as st

from checks import MISSING, OK, PARTIAL, PRESENT, REVIEW, VIOLATION, check_required, check_violations
from law_db import LawDB
from rule_parser import extract_text, split_articles

ICON = {PRESENT: "✅", PARTIAL: "⚠️", MISSING: "❌", VIOLATION: "🚨", REVIEW: "🔍", OK: "✅"}

st.set_page_config(page_title="취업규칙 검토", page_icon="📋", layout="wide")


@st.cache_resource
def load_laws():
    return LawDB("laws")


@st.cache_data
def analyze(pdf_bytes):
    text = extract_text(pdf_bytes)
    articles = split_articles(text)
    body = [a for a in articles if not a["부칙"]]
    return text, articles, check_required(body), check_violations(articles)


def show_law(db, law, label):
    a = db.article(law, label)
    if a:
        st.markdown(f"**{a['법령명']} {a['조문']}({a['제목']})** · 시행 {a['법령시행일자']}")
        st.text(a["내용"])
    else:
        st.caption(f"{law} {label}: 법령 데이터가 없습니다. download_laws.py를 다시 실행하세요.")


def to_excel(articles, required, findings):
    req_rows = [{
        "번호": r["번호"], "항목": r["항목"], "상태": r["상태"],
        "세부": "\n".join(
            f"{d['세부']}{' (해당 시)' if d['해당 시만'] else ''}: {', '.join(d['조항']) or '없음'}"
            for d in r["세부"]),
    } for r in required]
    find_rows = [{
        "상태": f["상태"], "주제": f["주제"], "조항": f["조항"], "발췌": f["발췌"], "설명": f["설명"],
        "근거": ", ".join(f"{law} {label}" for law, label in f["근거"]),
    } for f in findings]
    art_rows = [{k: a[k] for k in ("조항", "제목", "장", "내용")} for a in articles]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(req_rows).to_excel(xw, sheet_name="필수기재사항", index=False)
        pd.DataFrame(find_rows).to_excel(xw, sheet_name="위반점검", index=False)
        pd.DataFrame(art_rows).to_excel(xw, sheet_name="조항목록", index=False)
    return buf.getvalue()


db = load_laws()

with st.sidebar:
    st.header("법령 데이터")
    laws = db.summary()
    if laws:
        for name, date, count in laws:
            st.caption(f"{name} · 시행 {date} · {count}개 조문")
    else:
        st.warning("laws 폴더에 법령 데이터가 없습니다. 먼저 download_laws.py를 실행하세요.")
    st.divider()
    st.caption("출처: 국가법령정보센터(www.law.go.kr)")

st.title("📋 취업규칙 검토")
st.caption("키워드와 숫자를 기준으로 한 1차 점검입니다. 법률 자문이 아니므로, 결과는 반드시 법령 원문과 함께 확인하세요.")

uploaded = st.file_uploader("취업규칙 PDF 파일을 올려 주세요", type="pdf")
if not uploaded:
    st.stop()

with st.spinner("PDF를 읽고 점검하는 중..."):
    try:
        text, articles, required, findings = analyze(uploaded.getvalue())
    except Exception as e:
        st.error(f"PDF를 읽지 못했습니다: {e}")
        st.stop()

if not text.strip():
    st.error("PDF에서 글자를 읽을 수 없습니다. 스캔한 이미지 PDF는 지원하지 않습니다. 한글·워드 원본에서 PDF로 다시 저장해 주세요.")
    st.stop()
if not articles:
    st.error("'제1조(목적)' 같은 조항 제목을 찾지 못했습니다. 아래 추출된 텍스트를 확인해 주세요.")
    st.text(text[:3000])
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("조항 수", sum(not a["부칙"] for a in articles))
c2.metric("필수 기재사항 누락", sum(r["상태"] in (MISSING, PARTIAL) for r in required))
c3.metric("위반 의심", sum(f["상태"] == VIOLATION for f in findings))
c4.metric("확인 필요", sum(f["상태"] == REVIEW for f in findings))

tab1, tab2, tab3, tab4 = st.tabs(["① 필수 기재사항", "② 위반 점검", "③ 조항 목록", "④ 보고서 다운로드"])

with tab1:
    st.write("근로기준법 제93조에 따라 취업규칙에 반드시 적어야 하는 사항입니다.")
    with st.expander("근로기준법 제93조 원문 보기"):
        show_law(db, "근로기준법", "제93조")
    for r in required:
        with st.expander(f"{ICON[r['상태']]} {r['번호']}. {r['항목']} — {r['상태']}"):
            for d in r["세부"]:
                where = ", ".join(d["조항"]) if d["조항"] else "찾지 못함"
                note = " (해당하는 경우에만 필요)" if d["해당 시만"] else ""
                st.markdown(f"- **{d['세부']}**{note}: {where}")
    st.caption("13호 '그 밖에 근로자 전체에 적용될 사항'은 사업장마다 달라 자동 점검하지 않습니다.")

with tab2:
    if not findings:
        st.info("점검할 항목을 찾지 못했습니다.")
    for f in findings:
        title = f"{ICON[f['상태']]} [{f['상태']}] {f['주제']}" + (f" — {f['조항']}" if f["조항"] else "")
        with st.expander(title, expanded=f["상태"] == VIOLATION):
            st.write(f["설명"])
            if f["발췌"]:
                st.markdown("**취업규칙 문구**")
                st.info(f["발췌"])
            st.markdown("**근거 법령**")
            for law, label in f["근거"]:
                show_law(db, law, label)

with tab3:
    st.write(f"PDF에서 {len(articles)}개 조항을 찾았습니다. 조항이 빠지거나 잘못 나뉘었다면 알려 주세요.")
    for a in articles:
        head = f"{a['조항']}" + (f"({a['제목']})" if a["제목"] else "")
        with st.expander(f"{head}" + (f" · {a['장']}" if a["장"] else "")):
            st.text(a["내용"])
    with st.expander("PDF에서 추출한 전체 텍스트"):
        st.text(text)

with tab4:
    st.write("점검 결과를 엑셀 파일로 내려받습니다. (필수기재사항, 위반점검, 조항목록 시트)")
    st.download_button(
        "📥 엑셀 보고서 다운로드",
        data=to_excel(articles, required, findings),
        file_name=f"{uploaded.name.rsplit('.', 1)[0]}_검토결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

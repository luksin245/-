"""취업규칙 검토 웹 화면.

실행: python -m streamlit run app.py
"""

import io
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from checks import (MISSING, OK, PARTIAL, PRESENT, REVIEW, VIOLATION, check_required, check_violations,
                    skipped_items)
from law_changes import (detect_base_date, fmt, is_relevant, law_changes,
                         load_history, related_articles, short_name)
from law_db import LawDB
from revision import (DELETE, FONTS, NEW, compare_rows, diff_html, diff_segments, draft_rows, numbered_rows,
                      plan_rules, strip_internal_refs, to_docx, to_rules_docx)
from rule_parser import extract_text, split_articles

ICON = {PRESENT: "✅", PARTIAL: "⚠️", MISSING: "❌", VIOLATION: "🚨", REVIEW: "🔍", OK: "✅"}

# 실행 위치와 상관없이 app.py 옆의 laws 폴더를 쓴다
LAWS_DIR = Path(__file__).resolve().parent / "laws"

st.set_page_config(page_title="취업규칙 검토", page_icon="📋", layout="wide")
# 화면 글자 크기: Streamlit은 대부분 rem 단위를 쓰므로 기준 크기만 키우면 전체가 커진다
st.markdown("""<style>
html { font-size: 19px; }
.stMarkdown p, .stMarkdown li, .stText, .stCaption, .stTextArea textarea, .stTextInput input { font-size: 1rem; }
.stTabs [data-baseweb="tab"] p { font-size: 1.05rem; }
</style>""", unsafe_allow_html=True)


@st.cache_resource
def load_laws():
    return LawDB(LAWS_DIR)


@st.cache_data
def analyze(pdf_bytes):
    text = extract_text(pdf_bytes)
    articles = split_articles(text)
    body = [a for a in articles if not a["부칙"]]
    return text, articles, check_required(body), check_violations(articles)


@st.cache_data
def cached_law_changes(base, laws_dir):
    history = load_history(laws_dir)
    changes, short = law_changes(history, base)
    first = min((h["버전"][0]["시행일자"] for h in history.values()), default=None)
    return bool(history), changes, short, first


def show_law(db, law, label):
    a = db.article(law, label)
    if a:
        st.markdown(f"**{a['법령명']} {a['조문']}({a['제목']})** · 시행 {a['법령시행일자']}")
        st.text(a["내용"])
    else:
        st.caption(f"{law} {label}: 법령 데이터가 없습니다. download_laws.py를 다시 실행하세요.")


def change_title(c):
    """법령 개정 한 건의 제목: '⏳ 시행 예정 · 남녀고용평등법 제18조의2(배우자 출산휴가) [개정] — 시행 2025. 2. 23.'"""
    when = ", ".join(f"{fmt(d)} {kind}".strip() for d, kind in c["이력"])
    tag = "⏳ 시행 예정 · " if c["시행예정"] else ""
    return f"{tag}{short_name(c['법령명'])} {c['조문']}({c['제목']}) [{c['구분']}] — 시행 {when}"


def show_law_change(c):
    """법 조문의 개정 전·후를 나란히 보여 준다 (바뀐 부분은 빨간 밑줄)."""
    left, right = st.columns(2)
    old_seg, new_seg = diff_segments(c["이전"], c["현재"])
    with left:
        st.markdown("**개정 전**")
        st.markdown(diff_html(old_seg) if c["이전"] else "(없음)", unsafe_allow_html=True)
    with right:
        st.markdown("**개정 후**")
        st.markdown(diff_html(new_seg) if c["현재"] else "(삭제)", unsafe_allow_html=True)


def to_excel(articles, required, findings, revision_rows=()):
    req_rows = [{
        "번호": r["번호"], "항목": r["항목"], "상태": r["상태"],
        "세부": "\n".join(
            f"{d['세부']}: {', '.join(d['조항']) or '없음'}"
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
        if revision_rows:
            pd.DataFrame(revision_rows).to_excel(xw, sheet_name="신구대조표", index=False)
    return buf.getvalue()


END = "(본칙 맨 끝)"


def edit_rows(rows, prefix, body=()):
    """신구대조표 행을 화면에서 고칠 수 있게 보여 주고, 포함하기로 한 행을 돌려준다.
    body가 있으면 신설 조항마다 넣을 위치(어느 조 다음)를 고를 수 있다."""
    final = []
    places = [END] + [a["조항"] for a in body]
    titles = {a["조항"]: a["제목"] for a in body}
    for i, r in enumerate(rows):
        key = f"{prefix}-{i}"
        head = f"[{r['구분']}] " + (r["조항"] or r["개정안"].split("\n", 1)[0][:30])
        # 아직 현행과 같은 개정 행(법 개정 탭·직접 추가에서 온 행)은 문서에 들어가지 않으므로 눈에 띄게 표시한다
        current_text = st.session_state.get(f"{key}-new", r["개정안"])
        unchanged = r["구분"] == "개정" and current_text.strip() == r["현행"].strip()
        if unchanged:
            head = f"✏️ {head} — 아직 고친 내용 없음 (문서에 안 들어감)"
        with st.expander(head):
            if unchanged:
                where = f" ({r['출처']})" if r.get("출처") else ""
                st.warning(f"이 조항은 직접 고치려고 추가한 조항입니다{where}. 개정(안) 칸을 고쳐야 신구대조표와 개정 취업규칙에 들어갑니다.")
            if r.get("법개정") or r.get("근거"):
                with st.container(border=True):
                    if r.get("법개정"):
                        st.markdown("##### 📜 관련 법령이 이렇게 바뀌었습니다")
                        for c in r["법개정"]:
                            st.markdown(f"**{change_title(c)}**")
                            show_law_change(c)
                    shown = {(c["법령명"], c["조문"]) for c in r.get("법개정", [])}
                    basis = [b for b in dict.fromkeys(r.get("근거", [])) if tuple(b) not in shown]
                    if basis:
                        st.markdown("##### 📜 근거 법령 (현행)")
                        for law, label in basis:
                            show_law(db, law, label)
            include = st.checkbox("신구대조표에 포함", value=True, key=f"{key}-on")
            left, right = st.columns(2)
            with left:
                st.markdown("**현행**")
                st.text(r["현행"] or "<신 설>")
            with right:
                st.markdown("**개정(안)** — 직접 고칠 수 있습니다")
                lines = r["개정안"].count("\n") + len(r["개정안"]) // 45 + 2
                revised = st.text_area("개정안", r["개정안"], key=f"{key}-new",
                                       height=min(400, max(100, lines * 24)), label_visibility="collapsed",
                                       disabled=r["구분"] == DELETE)
            reason = st.text_area("비고(개정 사유)", r["사유"], key=f"{key}-why",
                                  height=max(68, 28 * (r["사유"].count("\n") + 1)))
            position = r.get("위치")
            if r["구분"] == NEW and not r["조항"] and body:
                default = places.index(position) if position in places else 0
                choice = st.selectbox("넣을 위치", places, index=default, key=f"{key}-pos",
                                      format_func=lambda x: x if x == END else f"{x}({titles.get(x, '')}) 다음")
                position = None if choice == END else choice
            if r["구분"] not in (NEW, DELETE) and revised != r["현행"]:
                _, after = diff_segments(r["현행"], revised)
                st.markdown("**바뀐 부분 미리보기**")
                st.markdown(diff_html(after), unsafe_allow_html=True)
        if include and (r["구분"] in (NEW, DELETE) or revised.strip() != r["현행"].strip()):
            final.append({**r, "개정안": revised, "사유": reason, "위치": position})
    return final


def law_change_tab(articles, text):
    """기준일 이후 법 개정 사항. 신구대조표에 추가하기로 고른 행을 돌려준다."""
    body = [a for a in articles if not a["부칙"]]
    detected = detect_base_date(text)
    default = datetime.strptime(detected, "%Y%m%d").date() if detected else date(2020, 1, 1)
    base_date = st.date_input("취업규칙 기준일 (마지막으로 개정해 시행한 날)", value=default,
                              min_value=date(1990, 1, 1), max_value=date(2100, 12, 31))
    if detected:
        st.caption(f"부칙에서 찾은 가장 늦은 날짜({fmt(detected)})를 기준일로 넣었습니다. 다르면 고쳐 주세요.")
    else:
        st.warning("부칙에서 시행일을 찾지 못했습니다. 취업규칙을 마지막으로 개정한 날짜를 직접 입력해 주세요.")
    base = base_date.strftime("%Y%m%d")

    has_history, changes, short, first = cached_law_changes(base, str(LAWS_DIR))
    if not has_history:
        st.warning("법령 개정 이력 데이터가 없습니다. 새 버전의 download_laws.py를 실행해 개정 이력을 받아 주세요.")
        st.code("python download_laws.py --oc 인증키", language=None)
        return []
    if short:
        st.warning(f"다음 법령은 기준일까지 거슬러 올라가는 이력이 없어 {fmt(first)} 이후 개정만 보여 줍니다: "
                   f"{', '.join(short_name(x) for x in short)}. 더 이전부터 보려면 "
                   f"`python download_laws.py --oc 인증키 --since {base}` 로 다시 받으세요.")

    for c in changes:
        c["관련"] = related_articles(c, body)
    related = [c for c in changes if c["관련"]]
    others = [c for c in changes if not c["관련"] and not is_relevant(c)]

    m1, m2, m3 = st.columns(3)
    m1.metric("기준일 이후 바뀐 조문", len(changes))
    m2.metric("취업규칙 관련 조항 있음", len(related))
    m3.metric("시행 예정", sum(c["시행예정"] for c in changes))
    if not changes:
        st.success(f"{fmt(base)} 이후 바뀐 조문이 없습니다.")
        return []

    picked = {}  # 취업규칙 조항 → 행

    def reason(c):
        return f"{short_name(c['법령명'])} {c['조문']} {c['구분']}({fmt(c['이력'][-1][0])} 시행)"

    st.subheader("📌 취업규칙에 관련 조항이 있는 개정")
    st.caption("법이 바뀐 내용을 보고, 고쳐야 할 취업규칙 조항을 체크하면 신구대조표에 들어갑니다.")
    for i, c in enumerate(related):
        with st.expander(change_title(c), expanded=False):
            show_law_change(c)
            st.markdown("**관련 취업규칙 조항**")
            for label in c["관련"]:
                a = next(x for x in body if x["조항"] == label)
                if st.checkbox(f"{label}({a['제목']}) 신구대조표에 추가", key=f"law-{i}-{label}"):
                    row = picked.setdefault(label, {"구분": "개정", "조항": label, "현행": a["내용"],
                                                    "개정안": strip_internal_refs(a["내용"]), "사유": "",
                                                    "출처": "③ 법 개정 반영 탭에서 추가",
                                                    "법개정": []})
                    row["사유"] = "\n".join(filter(None, [row["사유"], reason(c)]))
                    row["법개정"].append(c)
                st.text(a["내용"])

    if others:
        with st.expander(f"기타 개정 {len(others)}건 (벌칙·위원회 등 취업규칙과 관련이 적은 조문)"):
            for c in others:
                st.markdown(f"- {change_title(c)}")
    return list(picked.values())


def revision_tab(articles, required, findings, file_name, law_rows=()):
    mode = st.radio("만드는 방법", ["점검 결과로 개정안 초안 만들기", "개정본 PDF와 비교하기"], horizontal=True)

    if mode.startswith("점검"):
        st.caption("위반 의심·확인 필요 항목과 빠진 필수 기재사항으로 개정안 초안을 만들었습니다. "
                   "사업장 실정에 맞게 고친 뒤 내려받으세요. 신설 조항의 '제○조'와 '○○' 부분은 직접 채워 주세요. "
                   "고치는 조항에서는 '제66조 제1항에 따라'처럼 다른 조항을 가리키는 표현을 지웠습니다(다른 법령 인용은 유지).")
        rows = draft_rows(articles, required, findings)
        by_label = {r["조항"]: r for r in rows if r["조항"]}
        for r in law_rows:  # '법 개정 반영' 탭에서 고른 조항
            if r["조항"] in by_label:
                by_label[r["조항"]]["사유"] += "\n" + r["사유"]
                by_label[r["조항"]]["법개정"] = by_label[r["조항"]].get("법개정", []) + r["법개정"]
            else:
                rows.append(dict(r))
        body = [a for a in articles if not a["부칙"]]
        extra = st.multiselect("직접 개정할 조항 추가", [a["조항"] for a in body],
                               format_func=lambda x: next(f"{x}({a['제목']})" for a in body if a["조항"] == x))
        drafted = {r["조항"] for r in rows}
        for label in extra:
            if label not in drafted:
                a = next(a for a in body if a["조항"] == label)
                rows.append({"구분": "개정", "조항": label, "현행": a["내용"], "개정안": strip_internal_refs(a["내용"]), "사유": "",
                             "출처": "직접 개정할 조항 추가"})
        prefix = f"draft-{file_name}"
    else:
        st.caption("개정한 취업규칙 PDF를 올리면 현행과 조항별로 비교합니다. 조항은 제목으로 먼저 맞추므로 번호만 바뀐 조항은 제외됩니다. "
                   "제목까지 바뀐 조항은 삭제·신설로 나올 수 있습니다.")
        revised_pdf = st.file_uploader("개정본 PDF", type="pdf", key="revised-pdf")
        if not revised_pdf:
            return []
        try:
            _, new_articles, _, _ = analyze(revised_pdf.getvalue())
        except Exception as e:
            st.error(f"개정본 PDF를 읽지 못했습니다: {e}")
            return []
        rows = compare_rows(articles, new_articles)
        prefix = f"compare-{file_name}-{revised_pdf.name}"

    if not rows:
        st.info("바뀐 조항이 없습니다.")
        return []

    drafting = mode.startswith("점검")
    body = [a for a in articles if not a["부칙"]]
    final = edit_rows(rows, prefix, body if drafting else ())
    st.divider()
    base_name = file_name.rsplit(".", 1)[0]
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    st.write(f"반영할 조항: {len(final)}개")
    if not final:
        return final

    if drafting:
        numbering = st.radio("신설 조항 번호 매기기", ["가지번호로 끼워 넣기 (예: 제40조의2) — 기존 조 번호 유지", "제1조부터 전체 번호 다시 매기기"],
                             help="가지번호 방식은 다른 조항의 번호가 바뀌지 않아 개정이 간단합니다(권장).")
        renumber = numbering.startswith("제1조")
        seq, mapping = plan_rules(articles, final, renumber)
        table_rows = numbered_rows(seq, final)
        new_items = [it for it in seq if it["종류"] == "신설"]
        if new_items:
            lines = []
            for it in new_items:
                title = (it["내용"].split("\n", 1)[0])[:40]
                where = f"{mapping.get(it['위치'], it['위치'])} 다음" if it.get("위치") else "본칙 맨 끝"
                lines.append(f"- **{it['조항']}** ← {where} · {title}")
            st.markdown("**신설 조항이 들어갈 자리**\n" + "\n".join(lines))
        if renumber and mapping:
            moved = sum(1 for old, new_label in mapping.items() if old != new_label)
            st.caption(f"번호가 바뀌는 기존 조항 {moved}개. 본문 속 '제○조' 인용도 새 번호로 바꿨지만(다른 법령 인용은 제외), "
                       "최종본에서 한 번 더 확인하세요. 번호만 바뀐 조항은 신구대조표에 넣지 않습니다.")
    else:
        table_rows = final

    font = st.selectbox("글꼴 (모든 문서 공통)", FONTS,
                        help="함초롬바탕은 한글(한컴오피스)이 설치된 PC에 있습니다. 없으면 바탕을 고르세요.")
    left, right = st.columns(2)
    with left:
        st.subheader("📄 신구대조표")
        st.caption("현행 / 개정 안 / 비고 3칸 표 (A4 가로)")
        title = st.text_input("신구대조표 제목", "취업규칙 신구대조표")
        with_reason = st.checkbox("비고에 개정 사유 넣기", value=True)
        highlight = st.checkbox("바뀐 부분 밑줄 표시", value=False)
        st.download_button("📥 신구대조표 다운로드 (.docx)",
                           data=to_docx(table_rows, title, font=font, highlight=highlight, with_reason=with_reason),
                           file_name=f"{base_name}_신구대조표.docx", mime=docx_mime, use_container_width=True)
    with right:
        st.subheader("📘 개정 취업규칙")
        if drafting:
            st.caption("현행 취업규칙 전체에 위 내용을 반영한 문서 (A4 세로). 신설 조항은 고른 자리에 들어갑니다.")
            rules_title = st.text_input("문서 제목", "취업규칙")
            effective = st.text_input("개정 시행일 (새 부칙에 들어감)", placeholder="예: 2026. 12. 1.  (비우면 ○○○○년 ○월 ○일)")
            st.download_button("📥 검토용 초안 (개정 파란색·신설 초록색)",
                               data=to_rules_docx(articles, seq, f"{rules_title} (개정안)", font=font, mark=True,
                                                  effective=effective),
                               file_name=f"{base_name}_개정안_검토용.docx", mime=docx_mime, use_container_width=True)
            st.download_button("📥 최종본 (색 표시 없음)",
                               data=to_rules_docx(articles, seq, rules_title, font=font, mark=False, effective=effective),
                               file_name=f"{base_name}_개정_최종본.docx", mime=docx_mime, use_container_width=True,
                               type="primary")
        else:
            st.caption("개정본 PDF와 비교하는 경우에는 올린 개정본이 곧 최종본이므로 따로 만들지 않습니다.")
    return table_rows


db = load_laws()

with st.sidebar:
    st.header("법령 데이터")
    laws = db.summary()
    if laws:
        for name, effective, count in laws:
            st.caption(f"{name} · 시행 {effective} · {count}개 조문")
    else:
        st.warning("법령 데이터가 없습니다. 이 프로그램과 같은 폴더에서 download_laws.py를 실행하세요.")
        st.caption(f"찾은 위치: {LAWS_DIR}")
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

tab_req, tab_check, tab_law, tab_rev, tab_list, tab_report = st.tabs(
    ["① 필수 기재사항", "② 위반 점검", "③ 법 개정 반영", "④ 신구대조표", "⑤ 조항 목록", "⑥ 보고서 다운로드"])

with tab_req:
    st.write("근로기준법 제93조와 고용노동부 표준취업규칙(2026. 2.)의 [필수] 조항을 기준으로, 취업규칙에 반드시 적어야 하는 사항입니다.")
    with st.expander("근로기준법 제93조 원문 보기"):
        show_law(db, "근로기준법", "제93조")
    for r in required:
        with st.expander(f"{ICON[r['상태']]} {r['번호']}. {r['항목']} — {r['상태']}"):
            for d in r["세부"]:
                where = ", ".join(d["조항"]) if d["조항"] else "찾지 못함"
                st.markdown(f"- **{d['세부']}**: {where}")
    st.caption(f"해당하는 경우에만 적으면 되는 항목({', '.join(skipped_items())})과 "
               "13호 '그 밖에 근로자 전체에 적용될 사항'은 사업장마다 달라 점검하지 않습니다.")

with tab_check:
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

with tab_list:
    st.write(f"PDF에서 {len(articles)}개 조항을 찾았습니다. 조항이 빠지거나 잘못 나뉘었다면 알려 주세요.")
    for a in articles:
        head = f"{a['조항']}" + (f"({a['제목']})" if a["제목"] else "")
        with st.expander(f"{head}" + (f" · {a['장']}" if a["장"] else "")):
            st.text(a["내용"])
    with st.expander("PDF에서 추출한 전체 텍스트"):
        st.text(text)

with tab_law:
    law_rows = law_change_tab(articles, text)

with tab_rev:
    final_rows = revision_tab(articles, required, findings, uploaded.name, law_rows)

with tab_report:
    st.write("점검 결과를 엑셀 파일로 내려받습니다. (필수기재사항, 위반점검, 조항목록, 신구대조표 시트)")
    st.download_button(
        "📥 엑셀 보고서 다운로드",
        data=to_excel(articles, required, findings, final_rows),
        file_name=f"{uploaded.name.rsplit('.', 1)[0]}_검토결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

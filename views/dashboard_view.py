from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from services import dashboard_service
from utils.formatting import format_amount

# 팔레트 (dataviz 스킬 가이드의 검증된 기본 팔레트에서 가져옴)
COLOR_INCOME = "#2a78d6"   # 카테고리 슬롯 1: blue
COLOR_EXPENSE = "#eb6834"  # 카테고리 슬롯 2: orange
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
GRIDLINE = "#e1e0d9"

TYPE_LABELS = {"income": "수입", "expense": "지출"}

st.title("🏠 대시보드")

# ---------- 조회 기간 ----------
st.subheader("조회 기간")

preset_col, start_col, end_col = st.columns([1, 1, 1])
with preset_col:
    preset = st.selectbox(
        "빠른 선택", dashboard_service.PERIOD_PRESETS, index=0, key="dash_preset"
    )

custom_start = None
custom_end = None
if preset == "직접 선택":
    with start_col:
        custom_start = st.date_input("시작일", value=date.today().replace(day=1), key="dash_custom_start")
    with end_col:
        custom_end = st.date_input("종료일", value=date.today(), key="dash_custom_end")

try:
    start, end = dashboard_service.get_period_range(preset, custom_start, custom_end)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.caption(f"조회 기간: {start.isoformat()} ~ {end.isoformat()}")

data = dashboard_service.get_dashboard_data(start, end)
summary = data["summary"]
prev_summary = data["prev_summary"]
prev_start, prev_end = data["prev_period"]

if summary["count"] == 0:
    st.info("해당 기간에 거래내역이 없습니다.")
    st.stop()

st.divider()

# ---------- KPI 카드 ----------


def _pct_delta_text(current: int, previous: int) -> str | None:
    pct = dashboard_service.calc_percent_change(current, previous)
    if pct is None:
        return None
    return f"{pct:+.1f}%"


kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
kpi_col1.metric(
    "총수입",
    f"{format_amount(summary['total_income'])}원",
    delta=_pct_delta_text(summary["total_income"], prev_summary["total_income"]),
)
kpi_col2.metric(
    "총지출",
    f"{format_amount(summary['total_expense'])}원",
    delta=_pct_delta_text(summary["total_expense"], prev_summary["total_expense"]),
    delta_color="inverse",  # 지출은 증가하면 부정적인 신호이므로 색상을 반대로
)

net_diff = summary["net_amount"] - prev_summary["net_amount"]
net_delta_text = None
if prev_summary["total_income"] > 0 or prev_summary["total_expense"] > 0:
    net_delta_text = f"{'+' if net_diff >= 0 else ''}{format_amount(net_diff)}원"
kpi_col3.metric(
    "순현금흐름",
    f"{format_amount(summary['net_amount'])}원",
    delta=net_delta_text,
)
kpi_col4.metric(
    "거래건수",
    f"{summary['count']:,}건",
    delta=_pct_delta_text(summary["count"], prev_summary["count"]),
    delta_color="off",
)

st.caption(f"직전 비교기간: {prev_start.isoformat()} ~ {prev_end.isoformat()} (선택 기간과 동일한 일수)")

# ---------- 추가 요약 ----------
income_avg = dashboard_service.calc_average(summary["total_income"], summary["income_count"])
expense_avg = dashboard_service.calc_average(summary["total_expense"], summary["expense_count"])

extra_col1, extra_col2, extra_col3, extra_col4 = st.columns(4)
extra_col1.metric("수입 거래 건수", f"{summary['income_count']:,}건")
extra_col2.metric("지출 거래 건수", f"{summary['expense_count']:,}건")
extra_col3.metric("평균 수입 거래금액", f"{format_amount(income_avg)}원" if income_avg is not None else "-")
extra_col4.metric("평균 지출 거래금액", f"{format_amount(expense_avg)}원" if expense_avg is not None else "-")

st.divider()

# ---------- 회계구분 기준 요약 (총수입/총지출과는 다른 개념) ----------
st.subheader("회계구분 기준 요약 (참고)")
st.caption(
    "⚠️ 위 총수입/총지출은 **통장 입금·출금 기준**이고, 아래 총매출/총비용은 "
    "거래마다 지정한 **회계구분**(매출/비용/자금이동/비매출입금/비비용출금/미분류) 기준입니다. "
    "예를 들어 대표자가 법인에 자금을 입금하면 통장 기준으로는 '수입'이지만, "
    "회계구분을 '비매출입금'으로 지정하면 매출로 집계되지 않습니다. 두 수치는 서로 다른 개념이므로 혼동하지 마세요."
)
accounting_summary = data["accounting_summary"]
acct_col1, acct_col2 = st.columns(2)
acct_col1.metric("총매출 (회계구분 기준)", f"{format_amount(accounting_summary['total_revenue'])}원")
acct_col2.metric("총비용 (회계구분 기준)", f"{format_amount(accounting_summary['total_cost'])}원")
if accounting_summary["card_cost"]:
    acct_col2.caption(
        f"통장 {format_amount(accounting_summary['bank_cost'])}원 + "
        f"법인카드 {format_amount(accounting_summary['card_cost'])}원 (카드는 이용일자 기준)"
    )

st.divider()

# ---------- 차트 1: 월별 수입/지출 추이 ----------
st.subheader("월별 수입 · 지출 추이")

trend_df = pd.DataFrame(data["monthly_trend"])
trend_long = trend_df.melt(id_vars="month", value_vars=["income", "expense"], var_name="구분", value_name="금액")
trend_long["구분"] = trend_long["구분"].map(TYPE_LABELS)
trend_long["금액_표시"] = trend_long["금액"].apply(format_amount)

fig_trend = px.bar(
    trend_long,
    x="month",
    y="금액",
    color="구분",
    barmode="group",
    text="금액_표시",
    color_discrete_map={"수입": COLOR_INCOME, "지출": COLOR_EXPENSE},
    category_orders={"구분": ["수입", "지출"]},
    labels={"month": "월", "금액": "금액(원)"},
)
fig_trend.update_traces(textposition="outside", cliponaxis=False)
fig_trend.update_layout(
    template="plotly_white",
    font_color="#0b0b0b",
    legend_title_text="",
    yaxis_gridcolor=GRIDLINE,
    xaxis_title=None,
    margin=dict(t=10, b=10),
)
st.plotly_chart(fig_trend, use_container_width=True, key="dash_chart_trend")

st.divider()

# ---------- 차트 2: 지출 카테고리별 금액 ----------
st.subheader("지출 카테고리별 금액")

expense_rows = data["expense_by_category"]
if not expense_rows:
    st.info("지출 데이터가 없습니다.")
else:
    cat_df = pd.DataFrame(expense_rows).sort_values("total", ascending=True)
    total_expense_amount = cat_df["total"].sum()
    cat_df["비중"] = cat_df["total"] / total_expense_amount * 100
    cat_df["표시"] = cat_df.apply(
        lambda r: f"{format_amount(r['total'])}원 ({r['비중']:.1f}%)", axis=1
    )

    fig_cat = px.bar(
        cat_df,
        x="total",
        y="category_name",
        orientation="h",
        text="표시",
        color="total",
        color_continuous_scale=SEQUENTIAL_BLUE,
        labels={"total": "금액(원)", "category_name": ""},
    )
    fig_cat.update_traces(textposition="outside", cliponaxis=False)
    fig_cat.update_layout(
        template="plotly_white",
        font_color="#0b0b0b",
        showlegend=False,
        coloraxis_showscale=False,
        xaxis_gridcolor=GRIDLINE,
        xaxis_range=[0, cat_df["total"].max() * 1.2],
        margin=dict(t=10, b=10, l=10),
    )
    st.plotly_chart(fig_cat, use_container_width=True, key="dash_chart_expense_category")

st.divider()

# ---------- 차트 3: 업무유형별 매출 ----------
st.subheader("업무유형별 매출")
REVENUE_CHART_CAPTION = (
    "통장 입금 중 회계구분이 '매출'이거나 아직 정하지 않은('미분류') 거래만 합산합니다. "
    "대표자 가수금(비매출입금)·계좌 간 이체(자금이동) 등 매출이 아니라고 표시한 입금은 제외됩니다."
)
st.caption(REVENUE_CHART_CAPTION)

work_type_rows = data["income_by_work_type"]
if not work_type_rows:
    st.info("표시할 매출 데이터가 없습니다.")
else:
    wt_df = pd.DataFrame(work_type_rows).sort_values("total", ascending=True)
    wt_df["표시"] = wt_df["total"].apply(lambda v: f"{format_amount(v)}원")

    fig_wt = px.bar(
        wt_df,
        x="total",
        y="work_type_name",
        orientation="h",
        text="표시",
        color="total",
        color_continuous_scale=SEQUENTIAL_BLUE,
        labels={"total": "금액(원)", "work_type_name": ""},
    )
    fig_wt.update_traces(textposition="outside", cliponaxis=False)
    fig_wt.update_layout(
        template="plotly_white",
        font_color="#0b0b0b",
        showlegend=False,
        coloraxis_showscale=False,
        xaxis_gridcolor=GRIDLINE,
        xaxis_range=[0, wt_df["total"].max() * 1.2],
        margin=dict(t=10, b=10, l=10),
    )
    st.plotly_chart(fig_wt, use_container_width=True, key="dash_chart_income_work_type")

st.divider()

# ---------- 차트 4: 거래처별 매출 TOP 10 ----------
st.subheader("거래처별 매출 TOP 10")
st.caption(REVENUE_CHART_CAPTION + " 거래처가 지정되지 않은 입금은 '미분류'로 합산합니다.")

client_rows = data["income_by_client"]
if not client_rows:
    st.info("표시할 매출 데이터가 없습니다.")
else:
    client_df = pd.DataFrame(client_rows).sort_values("total", ascending=True)
    client_df["표시"] = client_df["total"].apply(lambda v: f"{format_amount(v)}원")

    fig_client = px.bar(
        client_df,
        x="total",
        y="client_name",
        orientation="h",
        text="표시",
        color="total",
        color_continuous_scale=SEQUENTIAL_BLUE,
        labels={"total": "금액(원)", "client_name": ""},
    )
    fig_client.update_traces(textposition="outside", cliponaxis=False)
    fig_client.update_layout(
        template="plotly_white",
        font_color="#0b0b0b",
        showlegend=False,
        coloraxis_showscale=False,
        xaxis_gridcolor=GRIDLINE,
        xaxis_range=[0, client_df["total"].max() * 1.2],
        margin=dict(t=10, b=10, l=10),
    )
    st.plotly_chart(fig_client, use_container_width=True, key="dash_chart_income_client")

st.divider()

# ---------- 최근 거래내역 ----------
st.subheader("최근 거래내역")

recent = data["recent_transactions"]
recent_df = pd.DataFrame(recent)
recent_df["구분"] = recent_df["transaction_type"].map(TYPE_LABELS)
recent_df["금액"] = recent_df["amount"].apply(lambda v: f"{format_amount(v)}원")
recent_df["카테고리"] = recent_df["category_name"].fillna("")
recent_df["거래처"] = recent_df["client_name"].fillna("")
recent_df["거래일자"] = recent_df["transaction_date"]
recent_df["거래내용"] = recent_df["description"]

st.dataframe(
    recent_df,
    column_order=["거래일자", "거래내용", "구분", "금액", "카테고리", "거래처"],
    hide_index=True,
    use_container_width=True,
)

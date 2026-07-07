from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_utils import (
    build_data,
    construct_bar_chart,
    distribution_donut,
    format_score,
    inject_css,
    kpi_card,
    kra_header,
    latest_period,
    load_workbook,
    metric_delta,
    normalize_score,
    previous_period,
    short_text,
    sort_for_performance,
    survey_period_score,
    trend_bar_chart,
    trend_data,
    wrap_label,
)

st.set_page_config(
    page_title="KRA Survey Indices Dashboard",
    page_icon="assets/kra_logo.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_WORKBOOK = "survey_indices_entry_sheet_mapped.xlsx"

st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(kra_header(), unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_load_workbook(uploaded_bytes: bytes | None):
    if uploaded_bytes:
        return load_workbook(io.BytesIO(uploaded_bytes))
    return load_workbook(None, DEFAULT_WORKBOOK)


def dataframe_download(df: pd.DataFrame, label: str, filename: str):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv, file_name=filename, mime="text/csv", use_container_width=True)


def display_table(df: pd.DataFrame, height: int = 235):
    st.dataframe(df, use_container_width=True, hide_index=True, height=height)


with st.sidebar:
    st.markdown("### Navigation")
    page = st.radio(
        "Choose page",
        [
            "🏠 Executive Summary",
            "▮ Construct Performance",
            "↗ Time Trend",
            "👥 Segment Analysis",
            "▤ Survey Details",
            "☁ Upload Data",
            "ℹ About",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    uploaded = st.file_uploader("Upload updated entry workbook", type=["xlsx"], help="Use the mapped survey entry workbook.")
    st.caption("Keep the same sheet names: Survey_Master, Construct_Master, Corporate_Data, Departmental_Data, Segment_Data and Score_Type_Rules.")

uploaded_bytes = uploaded.getvalue() if uploaded is not None else None
try:
    sheets = cached_load_workbook(uploaded_bytes)
    survey_master, construct_master, all_data, segment_data, score_rules = build_data(sheets)
except Exception as exc:
    st.error(f"Could not read workbook: {exc}")
    st.stop()

if all_data.empty:
    st.warning("No survey data found in Corporate_Data or Departmental_Data.")
    st.stop()

# Top filters exactly like the reference dashboard.
f0, f1, f2, f3, f4 = st.columns([1.4, 1.25, 2.0, 2.1, 1.3])

survey_type = f1.selectbox("Survey Type", sorted(all_data["Survey_Type"].dropna().unique().tolist()), label_visibility="visible")
type_data = all_data[all_data["Survey_Type"] == survey_type].copy()
survey_options = type_data[["Survey_ID", "Survey_Name"]].drop_duplicates().sort_values(["Survey_Name", "Survey_ID"])
survey_labels = (survey_options["Survey_ID"] + " - " + survey_options["Survey_Name"]).tolist()
chosen_label = f2.selectbox("Survey", survey_labels)
survey_id = chosen_label.split(" - ", 1)[0]
survey_df = type_data[type_data["Survey_ID"] == survey_id].copy()
period_options = survey_df[["Survey_Period", "Period_Sort"]].drop_duplicates().sort_values("Period_Sort", ascending=False)
period_label = f3.selectbox("Survey Period", period_options["Survey_Period"].tolist())
selected_sort = period_options.loc[period_options["Survey_Period"] == period_label, "Period_Sort"].iloc[0]

with f0:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='pill'>{survey_type}</span><span class='pill'>{survey_id}</span><span class='pill'>{period_label.replace('FY ', '')}</span>",
        unsafe_allow_html=True,
    )
with f4:
    st.markdown("<br>", unsafe_allow_html=True)
    export_df = survey_df.copy()
    st.download_button("⬇ Export Report", data=export_df.to_csv(index=False).encode("utf-8"), file_name=f"{survey_id}_survey_data.csv", mime="text/csv", use_container_width=True)

latest_label, latest_sort = latest_period(survey_df)
previous = previous_period(survey_df, selected_sort)
current_row = survey_period_score(survey_df, selected_sort)
previous_row = survey_period_score(survey_df, previous[1]) if previous else None
current_period_df = survey_df[survey_df["Period_Sort"] == selected_sort].copy()
current_period_df["Display_Score"] = current_period_df.apply(lambda r: normalize_score(r["Score"], r["Score_Type"], r["Display_As"]), axis=1)

survey_name = survey_df["Survey_Name"].dropna().iloc[0] if not survey_df.empty else "Survey"
score_type = current_row.get("Score_Type", "Index") if current_row is not None else "Index"
display_as = current_row.get("Display_As", "Percentage") if current_row is not None else "Percentage"
better_direction = current_row.get("Better_Direction", "Higher") if current_row is not None else "Higher"
cur_score_display = format_score(current_row.get("Score"), score_type, display_as) if current_row is not None else "-"
delta = metric_delta(current_row, previous_row)
prev_text = f" vs {previous[0]}" if previous else ""
delta_sub = "percentage points" if str(display_as).lower().startswith("percent") else "change"

strongest_df = sort_for_performance(current_period_df, ascending_best=False).head(1)
weakest_df = sort_for_performance(current_period_df, ascending_best=True).head(1)
strong_name = strongest_df["Construct"].iloc[0] if not strongest_df.empty else "-"
weak_name = weakest_df["Construct"].iloc[0] if not weakest_df.empty else "-"
strong_score = format_score(strongest_df["Score"].iloc[0], strongest_df["Score_Type"].iloc[0], strongest_df["Display_As"].iloc[0]) if not strongest_df.empty else "-"
weak_score = format_score(weakest_df["Score"].iloc[0], weakest_df["Score_Type"].iloc[0], weakest_df["Display_As"].iloc[0]) if not weakest_df.empty else "-"

# KPI cards.
if page != "☁ Upload Data" and page != "ℹ About":
    k1, k2, k3, k4 = st.columns([1, 1, 1, 1])
    with k1:
        st.markdown(kpi_card("Overall Index Score", cur_score_display, f"{score_type} (0–100)" if str(display_as).lower().startswith("percent") else score_type, "⌁"), unsafe_allow_html=True)
    with k2:
        dval = "-" if delta is None else f"{delta:+.1f}"
        st.markdown(kpi_card(f"Change vs Previous{prev_text}", dval, delta_sub, "▥", delta=delta), unsafe_allow_html=True)
    with k3:
        st.markdown(kpi_card("Highest Construct", short_text(strong_name, 36), strong_score, "🏆", small_value=True), unsafe_allow_html=True)
    with k4:
        st.markdown(kpi_card("Lowest Construct", short_text(weak_name, 36), weak_score, "◎", small_value=True), unsafe_allow_html=True)

page_key = page.split(" ", 1)[-1]

if page_key == "Executive Summary":
    left, right = st.columns([1.15, 1.05])
    with left:
        st.markdown(f"<div class='section-card'><div class='section-title'>Latest Construct Performance ({period_label})</div>", unsafe_allow_html=True)
        st.plotly_chart(construct_bar_chart(current_period_df, period_label, display_as), use_container_width=True, config={"displayModeBar": False}, key=f"exec_construct_{survey_id}_{period_label}")
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown(f"<div class='section-card'><div class='section-title'>Strongest and Weakest Areas ({period_label})</div>", unsafe_allow_html=True)
        t1, t2 = st.columns(2)
        top = sort_for_performance(current_period_df, ascending_best=False).head(5).copy()
        bottom = sort_for_performance(current_period_df, ascending_best=True).head(5).copy()
        top["#"] = range(1, len(top) + 1)
        bottom["#"] = range(1, len(bottom) + 1)
        top["Score"] = top.apply(lambda r: format_score(r["Score"], r["Score_Type"], r["Display_As"]), axis=1)
        bottom["Score"] = bottom.apply(lambda r: format_score(r["Score"], r["Score_Type"], r["Display_As"]), axis=1)
        with t1:
            st.markdown("<div class='green-head'>Top 5 Strongest Areas</div>", unsafe_allow_html=True)
            display_table(top[["#", "Construct", "Score"]], height=310)
        with t2:
            st.markdown("<div class='red-head'>Top 5 Areas Needing Attention</div>", unsafe_allow_html=True)
            display_table(bottom[["#", "Construct", "Score"]], height=310)
        st.markdown("</div>", unsafe_allow_html=True)

    b1, b2, b3 = st.columns([1, 1.15, 1.15])
    with b1:
        st.markdown(f"<div class='section-card'><div class='section-title'>Score Distribution ({period_label})</div>", unsafe_allow_html=True)
        st.plotly_chart(distribution_donut(current_period_df), use_container_width=True, config={"displayModeBar": False}, key=f"exec_dist_{survey_id}_{period_label}")
        st.markdown("</div>", unsafe_allow_html=True)
    with b2:
        st.markdown("<div class='section-card'><div class='section-title'>Overall Index Trend</div>", unsafe_allow_html=True)
        tdf = trend_data(survey_df)
        if not tdf.empty and tdf["Survey_Period"].nunique() > 1:
            st.plotly_chart(trend_bar_chart(tdf, period_label), use_container_width=True, config={"displayModeBar": False}, key=f"exec_trend_{survey_id}_{period_label}")
        else:
            st.info("Only one period is available. Trend is not forced.")
        st.markdown("</div>", unsafe_allow_html=True)
    with b3:
        st.markdown("<div class='section-card'><div class='section-title'>Survey Information</div>", unsafe_allow_html=True)
        freq = ""
        if not survey_master.empty and "Survey_ID" in survey_master.columns:
            row = survey_master[survey_master["Survey_ID"] == survey_id]
            if not row.empty:
                freq = row.iloc[0].get("Frequency", "")
        st.markdown(
            f"""
            <div class='info-list'>
            <b>Survey Type</b>: <span>{survey_type}</span><br>
            <b>Survey ID</b>: <span>{survey_id}</span><br>
            <b>Survey</b>: <span>{survey_name}</span><br>
            <b>Frequency</b>: <span>{freq if pd.notna(freq) else ''}</span><br>
            <b>Score Type</b>: <span>{score_type}</span><br>
            <b>Better Direction</b>: <span>{better_direction}</span><br>
            <b>Available Periods</b>: <span>{survey_df['Survey_Period'].nunique()}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

elif page_key == "Construct Performance":
    st.markdown(f"<div class='section-card'><div class='section-title'>Construct Ranking ({period_label})</div>", unsafe_allow_html=True)
    sort_order = st.radio("Sort order", ["Strongest first", "Weakest first", "Original order"], horizontal=True)
    if sort_order == "Strongest first":
        plot_df = sort_for_performance(current_period_df, ascending_best=False)
    elif sort_order == "Weakest first":
        plot_df = sort_for_performance(current_period_df, ascending_best=True)
    else:
        plot_df = current_period_df.sort_values("Construct_Order")
    st.plotly_chart(construct_bar_chart(plot_df, period_label, display_as), use_container_width=True, config={"displayModeBar": False}, key=f"construct_perf_{survey_id}_{period_label}")
    st.markdown("</div>", unsafe_allow_html=True)
    table = current_period_df.sort_values("Construct_Order").copy()
    table["Score"] = table.apply(lambda r: format_score(r["Score"], r["Score_Type"], r["Display_As"]), axis=1)
    st.dataframe(table[["Construct", "Score", "Score_Type", "Display_As", "Better_Direction", "Notes"]], use_container_width=True, hide_index=True)
    dataframe_download(table, "Download construct table", f"{survey_id}_{period_label}_constructs.csv")

elif page_key == "Time Trend":
    tdf = trend_data(survey_df)
    st.markdown("<div class='section-card'><div class='section-title'>Overall Trend</div>", unsafe_allow_html=True)
    if tdf.empty or tdf["Survey_Period"].nunique() < 2:
        st.info("This survey has only one available period. No trend is forced.")
    else:
        st.plotly_chart(trend_bar_chart(tdf, period_label), use_container_width=True, config={"displayModeBar": False}, key=f"trend_overall_{survey_id}_{period_label}")
    st.markdown("</div>", unsafe_allow_html=True)
    constructs = survey_df["Construct"].dropna().drop_duplicates().tolist()
    selected_construct = st.selectbox("Select construct for trend", constructs)
    cdf = survey_df[survey_df["Construct"] == selected_construct].dropna(subset=["Period_Sort"]).sort_values("Period_Sort").copy()
    cdf["Display_Score"] = cdf.apply(lambda r: normalize_score(r["Score"], r["Score_Type"], r["Display_As"]), axis=1)
    st.markdown(f"<div class='section-card'><div class='section-title'>Construct Trend: {selected_construct}</div>", unsafe_allow_html=True)
    if cdf["Survey_Period"].nunique() < 2:
        st.info("This construct has only one available period.")
    else:
        st.plotly_chart(trend_bar_chart(cdf, period_label), use_container_width=True, config={"displayModeBar": False}, key=f"trend_construct_{survey_id}_{selected_construct}_{period_label}")
    st.markdown("</div>", unsafe_allow_html=True)

elif page_key == "Segment Analysis":
    seg = segment_data[(segment_data.get("Survey_ID", "") == survey_id) & (segment_data.get("Period_Sort", pd.Series(dtype=float)) == selected_sort)].copy() if not segment_data.empty else pd.DataFrame()
    if seg.empty:
        st.info("No segment data is available for the selected survey period.")
    else:
        c1, c2 = st.columns([1, 1])
        seg_type = c1.selectbox("Segment type", sorted(seg["Segment_Type"].dropna().unique().tolist()))
        metric = c2.selectbox("Metric", sorted(seg.loc[seg["Segment_Type"] == seg_type, "Metric"].dropna().unique().tolist()))
        sdf = seg[(seg["Segment_Type"] == seg_type) & (seg["Metric"] == metric)].copy().sort_values("Display_Value", ascending=True)
        sdf["Score"] = sdf.apply(lambda r: format_score(r.get("Value"), r.get("Score_Type"), r.get("Display_As")), axis=1)

        # Keep the original table columns intact. Create a separate chart dataframe
        # because construct_bar_chart expects Construct/Wrapped_Construct/Display_Score.
        chart_df = sdf.copy()
        chart_df["Construct"] = chart_df["Segment_Name"]
        chart_df["Wrapped_Construct"] = chart_df["Segment_Name"].apply(lambda x: wrap_label(x, 28))
        chart_df["Display_Score"] = chart_df["Display_Value"]

        st.markdown(f"<div class='section-card'><div class='section-title'>{seg_type}: {metric}</div>", unsafe_allow_html=True)
        st.plotly_chart(
            construct_bar_chart(chart_df, period_label, chart_df["Display_As"].iloc[0] if not chart_df.empty else "Number"),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"segment_chart_{survey_id}_{seg_type}_{metric}_{period_label}"
        )
        table_cols = [c for c in ["Segment_Name", "Metric", "Score", "Score_Type", "Notes"] if c in sdf.columns]
        st.dataframe(sdf[table_cols], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

elif page_key == "Survey Details":
    st.markdown("<div class='section-card'><div class='section-title'>Survey Master</div>", unsafe_allow_html=True)
    if not survey_master.empty:
        st.dataframe(survey_master[survey_master["Survey_ID"] == survey_id], use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-card'><div class='section-title'>Construct Master</div>", unsafe_allow_html=True)
    if not construct_master.empty:
        st.dataframe(construct_master[construct_master["Survey_ID"] == survey_id].sort_values("Construct_Order"), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif page_key == "Upload Data":
    st.markdown("<div class='section-card'><div class='section-title'>Mapped Workbook Input Rules</div>", unsafe_allow_html=True)
    st.write("Update the workbook by appending rows to Corporate_Data, Departmental_Data or Segment_Data. Do not change sheet names or column names.")
    st.write("The app automatically separates corporate and departmental surveys, detects latest periods, handles irregular time trends and applies score formatting rules.")
    with open(DEFAULT_WORKBOOK, "rb") as f:
        st.download_button("Download mapped entry workbook", data=f, file_name="survey_indices_entry_sheet_mapped.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-card'><div class='section-title'>Score Type Rules</div>", unsafe_allow_html=True)
    if not score_rules.empty:
        st.dataframe(score_rules, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

elif page_key == "About":
    st.markdown("<div class='section-card'><div class='section-title'>About this Dashboard</div>", unsafe_allow_html=True)
    st.write("This dashboard presents corporate and departmental survey indices using a clean mapped entry workbook. It is designed for executive review, construct performance analysis, trend review, and segment reporting.")
    st.write("Prepared for Tax Research & Analysis Department, Research & Surveys Section.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='footer'>Prepared and updated by&nbsp;&nbsp; <em>Cyrus Mutuku</em></div>", unsafe_allow_html=True)

from __future__ import annotations

import base64
import io
import textwrap
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

REQUIRED_DATA_COLUMNS = [
    "Survey_Type", "Survey_ID", "Survey_Name", "Survey_Period", "Period_Sort",
    "Construct", "Construct_Order", "Score", "Score_Type", "Display_As", "Scale_Min",
    "Scale_Max", "Better_Direction", "Is_Overall", "Segment_Type", "Segment_Name", "Notes"
]

KRA_RED = "#e30613"
KRA_DARK_RED = "#9b0008"
KRA_BLACK = "#050505"
KRA_GREEN = "#00843d"
KRA_AMBER = "#ffcc00"
KRA_ORANGE = "#ff7a00"


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().replace(" ", "_") for c in out.columns]
    return out


def strip_text(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.select_dtypes(include="object").columns:
        out[c] = out[c].astype(str).str.strip().replace({"nan": np.nan, "None": np.nan, "": np.nan})
    return out


def normalize_score(score, score_type: str = "Index", display_as: str = "Percentage") -> float:
    if pd.isna(score):
        return np.nan
    s = float(score)
    display = str(display_as or "").lower()
    stype = str(score_type or "").lower()
    if "percent" in display:
        if stype == "index" and s <= 1.5:
            return s * 100
        if s <= 1.5:
            return s * 100
        return s
    return s


def format_score(score, score_type: str = "Index", display_as: str = "Percentage") -> str:
    val = normalize_score(score, score_type, display_as)
    if pd.isna(val):
        return "-"
    display = str(display_as or "").lower()
    if "percent" in display:
        return f"{val:.1f}%"
    if abs(val) >= 1000:
        return f"{val:,.0f}"
    return f"{val:.1f}"


def short_text(value: str, limit: int = 34) -> str:
    value = "" if pd.isna(value) else str(value)
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 3)].rstrip() + "..."


def wrap_label(value: str, width: int = 30) -> str:
    if pd.isna(value):
        return ""
    return "<br>".join(textwrap.wrap(str(value), width=width, break_long_words=False))


def display_series(df: pd.DataFrame, value_col: str = "Score") -> pd.Series:
    return df.apply(lambda r: normalize_score(r.get(value_col), r.get("Score_Type"), r.get("Display_As")), axis=1)


def load_workbook(uploaded_file=None, default_path: str = "survey_indices_entry_sheet_mapped.xlsx") -> dict:
    source = uploaded_file if uploaded_file is not None else default_path
    sheets = pd.read_excel(source, sheet_name=None)
    out = {k: strip_text(clean_columns(v)) for k, v in sheets.items()}
    for key in ["Corporate_Data", "Departmental_Data", "Segment_Data"]:
        if key in out:
            for c in ["Period_Sort", "Score", "Scale_Min", "Scale_Max", "Value", "Construct_Order"]:
                if c in out[key].columns:
                    out[key][c] = pd.to_numeric(out[key][c], errors="coerce")
    return out


def build_data(sheets: dict) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    survey_master = sheets.get("Survey_Master", pd.DataFrame()).copy()
    construct_master = sheets.get("Construct_Master", pd.DataFrame()).copy()
    rules = sheets.get("Score_Type_Rules", pd.DataFrame()).copy()
    corp = sheets.get("Corporate_Data", pd.DataFrame(columns=REQUIRED_DATA_COLUMNS)).copy()
    dept = sheets.get("Departmental_Data", pd.DataFrame(columns=REQUIRED_DATA_COLUMNS)).copy()
    seg = sheets.get("Segment_Data", pd.DataFrame()).copy()
    data = pd.concat([corp, dept], ignore_index=True)
    if not data.empty:
        for col in REQUIRED_DATA_COLUMNS:
            if col not in data.columns:
                data[col] = np.nan
        data = data.dropna(subset=["Survey_ID", "Survey_Period", "Construct", "Score"], how="any")
        data["Display_Score"] = display_series(data)
        data["Wrapped_Construct"] = data["Construct"].apply(lambda x: wrap_label(x, 34))
        data["Survey_Label"] = data["Survey_ID"].astype(str) + " - " + data["Survey_Name"].astype(str)
    if not seg.empty:
        for c in ["Value", "Period_Sort"]:
            if c in seg.columns:
                seg[c] = pd.to_numeric(seg[c], errors="coerce")
        if "Value" in seg.columns:
            seg = seg.dropna(subset=["Survey_ID", "Survey_Period", "Segment_Name", "Metric", "Value"], how="any")
            seg["Display_Value"] = seg.apply(lambda r: normalize_score(r.get("Value"), r.get("Score_Type"), r.get("Display_As")), axis=1)
    return survey_master, construct_master, data, seg, rules


def latest_period(df: pd.DataFrame) -> tuple:
    d = df.dropna(subset=["Period_Sort"])
    if d.empty:
        p = df["Survey_Period"].dropna().iloc[-1]
        return p, np.nan
    row = d.sort_values("Period_Sort").iloc[-1]
    return row["Survey_Period"], row["Period_Sort"]


def previous_period(df: pd.DataFrame, period_sort) -> Optional[tuple]:
    if pd.isna(period_sort):
        return None
    d = df.dropna(subset=["Period_Sort"]).drop_duplicates(["Survey_Period", "Period_Sort"])
    d = d[d["Period_Sort"] < period_sort].sort_values("Period_Sort")
    if d.empty:
        return None
    row = d.iloc[-1]
    return row["Survey_Period"], row["Period_Sort"]


def overall_rows(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "Is_Overall" in d.columns and d["Is_Overall"].astype(str).str.lower().eq("yes").any():
        return d[d["Is_Overall"].astype(str).str.lower().eq("yes")]
    pattern = d["Construct"].astype(str).str.lower().str.contains("overall|index|satisfaction|score", regex=True)
    if pattern.any():
        return d[pattern]
    return d.sort_values("Construct_Order").head(1)


def survey_period_score(df: pd.DataFrame, period_sort) -> Optional[pd.Series]:
    d = df[df["Period_Sort"] == period_sort]
    if d.empty:
        return None
    o = overall_rows(d)
    if o.empty:
        return None
    return o.sort_values("Construct_Order").iloc[0]


def trend_data(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ps, group in df.groupby("Period_Sort"):
        row = survey_period_score(group, ps)
        if row is not None:
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("Period_Sort")
    out["Display_Score"] = display_series(out)
    return out


def metric_delta(current_row, previous_row) -> Optional[float]:
    if current_row is None or previous_row is None:
        return None
    cur = normalize_score(current_row.get("Score"), current_row.get("Score_Type"), current_row.get("Display_As"))
    prev = normalize_score(previous_row.get("Score"), previous_row.get("Score_Type"), previous_row.get("Display_As"))
    if pd.isna(cur) or pd.isna(prev):
        return None
    return cur - prev


def lower_is_better(series_or_value) -> bool:
    if isinstance(series_or_value, pd.Series):
        return str(series_or_value.get("Better_Direction", "Higher")).lower().startswith("lower")
    return str(series_or_value or "Higher").lower().startswith("lower")


def sort_for_performance(df: pd.DataFrame, score_col: str = "Display_Score", ascending_best: bool = False) -> pd.DataFrame:
    d = df.copy()
    lower = d.get("Better_Direction", pd.Series("Higher", index=d.index)).astype(str).str.lower().str.startswith("lower")
    if lower.any() and lower.all():
        return d.sort_values(score_col, ascending=not ascending_best)
    return d.sort_values(score_col, ascending=ascending_best)


def band_color(score: float, better_direction: str = "Higher") -> str:
    if pd.isna(score):
        return "#94a3b8"
    if str(better_direction).lower().startswith("lower"):
        if score <= 2: return KRA_GREEN
        if score <= 3: return "#6cc24a"
        if score <= 4: return KRA_AMBER
        return KRA_RED
    if score >= 80: return KRA_GREEN
    if score >= 70: return "#6cc24a"
    if score >= 60: return KRA_AMBER
    if score >= 50: return KRA_ORANGE
    return KRA_RED


def band_label(score: float, better_direction: str = "Higher") -> str:
    if pd.isna(score):
        return "Not available"
    if str(better_direction).lower().startswith("lower"):
        if score <= 2: return "Excellent"
        if score <= 3: return "Good"
        if score <= 4: return "Average"
        return "Needs attention"
    if score >= 80: return "Excellent"
    if score >= 70: return "Good"
    if score >= 60: return "Average"
    if score >= 50: return "Needs improvement"
    return "Poor"


def color_scale_for_scores(scores, better_direction="Higher"):
    return [band_color(v, better_direction) for v in scores]


def get_logo_base64(path: str = "assets/kra_logo.png") -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return base64.b64encode(p.read_bytes()).decode("utf-8")


def kra_header(logo_path: str = "assets/kra_logo.png") -> str:
    encoded = get_logo_base64(logo_path)
    if encoded:
        logo = f'<img src="data:image/png;base64,{encoded}" class="kra-logo" />'
    else:
        logo = '<div class="kra-word-logo"><b>KRA</b><span>Kenya Revenue Authority</span></div>'
    return f"""
    <div class="kra-topbar">
        <div class="kra-brand">{logo}</div>
        <div class="kra-title">
            <div class="main-title">Tax Research &amp; Analysis Department</div>
            <div class="title-line"><span></span><b>Research &amp; Surveys Section</b><span></span></div>
        </div>
        <div class="date-box"><span>Data as at:</span><b>23 May 2025</b></div>
    </div>
    """


def inject_css() -> str:
    return """
    <style>
    :root{--red:#e30613;--darkred:#9b0008;--black:#050505;--muted:#6b7280;--border:#e5e7eb;--soft:#f8fafc;}
    html, body, [class*="css"]{font-family: Inter, Segoe UI, Arial, sans-serif;}
    .block-container{padding-top:1.25rem;padding-bottom:.7rem;max-width:1540px;}
    header[data-testid="stHeader"]{background:transparent;height:0rem;}
    div[data-testid="stToolbar"]{display:none;}
    .kra-topbar{min-height:112px;display:flex;align-items:center;justify-content:space-between;background:#fff;margin:0 -14px 16px -14px;padding:14px 24px 14px 24px;border-bottom:3px solid var(--red);box-shadow:0 8px 20px rgba(0,0,0,.07);position:relative;overflow:hidden;box-sizing:border-box;}
    .kra-topbar:after{content:"";position:absolute;right:-18px;top:0;width:300px;height:112px;background:linear-gradient(145deg,transparent 0 42%,var(--red) 43% 68%,#fff 69% 74%,var(--black) 75% 80%,transparent 81%);}
    .kra-brand{width:250px;z-index:2;display:flex;align-items:center;}
    .kra-logo{max-width:230px;max-height:78px;object-fit:contain;}
    .kra-word-logo{border-left:8px solid var(--red);padding-left:12px;text-transform:uppercase;line-height:1.0;}
    .kra-word-logo b{display:block;font-size:36px;color:var(--black);letter-spacing:1px;}.kra-word-logo span{display:block;font-size:13px;color:var(--red);font-weight:800;}
    .kra-title{z-index:2;text-align:center;flex:1;}
    .main-title{text-transform:uppercase;font-size:32px;font-weight:950;color:var(--black);letter-spacing:.5px;white-space:nowrap;line-height:1.05;}
    .title-line{display:flex;align-items:center;gap:14px;justify-content:center;margin-top:10px;}.title-line span{height:3px;width:170px;background:var(--red);display:inline-block;position:relative;}.title-line span:after{content:"";width:9px;height:9px;background:var(--red);border-radius:50%;position:absolute;right:-2px;top:-3px;}.title-line b{text-transform:uppercase;color:var(--red);font-size:22px;font-weight:950;letter-spacing:.5px;line-height:1.05;}
    .date-box{z-index:2;width:220px;text-align:right;padding-right:10px;color:var(--black);font-size:12px;line-height:1.2;margin-top:4px;}.date-box:before{content:"📅";font-size:24px;margin-right:6px;vertical-align:middle;}.date-box span{font-weight:800;display:inline-block;}.date-box b{display:block;font-size:12px;}
    section[data-testid="stSidebar"]{background:linear-gradient(180deg,#030303 0%,#090909 72%,#260004 100%);border-right:2px solid #111;}
    section[data-testid="stSidebar"] *{color:#fff!important;}
    section[data-testid="stSidebar"] .stRadio label{padding:.55rem .25rem;border-bottom:1px solid rgba(255,255,255,.10);}
    .pill{display:inline-block;background:#fee2e2;color:#991b1b;border-radius:24px;padding:10px 18px;font-weight:900;margin-right:8px;font-size:15px;}
    .kpi-card{background:#fff;border:1px solid var(--border);border-radius:14px;border-top:6px solid var(--red);box-shadow:0 8px 22px rgba(15,23,42,.06);padding:14px 16px;min-height:130px;display:flex;gap:16px;align-items:center;overflow:hidden;}
    .kpi-icon{width:76px;height:76px;border-radius:8px;background:linear-gradient(135deg,var(--red),#b0000a);color:#fff;font-size:37px;display:flex;align-items:center;justify-content:center;flex:0 0 76px;box-shadow:inset -16px -16px 28px rgba(0,0,0,.14);}
    .kpi-label{font-size:13px;color:#111827;font-weight:800;line-height:1.15;margin-bottom:5px;}
    .kpi-value{font-size:36px;line-height:1.0;color:#050505;font-weight:950;letter-spacing:-1px;white-space:normal;word-break:normal;}
    .kpi-value.small{font-size:18px;line-height:1.18;letter-spacing:0;word-break:normal;}
    .kpi-sub{font-size:13px;color:#6b7280;margin-top:8px;line-height:1.15;}
    .delta-up{color:#07883e;font-weight:800}.delta-down{color:#e30613;font-weight:800}.delta-flat{color:#6b7280;font-weight:800}
    .section-card{background:#fff;border:1px solid var(--border);border-radius:16px;box-shadow:0 8px 22px rgba(15,23,42,.055);padding:16px;margin-bottom:12px;min-height:80px;}
    .section-title{font-size:19px;font-weight:950;color:#111827;border-left:8px solid var(--red);padding-left:11px;margin-bottom:12px;line-height:1.1;}
    .green-head{background:linear-gradient(90deg,#00843d,#00a651);color:#fff;font-weight:900;padding:10px;border-radius:9px 9px 0 0;text-align:center;}.red-head{background:linear-gradient(90deg,#c40010,#e30613);color:#fff;font-weight:900;padding:10px;border-radius:9px 9px 0 0;text-align:center;}
    div[data-testid="stDataFrame"]{border-radius:0 0 10px 10px;overflow:hidden;}
    .footer{border-top:2px solid var(--red);text-align:center;font-size:12px;margin-top:8px;padding:9px 0 0 0;color:#111827;}.footer em{font-weight:900;color:#050505;}
    .info-list{font-size:14px;line-height:1.8;}.info-list b{display:inline-block;width:155px;color:#111827;}.info-list span{color:#111827;}
    @media(max-width:1050px){.kra-topbar{height:auto;min-height:145px;flex-direction:column;gap:4px}.kra-brand,.date-box{width:100%;text-align:center}.main-title{font-size:24px;white-space:normal}.title-line b{font-size:18px}.title-line span{width:60px}.kpi-value{font-size:30px}.kpi-value.small{font-size:18px}}
    </style>
    """


def kpi_card(label: str, value: str, sub: str = "", icon: str = "●", small_value: bool = False, delta: Optional[float] = None) -> str:
    vclass = "kpi-value small" if small_value else "kpi-value"
    sub_html = sub or ""
    if delta is not None and not pd.isna(delta):
        dclass = "delta-up" if delta > 0 else "delta-down" if delta < 0 else "delta-flat"
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        sub_html = f'<span class="{dclass}">{arrow} {abs(delta):.1f}</span> {sub}'
    return f"""
    <div class="kpi-card">
        <div class="kpi-icon">{icon}</div>
        <div>
            <div class="kpi-label">{label}</div>
            <div class="{vclass}">{value}</div>
            <div class="kpi-sub">{sub_html}</div>
        </div>
    </div>
    """


def construct_bar_chart(df: pd.DataFrame, period_label: str, display_as="Percentage") -> go.Figure:
    d = df.copy().dropna(subset=["Display_Score"])
    d = d.sort_values("Display_Score", ascending=True)
    d["Short_Label"] = d["Construct"].apply(lambda x: wrap_label(x, 31))
    colors = color_scale_for_scores(d["Display_Score"], d.get("Better_Direction", pd.Series("Higher", index=d.index)).iloc[0] if not d.empty else "Higher")
    suffix = "%" if str(display_as).lower().startswith("percent") else ""
    fig = go.Figure(go.Bar(
        x=d["Display_Score"], y=d["Short_Label"], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v:.1f}{suffix}" for v in d["Display_Score"]], textposition="outside",
        hovertext=d["Construct"], hoverinfo="text+x",
    ))
    xmax = 100 if str(display_as).lower().startswith("percent") else max(5, float(d["Display_Score"].max()) * 1.25 if not d.empty else 5)
    fig.update_layout(
        height=max(330, 32 * len(d) + 80), margin=dict(l=8, r=70, t=10, b=34),
        plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#050505"),
        xaxis=dict(range=[0, xmax], title="Score (%)" if suffix else "Score", showgrid=True, gridcolor="#edf2f7", zeroline=False),
        yaxis=dict(title="", automargin=True), bargap=.35,
    )
    return fig


def trend_bar_chart(df: pd.DataFrame, latest_period: str = "") -> go.Figure:
    d = df.copy().dropna(subset=["Display_Score"]).sort_values("Period_Sort")
    colors = [KRA_RED if str(p) == str(latest_period) else "#333333" for p in d["Survey_Period"]]
    fig = go.Figure(go.Bar(
        x=d["Survey_Period"], y=d["Display_Score"], marker_color=colors,
        text=[f"{v:.1f}%" for v in d["Display_Score"]], textposition="outside"
    ))
    fig.update_layout(height=245, margin=dict(l=30, r=18, t=15, b=36), plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#111827"), yaxis=dict(title="Score (%)", range=[0, max(100, d["Display_Score"].max()*1.15 if not d.empty else 100)], gridcolor="#edf2f7"), xaxis=dict(title=""))
    return fig


def distribution_donut(df: pd.DataFrame) -> go.Figure:
    d = df.copy().dropna(subset=["Display_Score"])
    labels = ["Excellent (80-100)", "Good (70-79)", "Average (60-69)", "Needs Improvement (50-59)", "Poor (0-49)"]
    bins = [
        (d["Display_Score"] >= 80).sum(),
        ((d["Display_Score"] >= 70) & (d["Display_Score"] < 80)).sum(),
        ((d["Display_Score"] >= 60) & (d["Display_Score"] < 70)).sum(),
        ((d["Display_Score"] >= 50) & (d["Display_Score"] < 60)).sum(),
        (d["Display_Score"] < 50).sum(),
    ]
    colors = [KRA_GREEN, "#6cc24a", KRA_AMBER, KRA_ORANGE, KRA_RED]
    fig = go.Figure(go.Pie(labels=labels, values=bins, hole=.58, marker=dict(colors=colors), textinfo="none"))
    fig.add_annotation(text=f"<b>{len(d)}</b><br>Constructs", showarrow=False, font=dict(size=15, color="#050505"))
    fig.update_layout(height=250, margin=dict(l=0, r=0, t=5, b=5), legend=dict(orientation="v", y=.5, x=.74, font=dict(size=11)), paper_bgcolor="white")
    return fig

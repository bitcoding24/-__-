import math
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="학습 공백 위험지수 대시보드",
    page_icon="📚",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main .block-container { padding-top: 2rem; padding-bottom: 4rem; }
    .metric-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }
    .calendar-grid {
        display: grid;
        grid-template-columns: repeat(7, minmax(0, 1fr));
        gap: 8px;
    }
    .calendar-head {
        text-align: center;
        font-weight: 700;
        color: #475569;
        font-size: 0.85rem;
        padding: 6px 0;
    }
    .calendar-day {
        min-height: 88px;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        padding: 8px;
        font-size: 0.78rem;
        overflow: hidden;
    }
    .study { background: #ecfdf5; border-color: #bbf7d0; }
    .rest { background: #fff1f2; border-color: #fecdd3; }
    .vacation { background: #f1f5f9; border-color: #cbd5e1; }
    .empty { background: #f8fafc; border-color: #f1f5f9; }
    .badge {
        display: inline-block;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 0.68rem;
        color: white;
        font-weight: 700;
    }
    .badge-study { background: #10b981; }
    .badge-rest { background: #f43f5e; }
    .badge-vacation { background: #64748b; }
    </style>
    """,
    unsafe_allow_html=True,
)


APP_DIR = Path(__file__).resolve().parent
DATA_CANDIDATES = [
    APP_DIR / "schedule_preprocessed_daily.csv.gz",
    APP_DIR / "data" / "schedule_preprocessed_daily.csv.gz",
    APP_DIR / "schedule_2025_04_preprocessed_daily.csv.gz",
]

REQUIRED_PREPROCESSED_COLUMNS = [
    "unit_id",
    "edu_code",
    "school_name",
    "school_year",
    "school_level",
    "date",
    "is_rest_event",
    "is_no_deduction",
    "is_vacation_day",
    "event_count",
    "event_names",
]

EDU_NAME_MAP = {
    "B10": "서울특별시교육청",
    "C10": "부산광역시교육청",
    "D10": "대구광역시교육청",
    "E10": "인천광역시교육청",
    "F10": "광주광역시교육청",
    "G10": "대전광역시교육청",
    "H10": "울산광역시교육청",
    "I10": "세종특별자치시교육청",
    "J10": "경기도교육청",
    "K10": "강원특별자치도교육청",
    "M10": "충청북도교육청",
    "N10": "충청남도교육청",
    "P10": "전북특별자치도교육청",
    "Q10": "전라남도교육청",
    "R10": "경상북도교육청",
    "S10": "경상남도교육청",
    "T10": "제주특별자치도교육청",
}


def find_packaged_data() -> Path | None:
    for path in DATA_CANDIDATES:
        if path.exists():
            return path
    return None


def read_preprocessed_csv(source, source_name: str) -> pd.DataFrame:
    compression = "gzip" if source_name.endswith(".gz") else None
    dtype = {
        "unit_id": "int32",
        "edu_code": "string",
        "school_name": "string",
        "school_year": "string",
        "school_level": "string",
        "date": "string",
        "is_rest_event": "int8",
        "is_no_deduction": "int8",
        "is_vacation_day": "int8",
        "event_count": "int16",
        "event_names": "string",
    }
    return pd.read_csv(source, compression=compression, dtype=dtype, low_memory=False)


def normalize_preprocessed_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()

    missing = [col for col in REQUIRED_PREPROCESSED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"전처리 데이터에 필수 열이 없습니다: {missing}")

    for col in ["edu_code", "school_name", "school_year", "school_level", "date", "event_names"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    df["date"] = df["date"].str.replace(r"\D", "", regex=True)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    df["unit_id"] = pd.to_numeric(df["unit_id"], errors="coerce").astype("Int32")
    df = df.dropna(subset=["unit_id"]).copy()
    df["unit_id"] = df["unit_id"].astype("int32")

    for col in ["is_rest_event", "is_no_deduction", "is_vacation_day"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int8").astype(bool)

    df["event_count"] = pd.to_numeric(df["event_count"], errors="coerce").fillna(0).astype("int16")
    df["edu_name"] = df["edu_code"].map(EDU_NAME_MAP).fillna(df["edu_code"])
    df["school_display_name"] = df["school_name"] + " (" + df["school_level"] + ")"
    df["school_select_label"] = (
        df["school_display_name"] + " · " + df["edu_name"] + " · ID " + df["unit_id"].astype(str)
    )

    return df.sort_values(["unit_id", "date"]).reset_index(drop=True)


@st.cache_data(show_spinner=False, max_entries=2)
def load_preprocessed_from_path(path: str, mtime: float) -> pd.DataFrame:
    del mtime
    return normalize_preprocessed_data(read_preprocessed_csv(path, path))


@st.cache_data(show_spinner=False, max_entries=2)
def load_preprocessed_from_bytes(raw: bytes, name: str) -> pd.DataFrame:
    return normalize_preprocessed_data(read_preprocessed_csv(BytesIO(raw), name))


def to_excel_bytes(dfs: dict) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


def simulate_one_group(group: pd.DataFrame, M0: float, K1: float, C: float, D: float, R: float) -> pd.DataFrame:
    group = group.sort_values("date").copy()
    main_analysis = group["is_main_analysis_day"].to_numpy(dtype=bool)
    main_rest = group["is_main_rest_day"].to_numpy(dtype=bool)

    n = len(group)
    memory_scores = np.full(n, np.nan, dtype=float)
    risk_scores = np.full(n, np.nan, dtype=float)
    k_values = np.full(n, np.nan, dtype=float)
    p_values = np.full(n, np.nan, dtype=float)
    calculation_types: list[str] = []

    memory = M0
    p = 0

    for i in range(n):
        if not main_analysis[i]:
            calculation_types.append("방학 제외")
            memory = M0
            p = 0
            continue

        if main_rest[i]:
            p += 1
            k = K1 / ((1 + C * p) ** D)
            memory = memory * math.exp(-k)
            calculation_type = "휴업일_망각"
        else:
            memory = memory + R * (M0 - memory)
            p = 0
            k = 0.0
            calculation_type = "수업일_회복"

        memory = max(0.0, min(M0, memory))
        memory_scores[i] = memory
        risk_scores[i] = M0 - memory
        k_values[i] = k
        p_values[i] = p
        calculation_types.append(calculation_type)

    group["memory_score"] = memory_scores
    group["risk_score"] = risk_scores
    group["k_value"] = k_values
    group["p_value"] = p_values
    group["calculation_type"] = calculation_types

    return group


@st.cache_data(show_spinner=False, max_entries=2)
def build_calendar(daily_data: pd.DataFrame, start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    daily = daily_data[(daily_data["date"] >= start_dt) & (daily_data["date"] <= end_dt)].copy()
    if daily.empty:
        return pd.DataFrame(), pd.DataFrame()

    all_dates = pd.DataFrame({"date": pd.date_range(start_dt, end_dt, freq="D")})
    unit_cols = [
        "unit_id",
        "edu_code",
        "edu_name",
        "school_name",
        "school_year",
        "school_level",
        "school_display_name",
        "school_select_label",
    ]
    units = daily[unit_cols].drop_duplicates().copy()
    calendar = units.merge(all_dates, how="cross")

    merge_cols = [
        "unit_id",
        "date",
        "is_rest_event",
        "is_no_deduction",
        "is_vacation_day",
        "event_count",
        "event_names",
    ]
    calendar = calendar.merge(daily[merge_cols], on=["unit_id", "date"], how="left")

    for col in ["is_rest_event", "is_no_deduction", "is_vacation_day"]:
        calendar[col] = calendar[col].fillna(False).astype(bool)

    calendar["event_count"] = calendar["event_count"].fillna(0).astype("int16")
    calendar["event_names"] = calendar["event_names"].fillna("")
    calendar["weekday_no"] = calendar["date"].dt.weekday
    calendar["is_weekend"] = calendar["weekday_no"] >= 5

    calendar["is_term_rest_day"] = calendar["is_rest_event"] & ~calendar["is_vacation_day"]
    calendar["is_main_rest_day"] = (~calendar["is_vacation_day"]) & (
        calendar["is_weekend"] | calendar["is_term_rest_day"]
    )
    calendar["is_main_analysis_day"] = ~calendar["is_vacation_day"]
    calendar["is_study_day"] = calendar["is_main_analysis_day"] & ~calendar["is_main_rest_day"]

    vacation_check = (
        calendar.groupby(unit_cols)
        .agg(
            total_days=("date", "nunique"),
            vacation_days=("is_vacation_day", "sum"),
            analysis_days=("is_main_analysis_day", "sum"),
            rest_days=("is_main_rest_day", "sum"),
            study_days=("is_study_day", "sum"),
        )
        .reset_index()
    )
    vacation_check["inferred_vacation_days"] = 0

    return calendar, vacation_check


@st.cache_data(show_spinner=False, max_entries=2)
def simulate_memory(calendar: pd.DataFrame, M0: float, K1: float, C: float, D: float, R: float) -> pd.DataFrame:
    if calendar.empty:
        return calendar.copy()

    sorted_calendar = calendar.sort_values(["unit_id", "date"]).copy()
    unit_ids = sorted_calendar["unit_id"].to_numpy()
    main_analysis = sorted_calendar["is_main_analysis_day"].to_numpy(dtype=bool)
    main_rest = sorted_calendar["is_main_rest_day"].to_numpy(dtype=bool)

    n = len(sorted_calendar)
    memory_scores = np.full(n, np.nan, dtype=float)
    risk_scores = np.full(n, np.nan, dtype=float)
    k_values = np.full(n, np.nan, dtype=float)
    p_values = np.full(n, np.nan, dtype=float)
    calculation_types: list[str] = []

    current_unit = None
    memory = M0
    p = 0

    for i in range(n):
        if unit_ids[i] != current_unit:
            current_unit = unit_ids[i]
            memory = M0
            p = 0

        if not main_analysis[i]:
            calculation_types.append("방학 제외")
            memory = M0
            p = 0
            continue

        if main_rest[i]:
            p += 1
            k = K1 / ((1 + C * p) ** D)
            memory = memory * math.exp(-k)
            calculation_type = "휴업일_망각"
        else:
            memory = memory + R * (M0 - memory)
            p = 0
            k = 0.0
            calculation_type = "수업일_회복"

        memory = max(0.0, min(M0, memory))
        memory_scores[i] = memory
        risk_scores[i] = M0 - memory
        k_values[i] = k
        p_values[i] = p
        calculation_types.append(calculation_type)

    sorted_calendar["memory_score"] = memory_scores
    sorted_calendar["risk_score"] = risk_scores
    sorted_calendar["k_value"] = k_values
    sorted_calendar["p_value"] = p_values
    sorted_calendar["calculation_type"] = calculation_types
    return sorted_calendar.reset_index(drop=True)


@st.cache_data(show_spinner=False, max_entries=2)
def summarize_school(
    simulated: pd.DataFrame,
    vacation_check: pd.DataFrame,
    high_risk_threshold: float,
    min_vacation_days: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    group_cols = [
        "edu_code",
        "edu_name",
        "school_name",
        "school_year",
        "school_level",
        "unit_id",
        "school_display_name",
        "school_select_label",
    ]

    if simulated.empty:
        return pd.DataFrame(), pd.DataFrame()

    analysis_data = simulated[simulated["is_main_analysis_day"]].copy()
    school_summary = (
        analysis_data.groupby(group_cols)
        .agg(
            analysis_days=("date", "nunique"),
            rest_days=("is_main_rest_day", "sum"),
            study_days=("is_study_day", "sum"),
            avg_memory_score=("memory_score", "mean"),
            avg_risk_score=("risk_score", "mean"),
            max_risk_score=("risk_score", "max"),
            min_memory_score=("memory_score", "min"),
            high_risk_days=("risk_score", lambda x: (x >= high_risk_threshold).sum()),
        )
        .reset_index()
    )

    school_summary["rest_day_ratio"] = school_summary["rest_days"] / school_summary["analysis_days"] * 100
    school_summary["high_risk_day_ratio"] = (
        school_summary["high_risk_days"] / school_summary["analysis_days"] * 100
    )
    school_summary["final_risk_index"] = (
        0.7 * school_summary["avg_risk_score"] + 0.3 * school_summary["high_risk_day_ratio"]
    )

    def risk_grade(score: float) -> str:
        if score >= 80:
            return "매우 높음"
        if score >= 60:
            return "높음"
        if score >= 40:
            return "보통"
        if score >= 20:
            return "낮음"
        return "매우 낮음"

    school_summary["risk_grade"] = school_summary["final_risk_index"].apply(risk_grade)
    school_summary = school_summary.merge(
        vacation_check[["unit_id", "vacation_days", "inferred_vacation_days"]],
        on="unit_id",
        how="left",
    )
    school_summary["vacation_days"] = school_summary["vacation_days"].fillna(0).astype(int)
    school_summary["inferred_vacation_days"] = school_summary["inferred_vacation_days"].fillna(0).astype(int)

    core_summary = school_summary[school_summary["vacation_days"] >= min_vacation_days].copy()
    if not core_summary.empty:
        core_summary["risk_percentile"] = core_summary["final_risk_index"].rank(pct=True) * 100

        def relative_grade(pct: float) -> str:
            if pct >= 95:
                return "상위 5%"
            if pct >= 80:
                return "상위 20%"
            if pct >= 50:
                return "중간"
            if pct >= 20:
                return "하위 50%"
            return "하위 20%"

        core_summary["relative_risk_grade"] = core_summary["risk_percentile"].apply(relative_grade)
        core_summary = core_summary.sort_values("final_risk_index", ascending=False)
    else:
        core_summary["risk_percentile"] = pd.Series(dtype=float)
        core_summary["relative_risk_grade"] = pd.Series(dtype=str)

    return school_summary, core_summary


def make_memory_figure(one_school: pd.DataFrame, school_name: str) -> go.Figure:
    df = one_school.sort_values("date").copy()
    df["memory_plot"] = df["memory_score"].where(~df["is_vacation_day"], np.nan)
    df["risk_plot"] = df["risk_score"].where(~df["is_vacation_day"], np.nan)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["memory_plot"], mode="lines", name="기억점수", connectgaps=False))
    fig.add_trace(go.Scatter(x=df["date"], y=df["risk_plot"], mode="lines", name="위험점수", connectgaps=False))

    rest = df[df["is_main_rest_day"]]
    fig.add_trace(
        go.Scatter(
            x=rest["date"],
            y=rest["memory_score"],
            mode="markers",
            name="휴업일",
            marker=dict(size=5),
        )
    )

    fig.update_layout(
        title=f"{school_name} 날짜별 기억점수·위험점수 변화",
        xaxis_title="날짜",
        yaxis_title="점수",
        yaxis=dict(range=[0, 100]),
        height=430,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=70, b=20),
    )
    return fig


def make_calendar_html(one_school: pd.DataFrame, month: str) -> str:
    df = one_school.copy()
    df["date"] = pd.to_datetime(df["date"])
    month_dt = pd.to_datetime(month + "-01")
    year = month_dt.year
    mon = month_dt.month

    month_df = df[(df["date"].dt.year == year) & (df["date"].dt.month == mon)].copy()
    by_date = {d.strftime("%Y-%m-%d"): row for d, row in month_df.set_index("date").iterrows()}

    first = pd.Timestamp(year=year, month=mon, day=1)
    last_day = (first + pd.offsets.MonthEnd(0)).day
    start_weekday = (first.weekday() + 1) % 7
    weekdays = ["일", "월", "화", "수", "목", "금", "토"]

    cells = ""
    for weekday in weekdays:
        cells += f'<div class="calendar-head">{weekday}</div>'

    for _ in range(start_weekday):
        cells += '<div class="calendar-day empty"></div>'

    for day in range(1, last_day + 1):
        date_str = f"{year}-{mon:02d}-{day:02d}"
        row = by_date.get(date_str)
        if row is None:
            cells += f'<div class="calendar-day empty"><b>{day}</b></div>'
            continue

        if bool(row["is_vacation_day"]):
            cls = "vacation"
            badge = '<span class="badge badge-vacation">방학</span>'
            score = "계산 제외"
        elif bool(row["is_main_rest_day"]):
            cls = "rest"
            badge = '<span class="badge badge-rest">휴업</span>'
            score = f"기억 {row['memory_score']:.1f} · 위험 {row['risk_score']:.1f}"
        else:
            cls = "study"
            badge = '<span class="badge badge-study">수업</span>'
            score = f"기억 {row['memory_score']:.1f} · 위험 {row['risk_score']:.1f}"

        event = escape(str(row.get("event_names", "")))
        score_text = escape(score)

        cells += f"""
        <div class="calendar-day {cls}">
            <div class="day-top">
                <b>{day}</b>{badge}
            </div>
            <div class="score" title="{score_text}">{score_text}</div>
            <div class="event" title="{event}">{event or "-"}</div>
        </div>
        """

    return f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8" />
      <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #0f172a; }}
        .calendar-grid {{ display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 8px; }}
        .calendar-head {{ text-align: center; font-weight: 800; color: #475569; font-size: 14px; padding: 6px 0; }}
        .calendar-day {{ min-height: 92px; border-radius: 8px; border: 1px solid #e5e7eb; padding: 10px; font-size: 13px; overflow: hidden; }}
        .study {{ background: #ecfdf5; border-color: #bbf7d0; }}
        .rest {{ background: #fff1f2; border-color: #fecdd3; }}
        .vacation {{ background: #f1f5f9; border-color: #cbd5e1; }}
        .empty {{ background: #f8fafc; border-color: #f1f5f9; }}
        .day-top {{ display: flex; justify-content: space-between; gap: 6px; align-items: center; }}
        .badge {{ display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 11px; color: white; font-weight: 800; }}
        .badge-study {{ background: #10b981; }}
        .badge-rest {{ background: #f43f5e; }}
        .badge-vacation {{ background: #64748b; }}
        .score {{ margin-top: 7px; color: #475569; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .event {{ margin-top: 7px; color: #64748b; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.35; }}
      </style>
    </head>
    <body>
      <div class="calendar-grid">{cells}</div>
    </body>
    </html>
    """


DISPLAY_RENAME = {
    "edu_name": "시도교육청",
    "school_name": "학교명",
    "school_year": "학년도",
    "school_level": "학교과정",
    "analysis_days": "분석일수",
    "rest_days": "휴업일수",
    "study_days": "수업일수",
    "rest_day_ratio": "휴업일비율",
    "avg_risk_score": "평균위험점수",
    "high_risk_day_ratio": "고위험일비율",
    "final_risk_index": "최종위험지수",
    "risk_grade": "위험등급",
    "vacation_days": "방학일수",
    "relative_risk_grade": "상대위험등급",
}


st.title("📚 학사일정 기반 학습 공백 위험지수 대시보드")
st.caption("Colab에서 전처리한 경량 CSV.GZ를 읽어 학교별 위험지수를 계산합니다.")

with st.sidebar:
    st.header("1. 데이터")
    uploaded_file = st.file_uploader(
        "전처리된 CSV.GZ 파일을 업로드하세요.",
        type=["gz", "csv"],
        accept_multiple_files=False,
    )

packaged_data = find_packaged_data()
try:
    if uploaded_file is not None:
        daily_data = load_preprocessed_from_bytes(uploaded_file.getvalue(), uploaded_file.name)
        source_label = uploaded_file.name
    elif packaged_data is not None:
        daily_data = load_preprocessed_from_path(str(packaged_data), packaged_data.stat().st_mtime)
        source_label = packaged_data.name
    else:
        st.info("전처리된 `schedule_preprocessed_daily.csv.gz` 파일을 앱 폴더에 두거나 왼쪽에서 업로드하세요.")
        st.stop()
except Exception as exc:
    st.error(f"전처리 데이터를 읽지 못했습니다: {exc}")
    st.stop()

data_min_date = daily_data["date"].min().date()
data_max_date = daily_data["date"].max().date()
date_span_days = (data_max_date - data_min_date).days + 1

with st.sidebar:
    st.caption(f"데이터: {source_label}")
    st.caption(f"{len(daily_data):,}행 · {daily_data['unit_id'].nunique():,}개 학교-과정")
    st.caption(f"{data_min_date} ~ {data_max_date}")

    st.header("2. 분석 기간")
    start_date = st.date_input("시작일", value=data_min_date, min_value=data_min_date, max_value=data_max_date)
    end_date = st.date_input("종료일", value=data_max_date, min_value=data_min_date, max_value=data_max_date)

    st.header("3. 모델 파라미터")
    M0 = st.number_input("최대 기억점수 M0", value=100.0, min_value=1.0, step=1.0)
    K1 = st.number_input("초기 망각 속도 K1", value=0.35, min_value=0.0, step=0.01)
    C = st.number_input("k 감소 상수 C", value=0.5, min_value=0.0, step=0.1)
    D = st.number_input("k 감소 형태 D", value=1.0, min_value=0.1, step=0.1)
    R = st.number_input("수업일 회복률 R", value=0.30, min_value=0.0, max_value=1.0, step=0.05)
    high_risk_threshold = st.number_input("고위험 기준 점수", value=60.0, min_value=0.0, max_value=100.0, step=5.0)
    default_min_vacation_days = 10 if date_span_days >= 180 else 0
    min_vacation_days = st.number_input(
        "핵심 분석 포함 최소 방학일수",
        value=default_min_vacation_days,
        min_value=0,
        step=1,
    )

    run_btn = st.button("🚀 분석 실행", type="primary", use_container_width=True)

if start_date > end_date:
    st.error("시작일은 종료일보다 늦을 수 없습니다.")
    st.stop()

if run_btn:
    for key in ["calendar", "vacation_check", "simulated", "school_summary", "core_summary"]:
        if key in st.session_state:
            del st.session_state[key]

    with st.spinner("1년 전체 날짜표를 만드는 중..."):
        calendar, vacation_check = build_calendar(daily_data, str(start_date), str(end_date))
    if calendar.empty:
        st.warning("선택한 기간에 분석할 데이터가 없습니다.")
        st.stop()

    with st.spinner("기억점수와 위험점수를 계산하는 중..."):
        simulated = simulate_memory(calendar, M0, K1, C, D, R)
    with st.spinner("학교별 최종 위험지수를 요약하는 중..."):
        school_summary, core_summary = summarize_school(
            simulated,
            vacation_check,
            high_risk_threshold,
            min_vacation_days,
        )

    st.session_state["calendar"] = calendar
    st.session_state["vacation_check"] = vacation_check
    st.session_state["simulated"] = simulated
    st.session_state["school_summary"] = school_summary
    st.session_state["core_summary"] = core_summary
    st.success("분석 완료!")

if "core_summary" not in st.session_state:
    st.info("왼쪽에서 전처리 데이터를 확인하고 분석 실행 버튼을 누르세요.")
    st.stop()

core_summary = st.session_state["core_summary"].copy()
school_summary = st.session_state["school_summary"].copy()
simulated = st.session_state["simulated"].copy()
vacation_check = st.session_state["vacation_check"].copy()

if core_summary.empty:
    st.warning("핵심 분석 포함 최소 방학일수 조건을 만족하는 학교가 없습니다. 기준을 낮춰 다시 실행하세요.")
    st.stop()


excluded_count = len(school_summary) - len(core_summary)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("전체 학교-과정", f"{len(school_summary):,}")
col2.metric("핵심 분석 대상", f"{len(core_summary):,}")
col3.metric("제외", f"{excluded_count:,}", f"{excluded_count / max(len(school_summary), 1) * 100:.2f}%")
col4.metric("평균 위험지수", f"{core_summary['final_risk_index'].mean():.2f}")
col5.metric("휴업일-위험 상관", f"{core_summary['rest_day_ratio'].corr(core_summary['final_risk_index']):.3f}")

with st.expander("방학일수 데이터 점검", expanded=False):
    c1, c2, c3 = st.columns(3)
    c1.metric("방학일수 10일 미만", f"{(vacation_check['vacation_days'] < 10).sum():,}")
    c2.metric("방학일수 140일 이상", f"{(vacation_check['vacation_days'] >= 140).sum():,}")
    c3.metric("방학일수 최대값", f"{vacation_check['vacation_days'].max():.0f}일")
    st.dataframe(vacation_check["vacation_days"].describe().to_frame("방학일수"), use_container_width=True)


st.subheader("🔎 학교 검색 및 필터")
f1, f2, f3, f4 = st.columns([2.2, 1.2, 1.2, 1.4])
with f1:
    query = st.text_input("학교명 검색", placeholder="예: 대구여자고등학교")
with f2:
    regions = ["전체"] + sorted(core_summary["edu_name"].dropna().unique().tolist())
    region = st.selectbox("시도교육청", regions)
with f3:
    courses = ["전체"] + sorted(core_summary["school_level"].dropna().unique().tolist())
    course = st.selectbox("학교과정", courses)
with f4:
    sort_option = st.selectbox(
        "정렬",
        ["최종위험지수 높은순", "최종위험지수 낮은순", "휴업일비율 높은순", "방학일수 많은순", "학교명 가나다순"],
    )

filtered = core_summary.copy()
if query:
    mask = (
        filtered["school_name"].str.contains(query, case=False, na=False)
        | filtered["school_display_name"].str.contains(query, case=False, na=False)
    )
    filtered = filtered[mask]
if region != "전체":
    filtered = filtered[filtered["edu_name"] == region]
if course != "전체":
    filtered = filtered[filtered["school_level"] == course]

if sort_option == "최종위험지수 높은순":
    filtered = filtered.sort_values("final_risk_index", ascending=False)
elif sort_option == "최종위험지수 낮은순":
    filtered = filtered.sort_values("final_risk_index", ascending=True)
elif sort_option == "휴업일비율 높은순":
    filtered = filtered.sort_values("rest_day_ratio", ascending=False)
elif sort_option == "방학일수 많은순":
    filtered = filtered.sort_values("vacation_days", ascending=False)
else:
    filtered = filtered.sort_values("school_name", ascending=True)


st.subheader("📊 전체 분석 결과")
g1, g2 = st.columns(2)

region_summary = (
    core_summary.groupby("edu_name")
    .agg(
        school_count=("unit_id", "count"),
        avg_final_risk_index=("final_risk_index", "mean"),
        avg_rest_day_ratio=("rest_day_ratio", "mean"),
    )
    .reset_index()
    .sort_values("avg_final_risk_index", ascending=False)
)
course_summary = (
    core_summary.groupby("school_level")
    .agg(
        school_count=("unit_id", "count"),
        avg_final_risk_index=("final_risk_index", "mean"),
        avg_rest_day_ratio=("rest_day_ratio", "mean"),
    )
    .reset_index()
    .sort_values("avg_final_risk_index", ascending=False)
)

with g1:
    st.plotly_chart(
        px.bar(
            region_summary,
            x="avg_final_risk_index",
            y="edu_name",
            orientation="h",
            title="시도교육청별 평균 위험지수",
            labels={"avg_final_risk_index": "평균 위험지수", "edu_name": "시도교육청"},
        ),
        use_container_width=True,
    )
with g2:
    st.plotly_chart(
        px.bar(
            course_summary,
            x="school_level",
            y="avg_final_risk_index",
            title="학교과정별 평균 위험지수",
            labels={"school_level": "학교과정", "avg_final_risk_index": "평균 위험지수"},
        ),
        use_container_width=True,
    )

s1, s2 = st.columns(2)
with s1:
    st.plotly_chart(
        px.scatter(
            core_summary,
            x="rest_day_ratio",
            y="final_risk_index",
            color="school_level",
            hover_name="school_display_name",
            title="휴업일비율과 최종위험지수",
            labels={
                "rest_day_ratio": "휴업일비율",
                "final_risk_index": "최종위험지수",
                "school_level": "학교과정",
            },
        ),
        use_container_width=True,
    )
with s2:
    st.plotly_chart(
        px.scatter(
            core_summary,
            x="vacation_days",
            y="final_risk_index",
            color="school_level",
            hover_name="school_display_name",
            title="방학일수와 최종위험지수",
            labels={
                "vacation_days": "방학일수",
                "final_risk_index": "최종위험지수",
                "school_level": "학교과정",
            },
        ),
        use_container_width=True,
    )


st.subheader("🏫 학교별 결과")
st.caption(f"현재 필터 결과: {len(filtered):,}개 학교-과정")

show_cols = [
    "edu_name",
    "school_name",
    "school_level",
    "analysis_days",
    "rest_days",
    "study_days",
    "rest_day_ratio",
    "avg_risk_score",
    "high_risk_day_ratio",
    "final_risk_index",
    "risk_grade",
    "vacation_days",
    "relative_risk_grade",
]
show_cols = [col for col in show_cols if col in filtered.columns]
st.dataframe(filtered[show_cols].rename(columns=DISPLAY_RENAME).head(500), use_container_width=True, height=360)

if filtered.empty:
    st.warning("조건에 맞는 학교가 없습니다.")
    st.stop()

label_map = filtered.drop_duplicates("unit_id").set_index("unit_id")["school_select_label"].to_dict()
selected_id = st.selectbox(
    "상세 분석을 볼 학교를 선택하세요.",
    filtered["unit_id"].tolist(),
    index=0,
    format_func=lambda unit_id: label_map.get(unit_id, str(unit_id)),
)
selected_row = filtered[filtered["unit_id"] == selected_id].iloc[0]
one_school = simulated[simulated["unit_id"] == selected_id].sort_values("date").copy()

st.subheader(f"📌 {selected_row['school_display_name']} 상세 분석")
d1, d2, d3, d4, d5 = st.columns(5)
d1.metric("최종위험지수", f"{selected_row['final_risk_index']:.2f}")
d2.metric("휴업일비율", f"{selected_row['rest_day_ratio']:.2f}%")
d3.metric("분석일수", f"{int(selected_row['analysis_days']):,}일")
d4.metric("방학일수", f"{int(selected_row['vacation_days']):,}일")
d5.metric("고위험일비율", f"{selected_row['high_risk_day_ratio']:.2f}%")

st.plotly_chart(make_memory_figure(one_school, selected_row["school_display_name"]), use_container_width=True)

months = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="MS").strftime("%Y-%m").tolist()
calendar_month = st.selectbox("달력 월 선택", months, index=0)
components.html(make_calendar_html(one_school, calendar_month), height=720, scrolling=True)

with st.expander("선택 학교 날짜별 데이터 보기", expanded=False):
    detail_cols = [
        "date",
        "is_vacation_day",
        "is_rest_event",
        "is_no_deduction",
        "is_main_rest_day",
        "is_study_day",
        "memory_score",
        "risk_score",
        "p_value",
        "k_value",
        "calculation_type",
        "event_names",
    ]
    st.dataframe(one_school[detail_cols], use_container_width=True, height=400)


st.subheader("💾 결과 다운로드")
excel_bytes = to_excel_bytes(
    {
        "핵심분석_학교별요약": core_summary,
        "시도교육청별요약": region_summary,
        "학교과정별요약": course_summary,
        "방학일수점검": vacation_check,
    }
)
st.download_button(
    "엑셀로 결과 다운로드",
    data=excel_bytes,
    file_name="학습공백_위험지수_분석결과.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

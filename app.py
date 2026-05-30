import math
from io import BytesIO
from typing import List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# =========================================================
# Streamlit 기본 설정
# =========================================================

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
        border-radius: 18px;
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
        border-radius: 14px;
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

# =========================================================
# 유틸 함수
# =========================================================

def safe_display_name(row: pd.Series) -> str:
    return f"{row.get('학교명', '')} ({row.get('학교과정명', '')})"


def read_csv_safely(uploaded_file) -> pd.DataFrame:
    """공공데이터 CSV의 인코딩이 제각각일 수 있어서 여러 인코딩을 순서대로 시도."""
    raw = uploaded_file.getvalue()
    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]
    last_error = None

    for enc in encodings:
        try:
            return pd.read_csv(BytesIO(raw), encoding=enc, low_memory=False)
        except Exception as e:
            last_error = e

    raise ValueError(f"CSV 읽기 실패: {uploaded_file.name} / 마지막 오류: {last_error}")


def clean_text_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    return df


# =========================================================
# 1. 데이터 로드
# =========================================================

@st.cache_data(show_spinner=False, max_entries=2)
def load_uploaded_files(file_bytes_and_names: List[Tuple[bytes, str]]) -> pd.DataFrame:
    dfs = []
    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]

    for raw, name in file_bytes_and_names:
        last_error = None
        temp = None
        for enc in encodings:
            try:
                temp = pd.read_csv(BytesIO(raw), encoding=enc, low_memory=False)
                break
            except Exception as e:
                last_error = e
        if temp is None:
            raise ValueError(f"{name} 파일을 읽지 못했습니다. 마지막 오류: {last_error}")
        temp["원본파일명"] = name
        dfs.append(temp)

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    df.columns = df.columns.str.strip()
    return df


# =========================================================
# 2. 학교-과정-날짜 단위 요약
# =========================================================

@st.cache_data(show_spinner=False, max_entries=2)
def build_daily_school(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    df3 = df.copy()
    df3.columns = df3.columns.str.strip()

    required_cols = [
        "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명",
        "수업공제일명", "학사일자", "행사명", "행사내용"
    ]
    missing = [c for c in required_cols if c not in df3.columns]
    if missing:
        raise ValueError(f"필수 열이 없습니다: {missing}")

    df3["학사일자"] = df3["학사일자"].astype(str).str.replace(r"\D", "", regex=True)
    df3["date"] = pd.to_datetime(df3["학사일자"], format="%Y%m%d", errors="coerce")
    df3 = df3.dropna(subset=["date"]).copy()

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df3 = df3[(df3["date"] >= start_dt) & (df3["date"] <= end_dt)].copy()

    text_cols = [
        "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학년도",
        "주야과정명", "학교과정명", "수업공제일명", "행사명", "행사내용", "수정일자", "원본파일명"
    ]
    df3 = clean_text_columns(df3, text_cols)

    # 휴업일/공휴일 판정
    df3["is_rest_event"] = df3["수업공제일명"].isin(["휴업일", "공휴일"])

    # 사용자가 최종적으로 선택한 원래 방식: 행사명/내용에 '방학'이 들어가면 방학 관련 일정으로 처리
    vacation_keywords = "방학|여름방학|겨울방학|봄방학|학년말방학|동계방학|하계방학|방학식"
    df3["is_vacation_event"] = (
        df3["행사명"].fillna("").str.contains(vacation_keywords, regex=True) |
        df3["행사내용"].fillna("").str.contains(vacation_keywords, regex=True)
    )

    unit_cols = ["시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명"]

    def join_unique(values):
        values = [str(v).strip() for v in values if str(v).strip()]
        return ", ".join(sorted(set(values)))

    daily_school = (
        df3.groupby(unit_cols + ["date"], as_index=False)
        .agg(
            is_rest_event=("is_rest_event", "max"),
            is_vacation_day=("is_vacation_event", "max"),
            행사개수=("행사명", "size"),
            행사명_목록=("행사명", join_unique),
            수업공제일명_목록=("수업공제일명", join_unique),
        )
    )

    daily_school["분석단위ID"] = (
        daily_school["시도교육청코드"].astype(str) + "_" +
        daily_school["행정표준코드"].astype(str) + "_" +
        daily_school["학교과정명"].astype(str)
    )

    daily_school["학교표시명"] = daily_school["학교명"] + " (" + daily_school["학교과정명"] + ")"

    daily_school["is_term_rest_day"] = daily_school["is_rest_event"] & ~daily_school["is_vacation_day"]

    return daily_school


# =========================================================
# 3. 1년 전체 날짜표 생성
# =========================================================

@st.cache_data(show_spinner=False, max_entries=2)
def build_calendar(daily_school: pd.DataFrame, start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    all_dates = pd.DataFrame({"date": pd.date_range(start_dt, end_dt, freq="D")})

    unit_cols = [
        "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명", "분석단위ID", "학교표시명"
    ]
    units = daily_school[unit_cols].drop_duplicates().copy()
    calendar = units.merge(all_dates, how="cross")

    merge_cols = [
        "분석단위ID", "date", "is_rest_event", "is_vacation_day", "is_term_rest_day",
        "행사개수", "행사명_목록", "수업공제일명_목록"
    ]
    calendar = calendar.merge(daily_school[merge_cols], on=["분석단위ID", "date"], how="left")

    bool_cols = ["is_rest_event", "is_vacation_day", "is_term_rest_day"]
    for col in bool_cols:
        calendar[col] = calendar[col].fillna(False).astype(bool)

    calendar["행사개수"] = calendar["행사개수"].fillna(0).astype(int)
    calendar["행사명_목록"] = calendar["행사명_목록"].fillna("")
    calendar["수업공제일명_목록"] = calendar["수업공제일명_목록"].fillna("")

    calendar["요일번호"] = calendar["date"].dt.weekday
    calendar["is_weekend"] = calendar["요일번호"] >= 5

    calendar["is_main_rest_day"] = (~calendar["is_vacation_day"]) & (
        calendar["is_weekend"] | calendar["is_term_rest_day"]
    )
    calendar["is_main_analysis_day"] = ~calendar["is_vacation_day"]
    calendar["is_study_day"] = calendar["is_main_analysis_day"] & ~calendar["is_main_rest_day"]

    vacation_check = (
        calendar.groupby([
            "시도교육청명", "행정표준코드", "학교명", "학교과정명", "분석단위ID", "학교표시명"
        ])
        .agg(
            전체일수=("date", "nunique"),
            방학일수=("is_vacation_day", "sum"),
            메인분석일수=("is_main_analysis_day", "sum"),
            휴업일수=("is_main_rest_day", "sum"),
            수업일수=("is_study_day", "sum"),
        )
        .reset_index()
    )
    vacation_check["추론방학일수"] = 0

    return calendar, vacation_check


# =========================================================
# 4. 기억점수 시뮬레이션
# =========================================================

def simulate_one_group(group: pd.DataFrame, M0: float, K1: float, C: float, D: float, R: float) -> pd.DataFrame:
    group = group.sort_values("date").copy()
    memory = M0
    p = 0

    memory_scores = []
    risk_scores = []
    k_values = []
    p_values = []
    calculation_types = []

    for _, row in group.iterrows():
        if not row["is_main_analysis_day"]:
            memory_scores.append(np.nan)
            risk_scores.append(np.nan)
            k_values.append(np.nan)
            p_values.append(np.nan)
            calculation_types.append("방학 제외")
            memory = M0
            p = 0
            continue

        if row["is_main_rest_day"]:
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
        risk = M0 - memory

        memory_scores.append(memory)
        risk_scores.append(risk)
        k_values.append(k)
        p_values.append(p)
        calculation_types.append(calculation_type)

    group["memory_score"] = memory_scores
    group["risk_score"] = risk_scores
    group["k_value"] = k_values
    group["p_value"] = p_values
    group["calculation_type"] = calculation_types

    return group


@st.cache_data(show_spinner=False, max_entries=2)
def simulate_memory(calendar: pd.DataFrame, M0: float, K1: float, C: float, D: float, R: float) -> pd.DataFrame:
    if calendar.empty:
        return calendar.copy()

    results = []

    sorted_calendar = calendar.sort_values(["분석단위ID", "date"]).copy()

    for unit_id, group in sorted_calendar.groupby("분석단위ID", sort=False):
        simulated_group = simulate_one_group(group.copy(), M0, K1, C, D, R)

        # pandas groupby/apply 버전 차이로 식별자 열이 빠지는 상황 방지
        if "분석단위ID" not in simulated_group.columns:
            simulated_group["분석단위ID"] = unit_id

        results.append(simulated_group)

    simulated = pd.concat(results, ignore_index=True)

    return simulated

# =========================================================
# 5. 학교별 요약
# =========================================================

@st.cache_data(show_spinner=False, max_entries=2)
def summarize_school(simulated: pd.DataFrame, vacation_check: pd.DataFrame, high_risk_threshold: float, min_vacation_days: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    group_cols = [
        "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명", "분석단위ID", "학교표시명"
    ]

    missing_cols = [c for c in group_cols if c not in simulated.columns]
    if missing_cols:
        raise ValueError(
            f"simulated 데이터에 필요한 열이 없습니다: {missing_cols} / "
            f"현재 열 목록: {simulated.columns.tolist()}"
        )

    analysis_data = simulated[simulated["is_main_analysis_day"]].copy()

    school_summary = (
        analysis_data.groupby(group_cols)
        .agg(
            분석일수=("date", "nunique"),
            휴업일수=("is_main_rest_day", "sum"),
            수업일수=("is_study_day", "sum"),
            평균기억점수=("memory_score", "mean"),
            평균위험점수=("risk_score", "mean"),
            최대위험점수=("risk_score", "max"),
            최저기억점수=("memory_score", "min"),
            고위험일수=("risk_score", lambda x: (x >= high_risk_threshold).sum()),
        )
        .reset_index()
    )

    school_summary["휴업일비율"] = school_summary["휴업일수"] / school_summary["분석일수"] * 100
    school_summary["고위험일비율"] = school_summary["고위험일수"] / school_summary["분석일수"] * 100
    school_summary["최종위험지수"] = 0.7 * school_summary["평균위험점수"] + 0.3 * school_summary["고위험일비율"]

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

    school_summary["위험등급"] = school_summary["최종위험지수"].apply(risk_grade)

    school_summary = school_summary.merge(
        vacation_check[["분석단위ID", "방학일수", "추론방학일수"]],
        on="분석단위ID",
        how="left",
    )

    school_summary["방학일수"] = school_summary["방학일수"].fillna(0)
    school_summary["추론방학일수"] = school_summary["추론방학일수"].fillna(0)

    core_summary = school_summary[school_summary["방학일수"] >= min_vacation_days].copy()

    core_summary["위험백분위"] = core_summary["최종위험지수"].rank(pct=True) * 100

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

    core_summary["상대위험등급"] = core_summary["위험백분위"].apply(relative_grade)
    core_summary = core_summary.sort_values("최종위험지수", ascending=False)

    return school_summary, core_summary


# =========================================================
# 6. 시각화 보조 함수
# =========================================================

def make_memory_figure(one_school: pd.DataFrame, school_name: str) -> go.Figure:
    df = one_school.sort_values("date").copy()
    df["memory_plot"] = df["memory_score"].where(~df["is_vacation_day"], np.nan)
    df["risk_plot"] = df["risk_score"].where(~df["is_vacation_day"], np.nan)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["memory_plot"], mode="lines", name="기억점수", connectgaps=False))
    fig.add_trace(go.Scatter(x=df["date"], y=df["risk_plot"], mode="lines", name="위험점수", connectgaps=False))

    rest = df[df["is_main_rest_day"]]
    fig.add_trace(go.Scatter(
        x=rest["date"], y=rest["memory_score"], mode="markers", name="휴업일",
        marker=dict(size=5)
    ))

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
    start_weekday = (first.weekday() + 1) % 7  # 일요일=0
    weekdays = ["일", "월", "화", "수", "목", "금", "토"]

    cells = ""
    for w in weekdays:
        cells += f'<div class="calendar-head">{w}</div>'

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

        event = str(row.get("행사명_목록", ""))
        if event == "nan":
            event = ""

        cells += f"""
        <div class="calendar-day {cls}">
            <div class="day-top">
                <b>{day}</b>{badge}
            </div>
            <div class="score" title="{score}">{score}</div>
            <div class="event" title="{event}">{event or '-'}</div>
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
        .calendar-day {{ min-height: 92px; border-radius: 16px; border: 1px solid #e5e7eb; padding: 10px; font-size: 13px; overflow: hidden; }}
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


def to_excel_bytes(dfs: dict) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


# =========================================================
# 앱 화면
# =========================================================

st.title("📚 학사일정 기반 학습 공백 위험지수 대시보드")
st.caption("CSV 업로드 → Python 분석 → 학교별 검색·필터·그래프·달력 확인까지 한 번에 처리합니다.")

with st.sidebar:
    st.header("1. 데이터 업로드")
    uploaded_files = st.file_uploader(
        "월별 학사일정 CSV 파일을 업로드하세요.",
        type=["csv"],
        accept_multiple_files=True,
    )

    st.header("2. 분석 기간")
    start_date = st.date_input("시작일", value=pd.to_datetime("2025-03-01"))
    end_date = st.date_input("종료일", value=pd.to_datetime("2026-02-28"))

    st.header("3. 모델 파라미터")
    M0 = st.number_input("최대 기억점수 M0", value=100.0, min_value=1.0, step=1.0)
    K1 = st.number_input("초기 망각 속도 K1", value=0.35, min_value=0.0, step=0.01)
    C = st.number_input("k 감소 상수 C", value=0.5, min_value=0.0, step=0.1)
    D = st.number_input("k 감소 형태 D", value=1.0, min_value=0.1, step=0.1)
    R = st.number_input("수업일 회복률 R", value=0.30, min_value=0.0, max_value=1.0, step=0.05)
    high_risk_threshold = st.number_input("고위험 기준 점수", value=60.0, min_value=0.0, max_value=100.0, step=5.0)
    min_vacation_days = st.number_input("핵심 분석 포함 최소 방학일수", value=10, min_value=0, step=1)

    run_btn = st.button("🚀 분석 실행", type="primary", use_container_width=True)

if run_btn:
    for key in [
        "raw_df",
        "daily_school",
        "calendar",
        "vacation_check",
        "simulated",
        "school_summary",
        "core_summary",
    ]:
        if key in st.session_state:
            del st.session_state[key]

    if not uploaded_files:
        st.error("먼저 CSV 파일을 업로드하세요.")
    else:
        file_payload = [(f.getvalue(), f.name) for f in uploaded_files]
        with st.spinner("CSV 파일을 읽는 중..."):
            raw_df = load_uploaded_files(file_payload)
        with st.spinner("학교-과정-날짜 단위로 정리하는 중..."):
            daily_school = build_daily_school(raw_df, str(start_date), str(end_date))
        with st.spinner("1년 전체 날짜표를 만드는 중..."):
            calendar, vacation_check = build_calendar(daily_school, str(start_date), str(end_date))
        with st.spinner("기억점수와 위험점수를 계산하는 중... 데이터가 크면 시간이 걸릴 수 있어요."):
            simulated = simulate_memory(calendar, M0, K1, C, D, R)
        with st.spinner("학교별 최종 위험지수를 요약하는 중..."):
            school_summary, core_summary = summarize_school(simulated, vacation_check, high_risk_threshold, min_vacation_days)

        st.session_state["raw_df"] = raw_df
        st.session_state["daily_school"] = daily_school
        st.session_state["calendar"] = calendar
        st.session_state["vacation_check"] = vacation_check
        st.session_state["simulated"] = simulated
        st.session_state["school_summary"] = school_summary
        st.session_state["core_summary"] = core_summary
        st.success("분석 완료!")

if "core_summary" not in st.session_state:
    st.info("왼쪽에서 CSV 파일을 업로드하고 분석 실행 버튼을 누르세요.")
    st.stop()

core_summary = st.session_state["core_summary"].copy()
school_summary = st.session_state["school_summary"].copy()
simulated = st.session_state["simulated"].copy()
vacation_check = st.session_state["vacation_check"].copy()

# =========================================================
# 요약 카드
# =========================================================

excluded_count = len(school_summary) - len(core_summary)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("전체 학교-과정", f"{len(school_summary):,}")
col2.metric("핵심 분석 대상", f"{len(core_summary):,}")
col3.metric("제외", f"{excluded_count:,}", f"{excluded_count / max(len(school_summary), 1) * 100:.2f}%")
col4.metric("평균 위험지수", f"{core_summary['최종위험지수'].mean():.2f}")
col5.metric("휴업일-위험 상관", f"{core_summary['휴업일비율'].corr(core_summary['최종위험지수']):.3f}")

with st.expander("방학일수 데이터 점검", expanded=False):
    c1, c2, c3 = st.columns(3)
    c1.metric("방학일수 10일 미만", f"{(vacation_check['방학일수'] < 10).sum():,}")
    c2.metric("방학일수 140일 이상", f"{(vacation_check['방학일수'] >= 140).sum():,}")
    c3.metric("방학일수 최대값", f"{vacation_check['방학일수'].max():.0f}일")
    st.dataframe(vacation_check["방학일수"].describe().to_frame("방학일수"), use_container_width=True)

# =========================================================
# 필터 영역
# =========================================================

st.subheader("🔎 학교 검색 및 필터")
f1, f2, f3, f4 = st.columns([2.2, 1.2, 1.2, 1.4])
with f1:
    query = st.text_input("학교명 검색", placeholder="예: 대구여자고등학교")
with f2:
    regions = ["전체"] + sorted(core_summary["시도교육청명"].dropna().unique().tolist())
    region = st.selectbox("시도교육청", regions)
with f3:
    courses = ["전체"] + sorted(core_summary["학교과정명"].dropna().unique().tolist())
    course = st.selectbox("학교과정", courses)
with f4:
    sort_option = st.selectbox("정렬", ["최종위험지수 높은순", "최종위험지수 낮은순", "휴업일비율 높은순", "방학일수 많은순", "학교명 가나다순"])

filtered = core_summary.copy()
if query:
    mask = (
        filtered["학교명"].str.contains(query, case=False, na=False) |
        filtered["학교표시명"].str.contains(query, case=False, na=False)
    )
    filtered = filtered[mask]
if region != "전체":
    filtered = filtered[filtered["시도교육청명"] == region]
if course != "전체":
    filtered = filtered[filtered["학교과정명"] == course]

if sort_option == "최종위험지수 높은순":
    filtered = filtered.sort_values("최종위험지수", ascending=False)
elif sort_option == "최종위험지수 낮은순":
    filtered = filtered.sort_values("최종위험지수", ascending=True)
elif sort_option == "휴업일비율 높은순":
    filtered = filtered.sort_values("휴업일비율", ascending=False)
elif sort_option == "방학일수 많은순":
    filtered = filtered.sort_values("방학일수", ascending=False)
else:
    filtered = filtered.sort_values("학교명", ascending=True)

# =========================================================
# 전체 그래프
# =========================================================

st.subheader("📊 전체 분석 결과")
g1, g2 = st.columns(2)

region_summary = (
    core_summary.groupby("시도교육청명")
    .agg(
        학교수=("분석단위ID", "count"),
        평균최종위험지수=("최종위험지수", "mean"),
        평균휴업일비율=("휴업일비율", "mean"),
    )
    .reset_index()
    .sort_values("평균최종위험지수", ascending=False)
)

course_summary = (
    core_summary.groupby("학교과정명")
    .agg(
        학교수=("분석단위ID", "count"),
        평균최종위험지수=("최종위험지수", "mean"),
        평균휴업일비율=("휴업일비율", "mean"),
    )
    .reset_index()
    .sort_values("평균최종위험지수", ascending=False)
)


def get_zoom_axis(series: pd.Series, min_span: float = 1.0, pad_ratio: float = 0.18) -> Tuple[List[float], float]:
    """
    평균 위험지수 값들이 서로 비슷할 때 차이가 잘 보이도록 축 범위를 자동 확대한다.
    단, 그래프가 과도하게 길어 보이지 않도록 최소 표시 폭과 여백을 제한한다.
    """
    values = pd.to_numeric(series, errors="coerce").dropna()

    if values.empty:
        return [0.0, 1.0], 0.1

    v_min = float(values.min())
    v_max = float(values.max())
    data_span = v_max - v_min

    if data_span == 0:
        center = v_min
        half_span = min_span / 2
        axis_min = center - half_span
        axis_max = center + half_span
    else:
        span = max(data_span, min_span)
        padding = span * pad_ratio
        center = (v_min + v_max) / 2
        axis_min = center - span / 2 - padding
        axis_max = center + span / 2 + padding

    axis_min = max(0.0, axis_min)

    axis_span = axis_max - axis_min

    if axis_span <= 0.5:
        dtick = 0.05
    elif axis_span <= 1.5:
        dtick = 0.1
    elif axis_span <= 3:
        dtick = 0.2
    elif axis_span <= 6:
        dtick = 0.5
    else:
        dtick = 1.0

    return [axis_min, axis_max], dtick


region_x_range, region_x_dtick = get_zoom_axis(
    region_summary["평균최종위험지수"],
    min_span=1.0,
)

course_y_range, course_y_dtick = get_zoom_axis(
    course_summary["평균최종위험지수"],
    min_span=1.0,
)

# 시도교육청 그래프는 항목 수가 많으므로 높이를 자동 조절하되 너무 길어지지 않도록 상한을 둔다.
region_fig_height = min(520, max(380, 24 * len(region_summary) + 150))
course_fig_height = 420

with g1:
    region_fig = px.bar(
        region_summary,
        x="평균최종위험지수",
        y="시도교육청명",
        orientation="h",
        title="시도교육청별 평균 위험지수",
        labels={
            "평균최종위험지수": "평균 위험지수",
            "시도교육청명": "시도교육청",
        },
        text="평균최종위험지수",
    )

    region_fig.update_traces(
        texttemplate="%{x:.2f}",
        textposition="outside",
        cliponaxis=False,
    )

    region_fig.update_xaxes(
        range=region_x_range,
        dtick=region_x_dtick,
        tickformat=".2f",
        title="평균 위험지수",
    )

    region_fig.update_yaxes(
        categoryorder="array",
        categoryarray=region_summary["시도교육청명"].iloc[::-1].tolist(),
        title="시도교육청",
    )

    region_fig.update_layout(
        height=region_fig_height,
        margin=dict(l=10, r=60, t=60, b=40),
    )

    st.plotly_chart(region_fig, use_container_width=True)

with g2:
    course_fig = px.bar(
        course_summary,
        x="학교과정명",
        y="평균최종위험지수",
        title="학교과정별 평균 위험지수",
        labels={
            "학교과정명": "학교과정",
            "평균최종위험지수": "평균 위험지수",
        },
        text="평균최종위험지수",
    )

    course_fig.update_traces(
        texttemplate="%{y:.2f}",
        textposition="outside",
        cliponaxis=False,
    )

    course_fig.update_yaxes(
        range=course_y_range,
        dtick=course_y_dtick,
        tickformat=".2f",
        title="평균 위험지수",
    )

    course_fig.update_xaxes(
        title="학교과정",
    )

    course_fig.update_layout(
        height=course_fig_height,
        margin=dict(l=10, r=35, t=60, b=40),
    )

    st.plotly_chart(course_fig, use_container_width=True)

st.caption(
    "※ 위 두 그래프는 평균 위험지수 차이가 작게 보이는 문제를 줄이기 위해 값 축을 자동 확대했습니다. "
    "막대의 절대 길이보다 막대 끝 수치와 축 눈금을 함께 비교하세요."
)

s1, s2 = st.columns(2)

with s1:
    st.plotly_chart(
        px.scatter(
            core_summary,
            x="휴업일비율",
            y="최종위험지수",
            color="학교과정명",
            hover_name="학교표시명",
            title="휴업일비율과 최종위험지수",
        ),
        use_container_width=True,
    )

with s2:
    st.plotly_chart(
        px.scatter(
            core_summary,
            x="방학일수",
            y="최종위험지수",
            color="학교과정명",
            hover_name="학교표시명",
            title="방학일수와 최종위험지수",
        ),
        use_container_width=True,
    )
# =========================================================
# 학교 표 및 선택
# =========================================================

st.subheader("🏫 학교별 결과")
st.caption(f"현재 필터 결과: {len(filtered):,}개 학교-과정")

show_cols = [
    "시도교육청명", "학교명", "학교과정명", "분석일수", "휴업일수", "수업일수", "휴업일비율",
    "평균위험점수", "고위험일비율", "최종위험지수", "위험등급", "방학일수", "상대위험등급"
]
show_cols = [c for c in show_cols if c in filtered.columns]
st.dataframe(filtered[show_cols].head(500), use_container_width=True, height=360)

if len(filtered) == 0:
    st.warning("조건에 맞는 학교가 없습니다.")
    st.stop()

selected_label = st.selectbox(
    "상세 분석을 볼 학교를 선택하세요.",
    filtered["학교표시명"].tolist(),
    index=0,
)
selected_row = filtered[filtered["학교표시명"] == selected_label].iloc[0]
selected_id = selected_row["분석단위ID"]
one_school = simulated[simulated["분석단위ID"] == selected_id].sort_values("date").copy()

st.subheader(f"📌 {selected_row['학교표시명']} 상세 분석")
d1, d2, d3, d4, d5 = st.columns(5)
d1.metric("최종위험지수", f"{selected_row['최종위험지수']:.2f}")
d2.metric("휴업일비율", f"{selected_row['휴업일비율']:.2f}%")
d3.metric("분석일수", f"{int(selected_row['분석일수']):,}일")
d4.metric("방학일수", f"{int(selected_row['방학일수']):,}일")
d5.metric("고위험일비율", f"{selected_row['고위험일비율']:.2f}%")

st.plotly_chart(make_memory_figure(one_school, selected_row["학교표시명"]), use_container_width=True)

# 월별 달력
months = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="MS").strftime("%Y-%m").tolist()
calendar_month = st.selectbox("달력 월 선택", months, index=0)
components.html(make_calendar_html(one_school, calendar_month), height=720, scrolling=True)

with st.expander("선택 학교 날짜별 데이터 보기", expanded=False):
    detail_cols = [
        "date", "is_vacation_day", "is_main_rest_day", "is_study_day", "memory_score", "risk_score",
        "p_value", "k_value", "calculation_type", "행사명_목록"
    ]
    st.dataframe(one_school[detail_cols], use_container_width=True, height=400)

# =========================================================
# 다운로드
# =========================================================

st.subheader("💾 결과 다운로드")
excel_bytes = to_excel_bytes({
    "핵심분석_학교별요약": core_summary,
    "시도교육청별요약": region_summary,
    "학교과정별요약": course_summary,
    "방학일수점검": vacation_check,
})
st.download_button(
    "엑셀로 결과 다운로드",
    data=excel_bytes,
    file_name="학습공백_위험지수_분석결과.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

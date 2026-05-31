import math
import re
import html
from io import BytesIO
from typing import List, Tuple

@@ -31,56 +32,30 @@
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
# 고정 방학 키워드
# 화면에는 띄우지 않고, 코드 내부에서 방학 판정에만 사용
# =========================================================

def safe_display_name(row: pd.Series) -> str:
    return f"{row.get('학교명', '')} ({row.get('학교과정명', '')})"
DEFAULT_VACATION_KEYWORDS = """동계 휴가
하계 휴가
겨울 휴가
여름 휴가
동계휴가
하계휴가
학년말 휴가
휴가기간"""

# =========================================================
# 유틸 함수
# =========================================================

def read_csv_safely(uploaded_file) -> pd.DataFrame:
    """공공데이터 CSV의 인코딩이 제각각일 수 있어서 여러 인코딩을 순서대로 시도."""
    raw = uploaded_file.getvalue()
    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]
    last_error = None
@@ -113,14 +88,17 @@ def load_uploaded_files(file_bytes_and_names: List[Tuple[bytes, str]]) -> pd.Dat
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

@@ -137,71 +115,137 @@ def load_uploaded_files(file_bytes_and_names: List[Tuple[bytes, str]]) -> pd.Dat
# =========================================================

@st.cache_data(show_spinner=False)
def build_daily_school(df: pd.DataFrame, start_date: str, end_date: str, vacation_keyword_text: str = "") -> pd.DataFrame:
def build_daily_school(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    vacation_keyword_text: str = "",
) -> pd.DataFrame:
    df3 = df.copy()
    df3.columns = df3.columns.str.strip()

    required_cols = [
        "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명",
        "수업공제일명", "학사일자", "행사명", "행사내용"
        "시도교육청코드",
        "시도교육청명",
        "행정표준코드",
        "학교명",
        "학교과정명",
        "수업공제일명",
        "학사일자",
        "행사명",
        "행사내용",
    ]

    missing = [c for c in required_cols if c not in df3.columns]
    if missing:
        raise ValueError(f"필수 열이 없습니다: {missing}")
        raise ValueError(
            f"필수 열이 없습니다: {missing}. 현재 열 목록: {df3.columns.tolist()}"
        )

    # 날짜 변환 안정화
    # 20250301, 20250301.0, 2025-03-01 같은 값에서 8자리 날짜만 추출
    df3["학사일자_clean"] = (
        df3["학사일자"]
        .astype(str)
        .str.extract(r"(\d{8})")[0]
    )

    df3["date"] = pd.to_datetime(
        df3["학사일자_clean"],
        format="%Y%m%d",
        errors="coerce",
    )

    df3["학사일자"] = df3["학사일자"].astype(str).str.replace(r"\D", "", regex=True)
    df3["date"] = pd.to_datetime(df3["학사일자"], format="%Y%m%d", errors="coerce")
    df3 = df3.dropna(subset=["date"]).copy()

    if df3.empty:
        raise ValueError(
            "날짜 변환 후 남은 데이터가 없습니다. 업로드한 CSV의 학사일자 형식 또는 분석 기간을 확인하세요."
        )

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    df3 = df3[(df3["date"] >= start_dt) & (df3["date"] <= end_dt)].copy()

    if df3.empty:
        raise ValueError(
            f"분석 기간({start_date}~{end_date})에 해당하는 데이터가 없습니다. 업로드한 파일의 학사일자를 확인하세요."
        )

    text_cols = [
        "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학년도",
        "주야과정명", "학교과정명", "수업공제일명", "행사명", "행사내용", "수정일자", "원본파일명"
        "시도교육청코드",
        "시도교육청명",
        "행정표준코드",
        "학교명",
        "학년도",
        "주야과정명",
        "학교과정명",
        "수업공제일명",
        "행사명",
        "행사내용",
        "수정일자",
        "원본파일명",
    ]
    df3 = clean_text_columns(df3, text_cols)

    # 휴업일/공휴일 판정
    # 원본 기준 휴업/공휴일 판정
    df3["is_rest_event"] = df3["수업공제일명"].isin(["휴업일", "공휴일"])

    # 방학 판정 강화:
    # 1) '방학' 계열 표현은 항상 방학으로 처리
    # 2) '동계 휴가', '하계 휴가', '겨울 휴가'처럼 방학 대신 휴가로 적힌 표현도 처리
    # 3) '휴가'처럼 넓은 표현은 여름/겨울 방학 시즌 + 휴업/공휴일인 경우에만 방학으로 처리
    # 4) 사용자가 사이드바에 추가 키워드를 넣으면 함께 반영
    # 방학 판정 강화
    df3["month"] = df3["date"].dt.month
    event_text = (df3["행사명"].fillna("") + " " + df3["행사내용"].fillna(""))
    event_text_no_space = event_text.str.replace(" ", "", regex=False)
    event_text = df3["행사명"].fillna("") + " " + df3["행사내용"].fillna("")
    event_text_no_space = event_text.str.replace(r"\s+", "", regex=True)

    direct_vacation_pattern = (
        "방학|여름방학|겨울방학|봄방학|학년말방학|학기말방학|"
        "동계방학|하계방학|방학식|여름방학식|겨울방학식|"
        "동계휴가|하계휴가|여름휴가|겨울휴가|봄휴가|학년말휴가|학기말휴가|휴가기간"
        "동계휴가|하계휴가|여름휴가|겨울휴가|봄휴가|"
        "학년말휴가|학기말휴가|휴가기간"
    )

    custom_keywords = [kw.strip() for kw in str(vacation_keyword_text).splitlines() if kw.strip()]
    custom_keywords_no_space = [kw.replace(" ", "") for kw in custom_keywords]
    custom_keywords = [
        kw.strip()
        for kw in str(vacation_keyword_text).splitlines()
        if kw.strip()
    ]
    custom_keywords_no_space = [re.sub(r"\s+", "", kw) for kw in custom_keywords]
    custom_pattern = "|".join(re.escape(kw) for kw in custom_keywords_no_space)

    is_direct_vacation = event_text_no_space.str.contains(direct_vacation_pattern, regex=True, na=False)
    is_direct_vacation = event_text_no_space.str.contains(
        direct_vacation_pattern,
        regex=True,
        na=False,
    )

    if custom_pattern:
        is_custom_vacation = event_text_no_space.str.contains(custom_pattern, regex=True, na=False)
        is_custom_vacation = event_text_no_space.str.contains(
            custom_pattern,
            regex=True,
            na=False,
        )
    else:
        is_custom_vacation = False

    # 휴가처럼 넓은 표현은 방학 시즌 + 휴업/공휴일인 경우에만 방학으로 처리
    vacation_season_month = df3["month"].isin([1, 2, 7, 8, 12])
    is_seasonal_vacation_like = (
        vacation_season_month &
        df3["is_rest_event"] &
        event_text_no_space.str.contains("휴가|동계|하계", regex=True, na=False)
        vacation_season_month
        & df3["is_rest_event"]
        & event_text_no_space.str.contains("휴가|동계|하계", regex=True, na=False)
    )

    df3["is_vacation_event"] = is_direct_vacation | is_custom_vacation | is_seasonal_vacation_like
    df3["is_vacation_event"] = (
        is_direct_vacation | is_custom_vacation | is_seasonal_vacation_like
    )

    unit_cols = ["시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명"]
    unit_cols = [
        "시도교육청코드",
        "시도교육청명",
        "행정표준코드",
        "학교명",
        "학교과정명",
    ]

    def join_unique(values):
        values = [str(v).strip() for v in values if str(v).strip()]
@@ -219,14 +263,21 @@ def join_unique(values):
    )

    daily_school["분석단위ID"] = (
        daily_school["시도교육청코드"].astype(str) + "_" +
        daily_school["행정표준코드"].astype(str) + "_" +
        daily_school["학교과정명"].astype(str)
        daily_school["시도교육청코드"].astype(str)
        + "_"
        + daily_school["행정표준코드"].astype(str)
        + "_"
        + daily_school["학교과정명"].astype(str)
    )

    daily_school["학교표시명"] = daily_school["학교명"] + " (" + daily_school["학교과정명"] + ")"
    daily_school["학교표시명"] = (
        daily_school["학교명"] + " (" + daily_school["학교과정명"] + ")"
    )

    daily_school["is_term_rest_day"] = daily_school["is_rest_event"] & ~daily_school["is_vacation_day"]
    # 방학은 학기 중 휴업일에서 제외
    daily_school["is_term_rest_day"] = (
        daily_school["is_rest_event"] & ~daily_school["is_vacation_day"]
    )

    return daily_school

@@ -236,26 +287,53 @@ def join_unique(values):
# =========================================================

@st.cache_data(show_spinner=False)
def build_calendar(daily_school: pd.DataFrame, start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
def build_calendar(
    daily_school: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    all_dates = pd.DataFrame({"date": pd.date_range(start_dt, end_dt, freq="D")})

    unit_cols = [
        "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명", "분석단위ID", "학교표시명"
        "시도교육청코드",
        "시도교육청명",
        "행정표준코드",
        "학교명",
        "학교과정명",
        "분석단위ID",
        "학교표시명",
    ]

    missing_unit_cols = [c for c in unit_cols if c not in daily_school.columns]
    if missing_unit_cols:
        raise ValueError(
            f"daily_school에 필요한 열이 없습니다: {missing_unit_cols}. 현재 열 목록: {daily_school.columns.tolist()}"
        )

    units = daily_school[unit_cols].drop_duplicates().copy()
    calendar = units.merge(all_dates, how="cross")

    merge_cols = [
        "분석단위ID", "date", "is_rest_event", "is_vacation_day", "is_term_rest_day",
        "행사개수", "행사명_목록", "수업공제일명_목록"
        "분석단위ID",
        "date",
        "is_rest_event",
        "is_vacation_day",
        "is_term_rest_day",
        "행사개수",
        "행사명_목록",
        "수업공제일명_목록",
    ]
    calendar = calendar.merge(daily_school[merge_cols], on=["분석단위ID", "date"], how="left")

    bool_cols = ["is_rest_event", "is_vacation_day", "is_term_rest_day"]
    for col in bool_cols:
    calendar = calendar.merge(
        daily_school[merge_cols],
        on=["분석단위ID", "date"],
        how="left",
    )

    for col in ["is_rest_event", "is_vacation_day", "is_term_rest_day"]:
        calendar[col] = calendar[col].fillna(False).astype(bool)

    calendar["행사개수"] = calendar["행사개수"].fillna(0).astype(int)
@@ -269,12 +347,21 @@ def build_calendar(daily_school: pd.DataFrame, start_date: str, end_date: str) -
        calendar["is_weekend"] | calendar["is_term_rest_day"]
    )
    calendar["is_main_analysis_day"] = ~calendar["is_vacation_day"]
    calendar["is_study_day"] = calendar["is_main_analysis_day"] & ~calendar["is_main_rest_day"]
    calendar["is_study_day"] = (
        calendar["is_main_analysis_day"] & ~calendar["is_main_rest_day"]
    )

    vacation_check = (
        calendar.groupby([
            "시도교육청명", "행정표준코드", "학교명", "학교과정명", "분석단위ID", "학교표시명"
        ])
        calendar.groupby(
            [
                "시도교육청명",
                "행정표준코드",
                "학교명",
                "학교과정명",
                "분석단위ID",
                "학교표시명",
            ]
        )
        .agg(
            전체일수=("date", "nunique"),
            방학일수=("is_vacation_day", "sum"),
@@ -293,7 +380,14 @@ def build_calendar(daily_school: pd.DataFrame, start_date: str, end_date: str) -
# 4. 기억점수 시뮬레이션
# =========================================================

def simulate_one_group(group: pd.DataFrame, M0: float, K1: float, C: float, D: float, R: float) -> pd.DataFrame:
def simulate_one_group(
    group: pd.DataFrame,
    M0: float,
    K1: float,
    C: float,
    D: float,
    R: float,
) -> pd.DataFrame:
    group = group.sort_values("date").copy()
    memory = M0
    p = 0
@@ -304,8 +398,11 @@ def simulate_one_group(group: pd.DataFrame, M0: float, K1: float, C: float, D: f
    p_values = []
    calculation_types = []

    for _, row in group.iterrows():
        if not row["is_main_analysis_day"]:
    for row in group.itertuples(index=False):
        is_main_analysis_day = bool(getattr(row, "is_main_analysis_day"))
        is_main_rest_day = bool(getattr(row, "is_main_rest_day"))

        if not is_main_analysis_day:
            memory_scores.append(np.nan)
            risk_scores.append(np.nan)
            k_values.append(np.nan)
@@ -315,7 +412,7 @@ def simulate_one_group(group: pd.DataFrame, M0: float, K1: float, C: float, D: f
            p = 0
            continue

        if row["is_main_rest_day"]:
        if is_main_rest_day:
            p += 1
            k = K1 / ((1 + C * p) ** D)
            memory = memory * math.exp(-k)
@@ -345,12 +442,64 @@ def simulate_one_group(group: pd.DataFrame, M0: float, K1: float, C: float, D: f


@st.cache_data(show_spinner=False)
def simulate_memory(calendar: pd.DataFrame, M0: float, K1: float, C: float, D: float, R: float) -> pd.DataFrame:
    simulated = (
        calendar.sort_values(["분석단위ID", "date"])
        .groupby("분석단위ID", group_keys=False)
        .apply(lambda g: simulate_one_group(g, M0, K1, C, D, R))
    )
def simulate_memory(
    calendar: pd.DataFrame,
    M0: float,
    K1: float,
    C: float,
    D: float,
    R: float,
) -> pd.DataFrame:
    calendar = calendar.sort_values(["분석단위ID", "date"]).copy()

    if calendar.empty:
        raise ValueError("calendar가 비어 있습니다. 업로드 파일과 분석 기간을 확인하세요.")

    meta_cols = [
        "분석단위ID",
        "시도교육청코드",
        "시도교육청명",
        "행정표준코드",
        "학교명",
        "학교과정명",
        "학교표시명",
    ]

    missing_meta = [c for c in meta_cols if c not in calendar.columns]
    if missing_meta:
        raise ValueError(
            f"calendar에 필요한 메타 열이 없습니다: {missing_meta}. 현재 열 목록: {calendar.columns.tolist()}"
        )

    unit_meta = calendar[meta_cols].drop_duplicates("분석단위ID").copy()

    result_parts = []

    # pandas 3.x / Streamlit Cloud 환경에서 groupby.apply가 그룹 키 열을 제거할 수 있어
    # apply 대신 직접 반복해서 분석단위ID와 메타데이터를 확실히 보존한다.
    for unit_id, group in calendar.groupby("분석단위ID", sort=False, dropna=False):
        out = simulate_one_group(group.copy(), M0, K1, C, D, R)

        if "분석단위ID" not in out.columns:
            out["분석단위ID"] = unit_id

        result_parts.append(out)

    if not result_parts:
        raise ValueError("기억점수 계산 결과가 비어 있습니다. 업로드 파일과 분석 기간을 확인하세요.")

    simulated = pd.concat(result_parts, ignore_index=True)

    # 혹시 배포 환경에서 메타데이터 열이 누락되면 다시 붙인다.
    missing_after = [c for c in meta_cols if c not in simulated.columns]
    if missing_after:
        keep_cols = [c for c in simulated.columns if c not in meta_cols or c == "분석단위ID"]
        simulated = simulated[keep_cols].merge(
            unit_meta,
            on="분석단위ID",
            how="left",
        )

    return simulated


@@ -359,13 +508,42 @@ def simulate_memory(calendar: pd.DataFrame, M0: float, K1: float, C: float, D: f
# =========================================================

@st.cache_data(show_spinner=False)
def summarize_school(simulated: pd.DataFrame, vacation_check: pd.DataFrame, high_risk_threshold: float, min_vacation_days: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
def summarize_school(
    simulated: pd.DataFrame,
    vacation_check: pd.DataFrame,
    high_risk_threshold: float,
    min_vacation_days: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if "is_main_analysis_day" not in simulated.columns:
        raise ValueError(
            f"simulated 데이터에 is_main_analysis_day 열이 없습니다. 현재 열 목록: {simulated.columns.tolist()}"
        )

    analysis_data = simulated[simulated["is_main_analysis_day"]].copy()

    required_group_cols = [
        "시도교육청코드",
        "시도교육청명",
        "행정표준코드",
        "학교명",
        "학교과정명",
        "분석단위ID",
        "학교표시명",
    ]

    missing_cols = [c for c in required_group_cols if c not in analysis_data.columns]
    if missing_cols:
        raise ValueError(
            f"simulated 데이터에 필요한 열이 없습니다: {missing_cols}. 현재 열 목록: {analysis_data.columns.tolist()}"
        )

    if analysis_data.empty:
        raise ValueError(
            "방학을 제외한 분석 대상 날짜가 없습니다. 분석 기간, CSV 파일, 방학 판정 기준을 확인하세요."
        )

    school_summary = (
        analysis_data.groupby([
            "시도교육청코드", "시도교육청명", "행정표준코드", "학교명", "학교과정명", "분석단위ID", "학교표시명"
        ])
        analysis_data.groupby(required_group_cols)
        .agg(
            분석일수=("date", "nunique"),
            휴업일수=("is_main_rest_day", "sum"),
@@ -379,9 +557,16 @@ def summarize_school(simulated: pd.DataFrame, vacation_check: pd.DataFrame, high
        .reset_index()
    )

    school_summary["휴업일비율"] = school_summary["휴업일수"] / school_summary["분석일수"] * 100
    school_summary["고위험일비율"] = school_summary["고위험일수"] / school_summary["분석일수"] * 100
    school_summary["최종위험지수"] = 0.7 * school_summary["평균위험점수"] + 0.3 * school_summary["고위험일비율"]
    school_summary["휴업일비율"] = (
        school_summary["휴업일수"] / school_summary["분석일수"] * 100
    )
    school_summary["고위험일비율"] = (
        school_summary["고위험일수"] / school_summary["분석일수"] * 100
    )
    school_summary["최종위험지수"] = (
        0.7 * school_summary["평균위험점수"]
        + 0.3 * school_summary["고위험일비율"]
    )

    def risk_grade(score: float) -> str:
        if score >= 80:
@@ -402,9 +587,32 @@ def risk_grade(score: float) -> str:
        how="left",
    )

    school_summary["방학일수"] = school_summary["방학일수"].fillna(0)
    school_summary["추론방학일수"] = school_summary["추론방학일수"].fillna(0)

    core_summary = school_summary[school_summary["방학일수"] >= min_vacation_days].copy()

    if core_summary.empty:
        raise ValueError(
            "핵심 분석 대상이 0개입니다. 부분 데이터 테스트 중이라면 '핵심 분석 포함 최소 방학일수'를 0으로 낮추세요."
        )

    # 상대 비교 지표
    risk_mean = core_summary["최종위험지수"].mean()
    risk_std = core_summary["최종위험지수"].std()

    if pd.isna(risk_std) or risk_std == 0:
        core_summary["위험Z점수"] = 0.0
    else:
        core_summary["위험Z점수"] = (
            (core_summary["최종위험지수"] - risk_mean) / risk_std
        )

    core_summary["상대위험점수"] = 50 + 10 * core_summary["위험Z점수"]
    core_summary["위험백분위"] = core_summary["최종위험지수"].rank(pct=True) * 100
    core_summary["학교과정내_위험백분위"] = (
        core_summary.groupby("학교과정명")["최종위험지수"].rank(pct=True) * 100
    )

    def relative_grade(pct: float) -> str:
        if pct >= 95:
@@ -418,6 +626,7 @@ def relative_grade(pct: float) -> str:
        return "하위 20%"

    core_summary["상대위험등급"] = core_summary["위험백분위"].apply(relative_grade)
    school_summary = school_summary.sort_values("최종위험지수", ascending=False)
    core_summary = core_summary.sort_values("최종위험지수", ascending=False)

    return school_summary, core_summary
@@ -433,14 +642,35 @@ def make_memory_figure(one_school: pd.DataFrame, school_name: str) -> go.Figure:
    df["risk_plot"] = df["risk_score"].where(~df["is_vacation_day"], np.nan)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["memory_plot"], mode="lines", name="기억점수", connectgaps=False))
    fig.add_trace(go.Scatter(x=df["date"], y=df["risk_plot"], mode="lines", name="위험점수", connectgaps=False))
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["memory_plot"],
            mode="lines",
            name="기억점수",
            connectgaps=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["risk_plot"],
            mode="lines",
            name="위험점수",
            connectgaps=False,
        )
    )

    rest = df[df["is_main_rest_day"]]
    fig.add_trace(go.Scatter(
        x=rest["date"], y=rest["memory_score"], mode="markers", name="휴업일",
        marker=dict(size=5)
    ))
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
@@ -479,6 +709,7 @@ def make_calendar_html(one_school: pd.DataFrame, month: str) -> str:
    for day in range(1, last_day + 1):
        date_str = f"{year}-{mon:02d}-{day:02d}"
        row = by_date.get(date_str)

        if row is None:
            cells += f'<div class="calendar-day empty"><b>{day}</b></div>'
            continue
@@ -500,13 +731,16 @@ def make_calendar_html(one_school: pd.DataFrame, month: str) -> str:
        if event == "nan":
            event = ""

        safe_score = html.escape(score)
        safe_event = html.escape(event)

        cells += f"""
        <div class="calendar-day {cls}">
            <div class="day-top">
                <b>{day}</b>{badge}
            </div>
            <div class="score" title="{score}">{score}</div>
            <div class="event" title="{event}">{event or '-'}</div>
            <div class="score" title="{safe_score}">{safe_score}</div>
            <div class="event" title="{safe_event}">{safe_event or '-'}</div>
        </div>
        """

@@ -576,43 +810,61 @@ def to_excel_bytes(dfs: dict) -> bytes:
    R = st.number_input("수업일 회복률 R", value=0.30, min_value=0.0, max_value=1.0, step=0.05)
    high_risk_threshold = st.number_input("고위험 기준 점수", value=60.0, min_value=0.0, max_value=100.0, step=5.0)
    min_vacation_days = st.number_input("핵심 분석 포함 최소 방학일수", value=10, min_value=0, step=1)
    vacation_keyword_text = st.text_area(
        "추가 방학 판정 키워드",
        value="""동계 휴가
하계 휴가
겨울 휴가
여름 휴가
동계휴가
하계휴가""",
        help="학사일정에서 방학 대신 다른 표현을 쓰는 경우 한 줄에 하나씩 추가하세요. 예: 동계 휴가, 하계 휴가"
    )

    # 화면에는 보이지 않지만 방학 판정에는 적용됨
    vacation_keyword_text = DEFAULT_VACATION_KEYWORDS

    run_btn = st.button("🚀 분석 실행", type="primary", use_container_width=True)

if run_btn:
    if not uploaded_files:
        st.error("먼저 CSV 파일을 업로드하세요.")
    else:
        file_payload = [(f.getvalue(), f.name) for f in uploaded_files]
        with st.spinner("CSV 파일을 읽는 중..."):
            raw_df = load_uploaded_files(file_payload)
        with st.spinner("학교-과정-날짜 단위로 정리하는 중..."):
            daily_school = build_daily_school(raw_df, str(start_date), str(end_date), vacation_keyword_text)
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
        try:
            file_payload = [(f.getvalue(), f.name) for f in uploaded_files]

            with st.spinner("CSV 파일을 읽는 중..."):
                raw_df = load_uploaded_files(file_payload)

            with st.spinner("학교-과정-날짜 단위로 정리하는 중..."):
                daily_school = build_daily_school(
                    raw_df,
                    str(start_date),
                    str(end_date),
                    vacation_keyword_text,
                )

            with st.spinner("1년 전체 날짜표를 만드는 중..."):
                calendar, vacation_check = build_calendar(
                    daily_school,
                    str(start_date),
                    str(end_date),
                )

            with st.spinner("기억점수와 위험점수를 계산하는 중... 데이터가 크면 시간이 걸릴 수 있어요."):
                simulated = simulate_memory(calendar, M0, K1, C, D, R)

            with st.spinner("학교별 최종 위험지수를 요약하는 중..."):
                school_summary, core_summary = summarize_school(
                    simulated,
                    vacation_check,
                    high_risk_threshold,
                    min_vacation_days,
                )

            st.session_state["raw_df"] = raw_df
            st.session_state["daily_school"] = daily_school
            st.session_state["calendar"] = calendar
            st.session_state["vacation_check"] = vacation_check
            st.session_state["simulated"] = simulated
            st.session_state["school_summary"] = school_summary
            st.session_state["core_summary"] = core_summary
            st.success("분석 완료!")

        except Exception as e:
            st.error("분석 중 오류가 발생했습니다.")
            st.exception(e)
            st.stop()

if "core_summary" not in st.session_state:
    st.info("왼쪽에서 CSV 파일을 업로드하고 분석 실행 버튼을 누르세요.")
@@ -631,9 +883,16 @@ def to_excel_bytes(dfs: dict) -> bytes:
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("전체 학교-과정", f"{len(school_summary):,}")
col2.metric("핵심 분석 대상", f"{len(core_summary):,}")
col3.metric("제외", f"{excluded_count:,}", f"{excluded_count / max(len(school_summary), 1) * 100:.2f}%")
col3.metric(
    "제외",
    f"{excluded_count:,}",
    f"{excluded_count / max(len(school_summary), 1) * 100:.2f}%",
)
col4.metric("평균 위험지수", f"{core_summary['최종위험지수'].mean():.2f}")
col5.metric("휴업일-위험 상관", f"{core_summary['휴업일비율'].corr(core_summary['최종위험지수']):.3f}")
col5.metric(
    "휴업일-위험 상관",
    f"{core_summary['휴업일비율'].corr(core_summary['최종위험지수']):.3f}",
)

with st.expander("방학일수 데이터 점검", expanded=False):
    c1, c2, c3 = st.columns(3)
@@ -648,24 +907,65 @@ def to_excel_bytes(dfs: dict) -> bytes:

st.subheader("🔎 학교 검색 및 필터")
f1, f2, f3, f4 = st.columns([2.2, 1.2, 1.2, 1.4])

with f1:
    query = st.text_input("학교명 검색", placeholder="예: 대구여자고등학교")
    query = st.text_input("학교명 검색", placeholder="예: 부설, 대구여자고등학교")
with f2:
    regions = ["전체"] + sorted(core_summary["시도교육청명"].dropna().unique().tolist())
    region = st.selectbox("시도교육청", regions)
with f3:
    courses = ["전체"] + sorted(core_summary["학교과정명"].dropna().unique().tolist())
    course = st.selectbox("학교과정", courses)
with f4:
    sort_option = st.selectbox("정렬", ["최종위험지수 높은순", "최종위험지수 낮은순", "휴업일비율 높은순", "방학일수 많은순", "학교명 가나다순"])
    sort_option = st.selectbox(
        "정렬",
        [
            "최종위험지수 높은순",
            "최종위험지수 낮은순",
            "휴업일비율 높은순",
            "방학일수 많은순",
            "학교명 가나다순",
        ],
    )

filtered = core_summary.copy()

selected_from_search_id = None
if query:
    suggestion_df = core_summary[
        core_summary["학교명"].str.contains(query, case=False, na=False)
        | core_summary["학교표시명"].str.contains(query, case=False, na=False)
    ].copy()

    suggestion_df = suggestion_df.sort_values(["학교명", "학교과정명"]).head(50)

    if len(suggestion_df) > 0:
        suggestion_labels = (
            suggestion_df["학교표시명"]
            + " · "
            + suggestion_df["시도교육청명"]
            + " · 위험 "
            + suggestion_df["최종위험지수"].round(2).astype(str)
        ).tolist()

        selected_suggestion = st.selectbox(
            f"검색 추천 {len(suggestion_df):,}개 중 선택",
            ["선택 안 함"] + suggestion_labels,
            index=0,
        )

        if selected_suggestion != "선택 안 함":
            selected_idx = suggestion_labels.index(selected_suggestion)
            selected_from_search_id = suggestion_df.iloc[selected_idx]["분석단위ID"]
    else:
        st.caption("검색어가 포함된 학교가 없습니다.")

    mask = (
        filtered["학교명"].str.contains(query, case=False, na=False) |
        filtered["학교표시명"].str.contains(query, case=False, na=False)
        filtered["학교명"].str.contains(query, case=False, na=False)
        | filtered["학교표시명"].str.contains(query, case=False, na=False)
    )
    filtered = filtered[mask]

if region != "전체":
    filtered = filtered[filtered["시도교육청명"] == region]
if course != "전체":
@@ -691,27 +991,74 @@ def to_excel_bytes(dfs: dict) -> bytes:

region_summary = (
    core_summary.groupby("시도교육청명")
    .agg(학교수=("분석단위ID", "count"), 평균최종위험지수=("최종위험지수", "mean"), 평균휴업일비율=("휴업일비율", "mean"))
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
    .agg(학교수=("분석단위ID", "count"), 평균최종위험지수=("최종위험지수", "mean"), 평균휴업일비율=("휴업일비율", "mean"))
    .agg(
        학교수=("분석단위ID", "count"),
        평균최종위험지수=("최종위험지수", "mean"),
        평균휴업일비율=("휴업일비율", "mean"),
    )
    .reset_index()
    .sort_values("평균최종위험지수", ascending=False)
)

with g1:
    st.plotly_chart(px.bar(region_summary, x="평균최종위험지수", y="시도교육청명", orientation="h", title="시도교육청별 평균 위험지수"), use_container_width=True)
    st.plotly_chart(
        px.bar(
            region_summary,
            x="평균최종위험지수",
            y="시도교육청명",
            orientation="h",
            title="시도교육청별 평균 위험지수",
        ),
        use_container_width=True,
    )

with g2:
    st.plotly_chart(px.bar(course_summary, x="학교과정명", y="평균최종위험지수", title="학교과정별 평균 위험지수"), use_container_width=True)
    st.plotly_chart(
        px.bar(
            course_summary,
            x="학교과정명",
            y="평균최종위험지수",
            title="학교과정별 평균 위험지수",
        ),
        use_container_width=True,
    )

s1, s2 = st.columns(2)
with s1:
    st.plotly_chart(px.scatter(core_summary, x="휴업일비율", y="최종위험지수", color="학교과정명", hover_name="학교표시명", title="휴업일비율과 최종위험지수"), use_container_width=True)
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
    st.plotly_chart(px.scatter(core_summary, x="방학일수", y="최종위험지수", color="학교과정명", hover_name="학교표시명", title="방학일수와 최종위험지수"), use_container_width=True)
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
@@ -721,30 +1068,57 @@ def to_excel_bytes(dfs: dict) -> bytes:
st.caption(f"현재 필터 결과: {len(filtered):,}개 학교-과정")

show_cols = [
    "시도교육청명", "학교명", "학교과정명", "분석일수", "휴업일수", "수업일수", "휴업일비율",
    "평균위험점수", "고위험일비율", "최종위험지수", "위험등급", "방학일수", "상대위험등급"
    "시도교육청명",
    "학교명",
    "학교과정명",
    "분석일수",
    "휴업일수",
    "수업일수",
    "휴업일비율",
    "평균위험점수",
    "고위험일비율",
    "최종위험지수",
    "상대위험점수",
    "위험백분위",
    "학교과정내_위험백분위",
    "위험등급",
    "방학일수",
    "상대위험등급",
]
show_cols = [c for c in show_cols if c in filtered.columns]

st.dataframe(filtered[show_cols].head(500), use_container_width=True, height=360)

if len(filtered) == 0:
    st.warning("조건에 맞는 학교가 없습니다.")
    st.stop()

detail_options = filtered["학교표시명"].tolist()
selected_index = 0

if selected_from_search_id is not None:
    matched = filtered[filtered["분석단위ID"] == selected_from_search_id]
    if len(matched) > 0:
        selected_label_from_search = matched["학교표시명"].iloc[0]
        if selected_label_from_search in detail_options:
            selected_index = detail_options.index(selected_label_from_search)

selected_label = st.selectbox(
    "상세 분석을 볼 학교를 선택하세요.",
    filtered["학교표시명"].tolist(),
    index=0,
    detail_options,
    index=selected_index,
    key=f"detail_school_select_{selected_from_search_id or 'none'}_{len(filtered)}",
)

selected_row = filtered[filtered["학교표시명"] == selected_label].iloc[0]
selected_id = selected_row["분석단위ID"]
one_school = simulated[simulated["분석단위ID"] == selected_id].sort_values("date").copy()

st.subheader(f"📌 {selected_row['학교표시명']} 상세 분석")
d1, d2, d3, d4, d5 = st.columns(5)
d1.metric("최종위험지수", f"{selected_row['최종위험지수']:.2f}")
d2.metric("휴업일비율", f"{selected_row['휴업일비율']:.2f}%")
d3.metric("분석일수", f"{int(selected_row['분석일수']):,}일")
d2.metric("상대위험점수", f"{selected_row.get('상대위험점수', 50):.2f}")
d3.metric("휴업일비율", f"{selected_row['휴업일비율']:.2f}%")
d4.metric("방학일수", f"{int(selected_row['방학일수']):,}일")
d5.metric("고위험일비율", f"{selected_row['고위험일비율']:.2f}%")

@@ -757,25 +1131,37 @@ def to_excel_bytes(dfs: dict) -> bytes:

with st.expander("선택 학교 날짜별 데이터 보기", expanded=False):
    detail_cols = [
        "date", "is_vacation_day", "is_main_rest_day", "is_study_day", "memory_score", "risk_score",
        "p_value", "k_value", "calculation_type", "행사명_목록"
        "date",
        "is_vacation_day",
        "is_main_rest_day",
        "is_study_day",
        "memory_score",
        "risk_score",
        "p_value",
        "k_value",
        "calculation_type",
        "행사명_목록",
    ]
    detail_cols = [c for c in detail_cols if c in one_school.columns]
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

import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import datetime
import plotly.graph_objects as go

# 1. 페이지 설정
st.set_page_config(page_title="글로벌 매크로 & 시장 위험 경보 대시보드", layout="wide")

# API 설정 (st.secrets 사용)
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    fred = Fred(api_key=FRED_API_KEY)
except Exception:
    st.error("API Key를 찾을 수 없습니다.")
    st.stop()

# 2. 데이터 수집 엔진 (데이터 일관성 강화)
@st.cache_data(ttl=300) # 캐시를 5분으로 줄여 최신 데이터 강제 갱신 유도
def load_all_market_data(p_type):
    tickers = {'^KS11': 'KOSPI', '^IXIC': 'NASDAQ', '^GSPC': 'S_P500', '^RUT': 'RUSSELL2000', '^VIX': 'VIX'}
    df_market = pd.DataFrame()
    target_col = 'Adj Close' if p_type == "수정 종가 (Adj Close)" else 'Close'
    
    # 최근 2년 데이터를 확실하게 가져오도록 날짜 고정
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=730)).strftime('%Y-%m-%d')
    
    for ticker, name in tickers.items():
        try:
            # 기간 명시적 지정
            raw = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [col[0] for col in raw.columns]
                
                df_market[name] = raw[target_col] if target_col in raw.columns else raw['Close']
        except Exception as e:
            continue
                
    return df_market.sort_index().ffill().dropna()

# 데이터 로드
try:
    df_m = load_all_market_data("수정 종가 (Adj Close)" if "수정 종가" in st.sidebar.selectbox("적용 종가 선택", ["수정 종가 (Adj Close)", "일반 종가 (Close)"], key='p_type') else "Close")
    
    # FRED 데이터 수집
    us_10y = float(fred.get_series('DGS10').dropna().iloc[-1])
    core_cpi_series = fred.get_series('CPILFESL').dropna()
    core_cpi_yoy = float(((core_cpi_series.iloc[-1] - core_cpi_series.iloc[-13]) / core_cpi_series.iloc[-13]) * 100)
    sticky_cpi = float(fred.get_series('CORESTICKM159SFRBATL').dropna().iloc[-1])

    # 지표 계산
    ma_span = 50
    df_m['KOSPI_MA50'] = df_m['KOSPI'].rolling(window=ma_span).mean() # SMA 강제 적용으로 일관성 확보
    df_m['KOSPI_Disparity'] = (df_m['KOSPI'] / df_m['KOSPI_MA50']) * 100
    df_m = df_m.dropna()

    latest_date = df_m.index[-1].strftime('%Y-%m-%d')
    current_disparity = float(df_m['KOSPI_Disparity'].iloc[-1])
    current_vix = float(df_m['VIX'].iloc[-1])

    # 대시보드 출력
    st.title("🚨 글로벌 매크로 및 시장 위험 경보 시스템")
    st.write(f"**기준일: {latest_date}**")
    
    # 5대 지표 출력 (코드 간결화)
    cols = st.columns(5)
    metrics = [
        ("1. 코스피 이격도", f"{current_disparity:.1f}%"),
        ("2. 美 국채 10년물", f"{us_10y:.2f}%"),
        ("3. 美 근원 CPI", f"{core_cpi_yoy:.1f}%"),
        ("4. Sticky CPI", f"{sticky_cpi:.1f}%"),
        ("5. 미장 변동성", f"{current_vix:.1f}")
    ]
    for i, (label, val) in enumerate(metrics):
        cols[i].metric(label, val)

    # 정합성 검증표
    st.subheader("🔍 실시간 데이터 정합성 검증 표")
    st.dataframe(df_m[['KOSPI', 'KOSPI_MA50', 'KOSPI_Disparity']].tail(4).style.format("{:,.2f}"))

except Exception as e:
    st.error("데이터 로드 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import datetime
import plotly.graph_objects as go

# 1. 페이지 설정
st.set_page_config(page_title="글로벌 매크로 & 시장 위험 경보", layout="wide")

# 보안: secrets.toml에서 API 키 로드
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    fred = Fred(api_key=FRED_API_KEY)
except Exception:
    st.error("Secrets에 FRED_API_KEY가 설정되지 않았습니다.")
    st.stop()

# 2. 데이터 수집 엔진 (오차 제거를 위해 기간 명시)
@st.cache_data(ttl=300) # 5분마다 갱신 (실시간성 확보)
def load_all_market_data(p_type):
    # 오늘 날짜를 기준으로 기간을 고정하여 로컬/서버 오차 제거
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=730)).strftime('%Y-%m-%d')
    
    tickers = {'^KS11': 'KOSPI', '^IXIC': 'NASDAQ', '^GSPC': 'S_P500', '^RUT': 'RUSSELL2000', '^VIX': 'VIX'}
    df_market = pd.DataFrame()
    target_col = 'Adj Close' if p_type == "수정 종가 (Adj Close)" else 'Close'
    
    for ticker, name in tickers.items():
        try:
            # 명시적 기간 설정으로 오차 제거
            raw = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [col[0] for col in raw.columns]
                
                df_market[name] = raw[target_col] if target_col in raw.columns else raw['Close']
        except Exception:
            continue
                
    return df_market.sort_index().ffill().dropna()

# --- 데이터 로직 (사이드바 상태를 인자로 받음) ---
st.sidebar.header("⚙️ 계산 방식 조정")
ma_type = st.sidebar.selectbox("이동평균선 종류", ["단순 이동평균 (SMA)", "지수 이동평균 (EMA)"])
price_type = st.sidebar.selectbox("적용 종가", ["수정 종가 (Adj Close)", "일반 종가 (Close)"])

try:
    df_m = load_all_market_data(price_type)
    
    # 지표 계산 (공통 로직)
    if ma_type == "단순 이동평균 (SMA)":
        df_m['KOSPI_MA50'] = df_m['KOSPI'].rolling(window=50).mean()
    else:
        df_m['KOSPI_MA50'] = df_m['KOSPI'].ewm(span=50, adjust=False).mean()
    
    df_m['KOSPI_Disparity'] = (df_m['KOSPI'] / df_m['KOSPI_MA50']) * 100
    df_m = df_m.dropna()
    
    # FRED 데이터 (최신값 확보)
    us_10y = float(fred.get_series('DGS10').dropna().iloc[-1])
    core_cpi = float(fred.get_series('CPILFESL').dropna().iloc[-1]) # 최근값
    sticky_cpi = float(fred.get_series('CORESTICKM159SFRBATL').dropna().iloc[-1])
    
    # UI 출력 생략 (상단에 작성한 코드와 동일)
    st.write(f"최신 데이터: {df_m.index[-1].strftime('%Y-%m-%d')}")
    st.dataframe(df_m[['KOSPI', 'KOSPI_MA50', 'KOSPI_Disparity']].tail(3))

except Exception as e:
    st.error(f"데이터 처리 오류: {e}")

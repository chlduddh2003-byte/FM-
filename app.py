import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import datetime
import plotly.graph_objects as go

# 1. 페이지 설정
st.set_page_config(page_title="글로벌 매크로 대시보드", layout="wide")

st.markdown("""
    <style>
        .reportview-container { background: #0e1117; }
        .status-card { background-color: #171a23; border: 1px solid #262932; border-radius: 12px; padding: 20px; text-align: center; }
        .status-danger { border: 2px solid #e53e3e !important; background-color: #2d1a1a !important; }
        .status-info { border: 2px solid #3182ce !important; background-color: #1a242d !important; }
    </style>
""", unsafe_allow_html=True)

# API 설정
FRED_API_KEY = st.secrets["FRED_API_KEY"]
fred = Fred(api_key=FRED_API_KEY)

# 데이터 수집 엔진
@st.cache_data(ttl=600) 
def load_all_market_data():
    # 티커 정리 (KOSPI는 ^KS11 사용)
    tickers = {'^KS11': 'KOSPI', '^IXIC': 'NASDAQ', '^GSPC': 'S_P500', '^RUT': 'RUSSELL2000', '^VIX': 'VIX'}
    df_market = pd.DataFrame()
    
    for ticker, name in tickers.items():
        try:
            raw = yf.download(ticker, period="2y", progress=False)
            if not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [col[0] for col in raw.columns]
                df_market[name] = raw['Close']
        except Exception as e:
            st.error(f"{name} 수집 에러: {e}")
                
    return df_market.ffill().dropna()

try:
    df_m = load_all_market_data()
    
    # FRED 지표
    us_10y = float(fred.get_series('DGS10').dropna().iloc[-1])
    core_cpi_series = fred.get_series('CPILFESL').dropna()
    core_cpi_yoy = float(((core_cpi_series.iloc[-1] - core_cpi_series.iloc[-13]) / core_cpi_series.iloc[-13]) * 100)
    
    # 지표 계산
    df_m['KOSPI_MA50'] = df_m['KOSPI'].rolling(window=50).mean()
    df_m['KOSPI_Disparity'] = (df_m['KOSPI'] / df_m['KOSPI_MA50']) * 100
    
    latest_val = df_m.iloc[-1]
    
    st.title("🚨 글로벌 매크로 및 시장 위험 경보")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""<div class="status-card {'status-danger' if latest_val['KOSPI_Disparity'] > 105 else 'status-info'}">
            <h3>코스피 이격도</h3>
            <h2>{latest_val['KOSPI_Disparity']:.1f}%</h2>
        </div>""", unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""<div class="status-card">
            <h3>美 10년물 금리</h3>
            <h2>{us_10y:.2f}%</h2>
        </div>""", unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""<div class="status-card">
            <h3>美 근원 CPI</h3>
            <h2>{core_cpi_yoy:.1f}%</h2>
        </div>""", unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""<div class="status-card">
            <h3>VIX 지수</h3>
            <h2>{latest_val['VIX']:.1f}</h2>
        </div>""", unsafe_allow_html=True)

except Exception as e:
    st.error(f"데이터 로드 실패: {e}")

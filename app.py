import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import datetime
import plotly.graph_objects as go

# 1. 페이지 설정 및 다크 테마 커스텀 CSS 적용
st.set_page_config(page_title="글로벌 매크로 & 시장 위험 경보 대시보드", layout="wide")

st.markdown("""
    <style>
        .reportview-container { background: #0e1117; }
        .main .block-container { padding-top: 2rem; max-width: 1200px; }
        h1, h2, h3, p, span { font-family: 'Pretendard', -apple-system, sans-serif; }
        
        .status-card {
            background-color: #171a23;
            border: 1px solid #262932;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            margin-bottom: 15px;
        }
        .status-danger { border: 2px solid #e53e3e !important; background-color: #2d1a1a !important; }
        .status-warning { border: 2px solid #dd6b20 !important; background-color: #2d221a !important; }
        .status-success { border: 2px solid #1a2d20 !important; background-color: #1a2d20 !important; }
        .status-info { border: 2px solid #3182ce !important; background-color: #1a242d !important; }
        
        .memo-box {
            background-color: #1a1523;
            border-left: 5px solid #9f7aea;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 25px;
            font-weight: 500;
        }
    </style>
""", unsafe_allow_html=True)

# API 설정 (st.secrets 사용)
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    fred = Fred(api_key=FRED_API_KEY)
except Exception:
    st.error("API Key를 찾을 수 없습니다. .streamlit/secrets.toml 파일을 확인해주세요.")
    st.stop()

# 사이드바 옵션
st.sidebar.header("⚙️ 계산 방식 조정 (HTS 맞춤용)")
ma_type = st.sidebar.selectbox("이동평균선 종류 선택", ["단순 이동평균 (SMA)", "지수 이동평균 (EMA)"])
price_type = st.sidebar.selectbox("적용 종가 선택", ["수정 종가 (Adj Close)", "일반 종가 (Close)"])

# 2. 데이터 통합 수집 엔진
@st.cache_data(ttl=600) 
def load_all_market_data(p_type):
    tickers = {
        '^KS11': 'KOSPI', '^IXIC': 'NASDAQ', '^GSPC': 'S_P500', 
        '^RUT': 'RUSSELL2000', '^VIX': 'VIX',
        '005930.KS': 'Samsung', '000660.KS': 'Hynix'
    }
    df_market = pd.DataFrame()
    target_col = 'Adj Close' if p_type == "수정 종가 (Adj Close)" else 'Close'
    
    for ticker, name in tickers.items():
        try:
            raw = yf.download(ticker, period="2y", progress=False)
            if not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [col[0] for col in raw.columns]
                
                if target_col in raw.columns:
                    df_market[name] = raw[target_col]
                elif 'Close' in raw.columns:
                    df_market[name] = raw['Close']
        except Exception as e:
            st.error(f"{name} 수집 중 에러 발생: {e}")
                
    df_market = df_market.ffill().dropna()
    return df_market

# 데이터 호출 및 매크로 지표 결합
try:
    with st.spinner('데이터를 실시간으로 동기화 중입니다...'):
        df_m = load_all_market_data(price_type)
        
        # FRED 데이터 수집
        us_10y = float(fred.get_series('DGS10').dropna().iloc[-1])
        core_cpi_series = fred.get_series('CPILFESL').dropna()
        core_cpi_yoy = float(((core_cpi_series.iloc[-1] - core_cpi_series.iloc[-13]) / core_cpi_series.iloc[-13]) * 100)
        sticky_cpi = float(fred.get_series('CORESTICKM159SFRBATL').dropna().iloc[-1])

    # 50일선 이동평균 및 이격도 계산
    target_assets = ['KOSPI', 'Samsung', 'Hynix']
    for asset in target_assets:
        if ma_type == "단순 이동평균 (SMA)":
            df_m[f'{asset}_MA50'] = df_m[asset].rolling(window=50).mean()
        else:
            df_m[f'{asset}_MA50'] = df_m[asset].ewm(span=50, adjust=False).mean()
        
        df_m[f'{asset}_Disparity'] = (df_m[asset] / df_m[f'{asset}_MA50']) * 100

    # 최신 값 추출
    latest_date = df_m.index[-1].strftime('%Y-%m-%d')
    current_disparity = float(df_m['KOSPI_Disparity'].iloc[-1])
    current_vix = float(df_m['VIX'].iloc[-1])
    
    # 삼성/하이닉스 최신 데이터 (가격 및 이격도)
    s_price = float(df_m['Samsung'].iloc[-1])
    s_ma50 = float(df_m['Samsung_MA50'].iloc[-1])
    s_disparity = float(df_m['Samsung_Disparity'].iloc[-1])
    s_target_price = s_ma50 * 1.50 # 150% 도달가
    
    h_price = float(df_m['Hynix'].iloc[-1])
    h_ma50 = float(df_m['Hynix_MA50'].iloc[-1])
    h_disparity = float(df_m['Hynix_Disparity'].iloc[-1])
    h_target_price = h_ma50 * 1.75 # 175% 도달가

    # 3. UI 레이아웃
    st.title("🚨 글로벌 매크로 및 시장 위험 경보 시스템")
    st.caption(f"현재 동기화된 최신 영업일: {latest_date} | 적용 필터: {ma_type} / {price_type}")

    st.markdown("""
    <div class="memo-box">
        💡 <b>매매 멘탈 가이드:</b> 주가가 너무 튀어 계좌가 폭등할 때... 곧 조정이 옵니다. 아래 지표의 위험 한계선을 확인하고 브레이크를 잡으세요.
    </div>
    """, unsafe_allow_html=True)

    # 5대 핵심 지표 모니터링 (생략 - 기존 코드 유지)
    st.subheader("📌 5대 리스크 지표 현황")
    col1, col2, col3, col4, col5 = st.columns(5)
    # ... (기존 5대 지표 위젯 코드 동일) ...
    with col1:
        is_danger = current_disparity >= 130
        card_class = "status-card status-danger" if is_danger else ("status-card status-info" if current_disparity <= 105 else "status-card")
        status_lbl = "🚨 조정 급격 상승" if is_danger else ("🛒 분할 매수" if current_disparity <= 105 else "정상")
        st.markdown(f'<div class="{card_class}"><div style="font-size:14px; color:#a0aec0;">1. 코스피 이격도</div><div style="font-size:24px; font-weight:800; color:white; margin:5px 0;">{current_disparity:.1f}%</div><div style="font-size:12px;">{status_lbl}</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="status-card"><div style="font-size:14px; color:#a0aec0;">2. 美 국채 10년</div><div style="font-size:24px; font-weight:800; color:white; margin:5px 0;">{us_10y:.2f}%</div><div style="font-size:12px;">{"🚨 위험" if us_10y >= 5.0 else "정상"}</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="status-card"><div style="font-size:14px; color:#a0aec0;">3. 美 근원 CPI</div><div style="font-size:24px; font-weight:800; color:white; margin:5px 0;">{core_cpi_yoy:.1f}%</div><div style="font-size:12px;">{"🚨 위험" if core_cpi_yoy >= 3.0 else "정상"}</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="status-card"><div style="font-size:14px; color:#a0aec0;">4. Sticky CPI</div><div style="font-size:24px; font-weight:800; color:white; margin:5px 0;">{sticky_cpi:.1f}%</div><div style="font-size:12px;">{"🚨 위험" if sticky_cpi >= 3.5 else "정상"}</div></div>', unsafe_allow_html=True)
    with col5:
        st.markdown(f'<div class="status-card"><div style="font-size:14px; color:#a0aec0;">5. VIX 변동성</div><div style="font-size:24px; font-weight:800; color:white; margin:5px 0;">{current_vix:.1f}</div><div style="font-size:12px;">{"🔥 극단적 공포" if current_vix >= 30 else "정상"}</div></div>', unsafe_allow_html=True)

    # 삼성/하이닉스 섹션 추가
    st.subheader("📌 개별 종목 위험 신호 (삼성전자/SK하이닉스)")
    col_s1, col_s2 = st.columns(2)

    with col_s1:
        is_s_danger = s_disparity >= 150
        s_class = "status-card status-danger" if is_s_danger else "status-card"
        st.markdown(f"""
        <div class="{s_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">삼성전자</div>
            <div style="font-size:28px; font-weight:800; color:white; margin:5px 0;">{s_price:,.0f}원</div>
            <div style="font-size:16px; color:#cbd5e0; margin-bottom:10px;">이격도: <b>{s_disparity:.1f}%</b></div>
            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #262932;">
            <div style="font-size:13px; color:#a0aec0;">위험 도달가 (150%):</div>
            <div style="font-size:18px; font-weight:bold; color:#e53e3e;">{s_target_price:,.0f}원</div>
        </div>
        """, unsafe_allow_html=True)

    with col_s2:
        is_h_danger = h_disparity >= 175
        h_class = "status-card status-danger" if is_h_danger else "status-card"
        st.markdown(f"""
        <div class="{h_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">SK하이닉스</div>
            <div style="font-size:28px; font-weight:800; color:white; margin:5px 0;">{h_price:,.0f}원</div>
            <div style="font-size:16px; color:#cbd5e0; margin-bottom:10px;">이격도: <b>{h_disparity:.1f}%</b></div>
            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #262932;">
            <div style="font-size:13px; color:#a0aec0;">위험 도달가 (175%):</div>
            <div style="font-size:18px; font-weight:bold; color:#e53e3e;">{h_target_price:,.0f}원</div>
        </div>
        """, unsafe_allow_html=True)

    # 데이터 표
    st.subheader("🔍 실시간 데이터 정합성 검증")
    df_debug = df_m[['KOSPI', 'Samsung', 'Hynix', 'KOSPI_Disparity', 'Samsung_Disparity', 'Hynix_Disparity']].tail(4).copy()
    st.dataframe(df_debug.style.format("{:,.2f}"))

except Exception as main_err:
    st.error(f"대시보드 생성 중 오류가 발생했습니다: {main_err}")

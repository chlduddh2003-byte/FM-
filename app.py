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

# API 설정 (사용자님은 Secrets에서 불러옵니다)
fred = Fred(api_key=st.secrets["FRED_API_KEY"])

# 사이드바 옵션
st.sidebar.header("⚙️ 계산 방식 조정 (HTS 맞춤용)")
ma_type = st.sidebar.selectbox("이동평균선 종류 선택", ["단순 이동평균 (SMA)", "지수 이동평균 (EMA)"])
price_type = st.sidebar.selectbox("적용 종가 선택", ["수정 종가 (Adj Close)", "일반 종가 (Close)"])

# 2. 데이터 통합 수집 엔진 (수치 오류 수정 완료)
@st.cache_data(ttl=600) 
def load_all_market_data(p_type):
    # KOSPI 티커 확인 (야후 파이낸스에서 ^KS11은 지수용입니다)
    tickers = {'^KS11': 'KOSPI', '^IXIC': 'NASDAQ', '^GSPC': 'S_P500', '^RUT': 'RUSSELL2000', '^VIX': 'VIX'}
    df_market = pd.DataFrame()
    target_col = 'Adj Close' if p_type == "수정 종가 (Adj Close)" else 'Close'
    
    for ticker, name in tickers.items():
        try:
            # period를 길게 잡고 데이터 안정성 확보
            raw = yf.download(ticker, period="2y", progress=False)
            if not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [col[0] for col in raw.columns]
                
                # 데이터 유효성 체크
                if target_col in raw.columns:
                    df_market[name] = raw[target_col]
                else:
                    df_market[name] = raw['Close']
        except Exception as e:
            st.error(f"{name} 수집 중 에러 발생: {e}")
                
    return df_market.ffill().dropna()

# 데이터 호출
try:
    with st.spinner('데이터를 실시간으로 동기화 중입니다...'):
        df_m = load_all_market_data(price_type)
        
        # FRED 데이터 수집
        us_10y = float(fred.get_series('DGS10').dropna().iloc[-1])
        core_cpi_series = fred.get_series('CPILFESL').dropna()
        core_cpi_yoy = float(((core_cpi_series.iloc[-1] - core_cpi_series.iloc[-13]) / core_cpi_series.iloc[-13]) * 100)
        sticky_cpi = float(fred.get_series('CORESTICKM159SFRBATL').dropna().iloc[-1])

    if ma_type == "단순 이동평균 (SMA)":
        df_m['KOSPI_MA50'] = df_m['KOSPI'].rolling(window=50).mean()
    else:
        df_m['KOSPI_MA50'] = df_m['KOSPI'].ewm(span=50, adjust=False).mean()

    df_m['KOSPI_Disparity'] = (df_m['KOSPI'] / df_m['KOSPI_MA50']) * 100
    df_m = df_m.dropna()

    latest_date = df_m.index[-1].strftime('%Y-%m-%d')
    current_disparity = float(df_m['KOSPI_Disparity'].iloc[-1])
    current_kospi = float(df_m['KOSPI'].iloc[-1]) # 코스피 수치 변수 추가
    current_vix = float(df_m['VIX'].iloc[-1])

    # 3. 메인 UI (원본 그대로 유지)
    st.title("🚨 글로벌 매크로 및 시장 위험 경보 시스템")
    st.caption(f"현재 동기화된 최신 영업일: {latest_date} | 적용 필터: {ma_type} / {price_type}")

    st.markdown("""
    <div class="memo-box">
        💡 <b>매매 멘탈 가이드:</b> 보통 주가가 너무 튀어서 계좌가 폭등하고 내 기분이 졸라 좋을 때... 하루 이틀 있으면 여지없이 폭락조정이 옵니다. 항상 아래 지표의 위험 한계선을 확인하고 브레이크를 잡으세요.
    </div>
    """, unsafe_allow_html=True)

    st.subheader("📌 5대 리스크 지표 현황")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        is_danger = current_disparity >= 130
        card_class = "status-card status-danger" if is_danger else ("status-card status-info" if current_disparity <= 105 else "status-card")
        status_lbl = "🚨 조정 급격 상승 (일부 현금화)" if is_danger else ("🛒 분할 매수 구간" if current_disparity <= 105 else "정상 범위")
        st.markdown(f"""
        <div class="{card_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">1. 코스피 이격도 ({current_kospi:,.0f})</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{current_disparity:.1f}%</div>
            <div style="font-size:12px; font-weight:bold; color:#cbd5e0;">{status_lbl}</div>
        </div>
        """, unsafe_allow_html=True)

    # 나머지 col2 ~ col5 UI도 기존 사용자님 원본 유지
    with col2:
        is_danger = us_10y >= 5.0
        st.markdown(f"""<div class="status-card {'status-danger' if is_danger else ''}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">2. 美 국채 10년물</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{us_10y:.2f}%</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="status-card {'status-danger' if core_cpi_yoy >= 3.0 else ''}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">3. 美 근원 CPI</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{core_cpi_yoy:.1f}%</div>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""<div class="status-card {'status-danger' if sticky_cpi >= 3.5 else ''}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">4. Sticky CPI</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{sticky_cpi:.1f}%</div>
        </div>""", unsafe_allow_html=True)
    with col5:
        st.markdown(f"""<div class="status-card {'status-success' if current_vix >= 30 else ''}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">5. 미장 변동성</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{current_vix:.1f}</div>
        </div>""", unsafe_allow_html=True)

    # 데이터 표 및 차트 (원본 유지)
    st.markdown("### 🔍 실시간 데이터 정합성 검증 표")
    st.dataframe(df_m[['KOSPI', 'KOSPI_MA50', 'KOSPI_Disparity']].tail(3).style.format("{:,.2f}"))

    st.subheader("🔄 시장 확산성 다이버전스 체크")
    df_recent = df_m.tail(60).copy()
    df_normalized = (df_recent / df_recent.iloc[0]) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_normalized.index, y=df_normalized['NASDAQ'], name='나스닥'))
    fig.add_trace(go.Scatter(x=df_normalized.index, y=df_normalized['S_P500'], name='S&P 500'))
    fig.update_layout(template='plotly_dark', paper_bgcolor='#171a23', height=300)
    st.plotly_chart(fig, use_container_width=True)

except Exception as main_err:
    st.error(f"대시보드 생성 중 오류: {main_err}")

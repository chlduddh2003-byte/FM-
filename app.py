import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
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

# API 설정 (스트림릿 Secrets 비밀금고 연동)
FRED_API_KEY = st.secrets["FRED_API_KEY"]
fred = Fred(api_key=FRED_API_KEY)

# 사이드바 옵션 (HTS와 수치 맞추기용 필터)
st.sidebar.header("⚙️ 계산 방식 조정 (HTS 맞춤용)")
ma_type = st.sidebar.selectbox("이동평균선 종류 선택", ["단순 이동평균 (SMA)", "지수 이동평균 (EMA)"])

# 2. 데이터 통합 수집 엔진
@st.cache_data(ttl=600) 
def load_all_market_data():
    # 미장 및 변동성 지수는 야후 파이낸스 사용
    tickers = {'^IXIC': 'NASDAQ', '^GSPC': 'S_P500', '^RUT': 'RUSSELL2000', '^VIX': 'VIX'}
    df_market = pd.DataFrame()
    
    for ticker, name in tickers.items():
        try:
            raw = yf.download(ticker, period="2y", progress=False)
            if not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = [col[0] for col in raw.columns]
                df_market[name] = raw['Close']
        except Exception as e:
            st.error(f"{name} 수집 중 에러 발생: {e}")
            
    # ★ 코스피는 한국거래소 데이터셋(FinanceDataReader)으로 정확하게 수집
    try:
        kospi_raw = fdr.DataReader('KS11', datetime.datetime.now() - datetime.timedelta(days=730))
        if not kospi_raw.empty:
            df_market['KOSPI'] = kospi_raw['Close']
    except Exception as e:
        st.error(f"코스피 수집 중 에러 발생: {e}")
                
    df_market = df_market.ffill().dropna()
    return df_market

try:
    with st.spinner('데이터를 실시간으로 동기화 중입니다...'):
        df_m = load_all_market_data()
        
        # FRED 데이터 수집
        us_10y = float(fred.get_series('DGS10').dropna().iloc[-1])
        core_cpi_series = fred.get_series('CPILFESL').dropna()
        core_cpi_yoy = float(((core_cpi_series.iloc[-1] - core_cpi_series.iloc[-13]) / core_cpi_series.iloc[-13]) * 100)
        sticky_cpi = float(fred.get_series('CORESTICKM159SFRBATL').dropna().iloc[-1])

    # 이동평균선 계산
    if ma_type == "단순 이동평균 (SMA)":
        df_m['KOSPI_MA50'] = df_m['KOSPI'].rolling(window=50).mean()
    else:
        df_m['KOSPI_MA50'] = df_m['KOSPI'].ewm(span=50, adjust=False).mean()

    df_m['KOSPI_Disparity'] = (df_m['KOSPI'] / df_m['KOSPI_MA50']) * 100
    df_m = df_m.dropna()

    latest_date = df_m.index[-1].strftime('%Y-%m-%d')
    current_kospi = float(df_m['KOSPI'].iloc[-1])
    current_disparity = float(df_m['KOSPI_Disparity'].iloc[-1])
    current_vix = float(df_m['VIX'].iloc[-1])

    # 3. 메인 대시보드 UI 레이아웃
    st.title("🚨 글로벌 매크로 및 시장 위험 경보 시스템")
    st.caption(f"현재 동기화된 최신 영업일: {latest_date} | 적용 필터: {ma_type}")

    st.markdown("""
    <div class="memo-box">
        💡 <b>매매 멘탈 가이드:</b> 보통 주가가 너무 튀어서 계좌가 폭등하고 내 기분이 좋을 때... 하루 이틀 있으면 여지없이 폭락조정이 옵니다. 항상 아래 지표의 위험 한계선을 확인하고 브레이크를 잡으세요.
    </div>
    """, unsafe_allow_html=True)

    # 4. 5대 핵심 지표 모니터링 현황
    st.subheader("📌 5대 리스크 지표 현황")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        is_danger = current_disparity >= 106  # 통상 코스피는 105~106% 이상이면 단기 과열권입니다.
        card_class = "status-card status-danger" if is_danger else ("status-card status-info" if current_disparity <= 95 else "status-card")
        status_lbl = "🚨 과열 구간 (일부 현금화)" if is_danger else ("🛒 분할 매수 구간" if current_disparity <= 95 else "정상 범위")
        st.markdown(f"""
        <div class="{card_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">1. 코스피 이격도 ({current_kospi:,.1f})</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{current_disparity:.1f}%</div>
            <div style="font-size:12px; font-weight:bold; color:#cbd5e0;">{status_lbl}</div>
            <div style="font-size:11px; color:#718096; margin-top:5px;">기준선: 106% 이상 과열 / 95% 이하 과매도</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        is_danger = us_10y >= 5.0
        card_class = "status-card status-danger" if is_danger else "status-card"
        status_lbl = "🚨 상승장 끝 (위험)" if is_danger else "정상 범위"
        st.markdown(f"""
        <div class="{card_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">2. 美 국채 10년물</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{us_10y:.2f}%</div>
            <div style="font-size:12px; font-weight:bold; color:#cbd5e0;">{status_lbl}</div>
            <div style="font-size:11px; color:#718096; margin-top:5px;">기준선: 5.0% 이상 종료</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        is_danger = core_cpi_yoy >= 3.0
        card_class = "status-card status-danger" if is_danger else "status-card"
        status_lbl = "🚨 끝물근처 / 하락징후" if is_danger else "정상 범위"
        st.markdown(f"""
        <div class="{card_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">3. 美 근원 CPI (YoY)</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{core_cpi_yoy:.1f}%</div>
            <div style="font-size:12px; font-weight:bold; color:#cbd5e0;">{status_lbl}</div>
            <div style="font-size:11px; color:#718096; margin-top:5px;">기준선: 3.0% 이상 위험</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        is_danger = sticky_cpi >= 3.5
        card_class = "status-card status-danger" if is_danger else "status-card"
        status_lbl = "🚨 끝물근처 / 하락징후" if is_danger else "정상 범위"
        st.markdown(f"""
        <div class="{card_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">4. Sticky CPI (YoY)</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{sticky_cpi:.1f}%</div>
            <div style="font-size:12px; font-weight:bold; color:#cbd5e0;">{status_lbl}</div>
            <div style="font-size:11px; color:#718096; margin-top:5px;">기준선: 3.5% 이상 위험</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        is_fng_extreme_fear = current_vix >= 30
        card_class = "status-card status-success" if is_fng_extreme_fear else "status-card"
        status_lbl = "🔥 극단적 공포 (분할몰빵!)" if is_fng_extreme_fear else "시장 관망 가능"
        st.markdown(f"""
        <div class="{card_class}">
            <div style="font-size:14px; color:#a0aec0; font-weight:bold;">5. 미장 변동성 (VIX)</div>
            <div style="font-size:32px; font-weight:800; color:white; margin:10px 0;">{current_vix:.1f}</div>
            <div style="font-size:12px; font-weight:bold; color:#cbd5e0;">{status_lbl}</div>
            <div style="font-size:11px; color:#718096; margin-top:5px;"><a href="https://edition.cnn.com/markets/fear-and-greed" target="_blank" style="color:#4299e1; text-decoration:none;">🔗 CNN 공포지수 직접확인</a></div>
        </div>
        """, unsafe_allow_html=True)

    # 데이터 정합성 검증 표
    st.markdown("### 🔍 실시간 데이터 정합성 검증 표")
    df_debug = df_m[['KOSPI', 'KOSPI_MA50', 'KOSPI_Disparity']].tail(4).copy()
    df_debug.columns = ['코스피 종가(KRX)', '앱이 계산한 50일선', '최종 이격도(%)']
    st.dataframe(df_debug.style.format("{:,.2f}"))

    # 5. 시장 확산성 다이버전스 차트
    st.markdown("---")
    st.subheader("🔄 시장 확산성 다이버전스 체크 (끝물 필터링)")
    df_recent = df_m.tail(60).copy()
    df_normalized = (df_recent / df_recent.iloc[0]) * 100

    fig_div = go.Figure()
    fig_div.add_trace(go.Scatter(x=df_normalized.index, y=df_normalized['NASDAQ'], mode='lines', name='나스닥', line=dict(color='#3182ce', width=2.5)))
    fig_div.add_trace(go.Scatter(x=df_normalized.index, y=df_normalized['S_P500'], mode='lines', name='S&P 500', line=dict(color='#e53e3e', width=1.5, dash='dash')))
    fig_div.add_trace(go.Scatter(x=df_normalized.index, y=df_normalized['RUSSELL2000'], mode='lines', name='러셀 2000', line=dict(color='#38a169', width=1.5, dash='dot')))

    fig_div.update_layout(template='plotly_dark', paper_bgcolor='#171a23', plot_bgcolor='#171a23', height=350, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_div, use_container_width=True)

except Exception as main_err:
    st.error(f"대시보드 생성 중 오류가 발생했습니다: {main_err}")

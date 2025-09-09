# app.py

import streamlit as st
import polars as pl
import yfinance as yf
from requests_html import HTMLSession
import plotly.graph_objects as go

# --- 페이지 설정 ---
st.set_page_config(page_title="Stock Analysis Dashboard", page_icon="📊", layout="wide")

# --- 기능 2: 즐겨찾기 시스템 초기화 ---
# st.session_state는 앱이 재실행되어도 유지되는 변수들의 저장소입니다.
if 'favorites' not in st.session_state:
    # 앱이 처음 실행될 때 기본 즐겨찾기 목록을 만들어줍니다.
    st.session_state.favorites = ["MSFT", "AAPL", "GOOG", "NVDA"]

# --- 데이터 로딩 함수들 ---

@st.cache_data(ttl=600)
def fetch_yahoo_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # --- 기능 1 수정: 더 많은 과거 데이터 로딩 ---
        # MA200을 차트 시작부터 그리려면 최소 1년 + 200일의 데이터가 필요합니다.
        # 넉넉하게 2년치 데이터를 불러옵니다.
        hist_pd = ticker.history(period="2y", interval="1d")
        if hist_pd.empty:
            return None

        hist_pl = pl.from_pandas(hist_pd.reset_index())

        delta = hist_pl["Close"].diff()
        gain = delta.clip(lower_bound=0).fill_null(0)
        loss = -delta.clip(upper_bound=0).fill_null(0)
        avg_gain = gain.ewm_mean(span=14, adjust=False)
        avg_loss = loss.ewm_mean(span=14, adjust=False)
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        hist_pl = hist_pl.with_columns([
            pl.col("Close").rolling_mean(window_size=50).alias("MA50"),
            pl.col("Close").rolling_mean(window_size=200).alias("MA200"),
            rsi.alias("RSI")
        ])

        # --- 기능 1 수정: 계산은 긴 데이터로, 표시는 최근 1년치만 ---
        # 모든 계산이 끝난 후, 최근 1년(거래일 기준 약 252일)의 데이터만 잘라서 반환합니다.
        return hist_pl.tail(252)

    except Exception as e:
        st.error(f"Yahoo Finance 데이터 로딩 중 오류 발생: {e}")
        return None

@st.cache_data(ttl=600)
def scrape_finviz_data(ticker_symbol):
    # (이전과 동일)
    try:
        session = HTMLSession()
        url = f"https://finviz.com/quote.ashx?t={ticker_symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = session.get(url, headers=headers)
        snapshot_data = r.html.find('td.snapshot-td2')
        data_map = {snapshot_data[i].text: snapshot_data[i+1].text for i in range(0, len(snapshot_data), 2)}
        metrics = {name: data_map.get(name, "N/A") for name in ["P/E", "P/S", "P/B", "ROE", "Target Price"]}
        return metrics
    except Exception as e:
        st.error(f"Finviz 데이터 스크레이핑 중 오류 발생: {e}")
        return {name: "Error" for name in ["P/E", "P/S", "P/B", "ROE", "Target Price"]}

# --- 대시보드 UI 구성 ---

st.title("📊 실시간 주식 분석 대시보드")

# --- 기능 2: 즐겨찾기 사이드바 ---
st.sidebar.header("⭐ 즐겨찾기")
# st.session_state.favorites를 순회하며 각 종목에 대한 버튼을 만듭니다.
for fav_ticker in st.session_state.favorites:
    # 각 버튼이 클릭되면, 해당 종목으로 검색을 실행합니다.
    if st.sidebar.button(fav_ticker, key=f"fav_{fav_ticker}"):
        # st.session_state에 현재 조회할 종목을 저장하여, form 제출 로직과 연동합니다.
        st.session_state.ticker_to_search = fav_ticker
        st.session_state.run_search = True

st.sidebar.header("조회 설정")
# --- 기능 3: 엔터 키 검색을 위한 st.form ---
with st.sidebar.form(key="search_form"):
    ticker_input = st.text_input("종목 코드를 입력하세요", "MSFT").upper()
    # 버튼은 st.form_submit_button으로 변경해야 form과 연동됩니다.
    run_button = st.form_submit_button("분석 실행")

# form이 제출되었는지(버튼 클릭 또는 엔터) 확인합니다.
if run_button:
    st.session_state.ticker_to_search = ticker_input
    st.session_state.run_search = True

# 즐겨찾기 버튼 클릭 또는 form 제출 시 분석을 실행합니다.
if st.session_state.get("run_search", False):
    ticker_to_display = st.session_state.ticker_to_search
    
    with st.spinner(f"{ticker_to_display}의 데이터를 분석하는 중입니다..."):
        stock_data = fetch_yahoo_data(ticker_to_display)
        finviz_data = scrape_finviz_data(ticker_to_display)

    if stock_data is not None and not stock_data.is_empty():
        # --- 기능 2: 즐겨찾기 추가 버튼 ---
        # 현재 조회한 종목이 즐겨찾기에 없다면, 추가 버튼을 보여줍니다.
        if ticker_to_display not in st.session_state.favorites:
            if st.button(f"⭐ {ticker_to_display} 즐겨찾기에 추가"):
                st.session_state.favorites.append(ticker_to_display)
                st.success(f"'{ticker_to_display}'를 즐겨찾기에 추가했습니다!")
                # st.rerun()을 호출하여 사이드바를 즉시 새로고침합니다.
                st.rerun()
        
        st.header(f"[{ticker_to_display}] 주요 지표")
        
        latest_row = stock_data.row(-1, named=True)
        prev_row = stock_data.row(-2, named=True)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("현재가", f"${latest_row['Close']:.2f}", f"{latest_row['Close'] - prev_row['Close']:.2f}")
        col2.metric("P/E", finviz_data.get("P/E", "N/A"))
        col3.metric("ROE", finviz_data.get("ROE", "N/A"))
        col4.metric("RSI(14)", f"{latest_row['RSI']:.2f}" if latest_row['RSI'] is not None else "N/A")

        st.markdown("---")
        
        st.header("주가 및 이동평균선")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=stock_data["Date"], y=stock_data["Close"], mode='lines', name='종가'))
        fig.add_trace(go.Scatter(x=stock_data["Date"], y=stock_data["MA50"], mode='lines', name='MA50', line=dict(color='orange')))
        fig.add_trace(go.Scatter(x=stock_data["Date"], y=stock_data["MA200"], mode='lines', name='MA200', line=dict(color='purple')))
        fig.update_layout(title=f'{ticker_to_display} 주가 차트', xaxis_title='날짜', yaxis_title='가격 (USD)')
        st.plotly_chart(fig, use_container_width=True)
        
        st.header("상세 데이터")
        st.dataframe(stock_data.tail(10))

    else:
        st.error(f"'{ticker_to_display}'에 대한 데이터를 찾을 수 없거나 데이터가 비어있습니다. 종목 코드를 확인해주세요.")
    
    # 분석이 끝나면 run_search 상태를 초기화합니다.
    st.session_state.run_search = False

else:
    st.info("사이드바에서 종목 코드를 입력하고 '분석 실행' 버튼을 누르거나 즐겨찾기를 클릭해주세요.")
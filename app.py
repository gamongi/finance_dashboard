# app.py

import streamlit as st
import polars as pl
import yfinance as yf
from requests_html import HTMLSession
import plotly.graph_objects as go
from github import Github, UnknownObjectException
import json

# --- 페이지 설정 및 UI 커스텀 CSS ---
st.set_page_config(page_title="Stock Dashboard", page_icon="📊", layout="wide")

st.markdown("""
<style>
/* 전체 앱의 여백을 줄여 공간 활용도 높임 */
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    padding-left: 3rem;
    padding-right: 3rem;
}
/* 사이드바 즐겨찾기 버튼 스타일 */
div[data-testid="stSidebarNav"] + div div[data-testid="stButton"] > button {
    border: none; background-color: transparent; text-align: left;
    padding-left: 0; color: inherit; font-size: 1.1em;
}
div[data-testid="stSidebarNav"] + div div[data-testid="stButton"] > button:hover {
    color: #FF4B4B; background-color: transparent;
}
/* 검색창 Form 배경 투명화 */
form[data-testid="stForm"] {
    background: transparent;
    border: none;
    padding: 0;
}
/* 검색창 입력 필드 스타일 */
div[data-testid="stTextInput"] > div > div > input {
    background-color: rgba(230, 230, 230, 0.5); /* 반투명 회색 */
    border: none;
}
/* 메인 헤더의 가격/등락률 스타일 */
.stock-price { font-size: 2em; font-weight: bold; }
.stock-delta-positive { font-size: 1.2em; color: #FF4B4B; }
.stock-delta-negative { font-size: 1.2em; color: #4B9BFF; }
</style>
""", unsafe_allow_html=True)

# --- GitHub 연동 및 데이터 로딩/처리 함수들 (이전과 거의 동일) ---
FAVORITES_FILE_PATH = "favorites.json"

try:
    g = Github(st.secrets["GITHUB_TOKEN"])
    repo = g.get_repo(st.secrets["GITHUB_REPO"])
except Exception as e:
    st.sidebar.error("GitHub 인증 실패. Secrets를 확인하세요.")
    st.stop()

@st.cache_data(ttl=60)
def read_favorites_from_github():
    try:
        content = repo.get_contents(FAVORITES_FILE_PATH)
        return json.loads(content.decoded_content.decode())
    except UnknownObjectException:
        return ["MSFT", "AAPL", "GOOG", "NVDA"]
    except Exception as e:
        st.sidebar.error(f"즐겨찾기 로딩 실패: {e}")
        return []

def write_favorites_to_github(favorites_list):
    try:
        contents = json.dumps(sorted(list(set(favorites_list))), indent=4)
        try:
            file = repo.get_contents(FAVORITES_FILE_PATH)
            repo.update_file(FAVORITES_FILE_PATH, "Update favorites", contents, file.sha)
        except UnknownObjectException:
            repo.create_file(FAVORITES_FILE_PATH, "Create favorites", contents)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"즐겨찾기 저장 실패: {e}")
        return False

@st.cache_data(ttl=600)
def fetch_full_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        # CAGR(5y) 계산을 위해 6년치 데이터 로딩
        hist_pd = ticker.history(period="6y", interval="1d")
        if hist_pd.empty: return None
        financials = ticker.financials
        return {"info": info, "history": hist_pd, "financials": financials}
    except Exception as e:
        st.error(f"데이터 로딩 중 오류 발생: {e}")
        return None

def process_data(full_data):
    hist_pl = pl.from_pandas(full_data["history"].reset_index())
    hist_pl = hist_pl.with_columns([
        pl.col("Close").rolling_mean(window_size=50).alias("MA50"),
        pl.col("Close").rolling_mean(window_size=200).alias("MA200"),
    ]).drop_nulls()
    view_data = hist_pl.tail(252)
    max_point = view_data.filter(pl.col("High") == view_data["High"].max())
    min_point = view_data.filter(pl.col("Low") == view_data["Low"].min())
    cross_signal = pl.when(pl.col("MA50") > pl.col("MA200")).then(1).otherwise(-1)
    cross_events = view_data.with_columns(cross_signal.diff().alias("cross")).filter(pl.col("cross") != 0)
    financials_pl = pl.from_pandas(full_data["financials"].transpose().reset_index())
    cagr = {}
    for col_name_eng, col_name_kor in [("Total Revenue", "매출"), ("Net Income", "순이익")]:
        if col_name_eng in financials_pl.columns and financials_pl[col_name_eng].drop_nulls().len() > 1:
            series = financials_pl[col_name_eng].drop_nulls()
            start_val = series.last()
            end_val = series.first()
            if start_val and end_val and start_val > 0:
                num_years = series.len() - 1
                if num_years > 0:
                    cagr_val = ((end_val / start_val) ** (1 / num_years)) - 1
                    cagr[col_name_kor] = f"{cagr_val:.2%}"
    return {"history": view_data, "max_point": max_point, "min_point": min_point, "cross_events": cross_events, "cagr": cagr}

@st.cache_data(ttl=600)
def scrape_finviz_data(ticker_symbol):
    try:
        session = HTMLSession()
        url = f"https://finviz.com/quote.ashx?t={ticker_symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = session.get(url, headers=headers)
        snapshot_data = r.html.find('td.snapshot-td2')
        data_map = {snapshot_data[i].text: snapshot_data[i+1].text for i in range(0, len(snapshot_data), 2)}
        metrics_to_get = ["P/E", "PEG"]
        metrics = {name: data_map.get(name, "N/A") for name in metrics_to_get}
        
        # RSI는 yfinance 데이터로 직접 계산
        hist = yf.Ticker(ticker_symbol).history(period="1mo")
        delta = hist['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        metrics['RSI'] = 100 - (100 / (1 + rs)).iloc[-1]
        
        return metrics
    except Exception:
        return {name: "Error" for name in ["P/E", "PEG", "RSI"]}

# --- UI 렌더링 시작 ---

# 1. 사이드바 (즐겨찾기 내비게이션)
if 'favorites' not in st.session_state:
    st.session_state.favorites = read_favorites_from_github()
for fav_ticker in st.session_state.favorites:
    if st.sidebar.button(fav_ticker, key=f"fav_{fav_ticker}"):
        st.session_state.ticker_to_search = fav_ticker
        st.session_state.run_search = True

# 2. 전역 검색창 (최상단 우측)
_, search_col = st.columns([0.7, 0.3])
with search_col:
    with st.form(key="search_form"):
        ticker_input = st.text_input("Search", label_visibility="collapsed", placeholder="종목 검색...")
        run_button = st.form_submit_button("🔍")

if run_button:
    st.session_state.ticker_to_search = ticker_input
    st.session_state.run_search = True

# 3. 분석 실행 로직
if "ticker_to_search" not in st.session_state:
    st.session_state.ticker_to_search = "MSFT"
if "run_search" not in st.session_state:
    st.session_state.run_search = True

if st.session_state.get("run_search", False):
    ticker = st.session_state.ticker_to_search
    full_data = fetch_full_data(ticker)
    
    if full_data and not full_data["history"].empty:
        processed_data = process_data(full_data)
        finviz_data = scrape_finviz_data(ticker)
        
        # 4. 동적 헤더
        info = full_data["info"]
        price_info = full_data["history"].iloc[-1]
        price = price_info['Close']
        delta = price - full_data["history"].iloc[-2]['Close']
        delta_pct = (delta / full_data["history"].iloc[-2]['Close']) * 100
        delta_color = "positive" if delta >= 0 else "negative"

        name_col, price_col, star_col = st.columns([0.6, 0.3, 0.1])
        with name_col:
            st.markdown(f"""
            <span style="font-size: 2.2em; font-weight: bold;">{info.get('longName', ticker)}</span>
            <span style="font-size: 1.2em; color: grey;">{ticker}</span>
            """, unsafe_allow_html=True)
        with price_col:
            st.markdown(f"""
            <span class="stock-price">${price:,.2f}</span>
            <span class="stock-delta-{delta_color}">({delta:+.2f} / {delta_pct:+.2f}%)</span>
            """, unsafe_allow_html=True)
        with star_col:
            is_favorite = ticker in st.session_state.favorites
            star_icon = "⭐" if is_favorite else "★"
            if st.button(star_icon, key="fav_toggle"):
                if is_favorite: st.session_state.favorites.remove(ticker)
                else: st.session_state.favorites.append(ticker)
                if write_favorites_to_github(st.session_state.favorites): st.rerun()

        st.markdown("---")

        # 5. 메인 컨텐츠 (차트 + 지표)
        chart_col, metrics_col = st.columns([0.7, 0.3])
        with chart_col:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=processed_data["history"]["Date"], y=processed_data["history"]["Close"], mode='lines', name='종가', line=dict(width=3)))
            fig.add_trace(go.Scatter(x=processed_data["history"]["Date"], y=processed_data["history"]["MA50"], mode='lines', name='MA50', line=dict(color='orange', width=1.5)))
            fig.add_trace(go.Scatter(x=processed_data["history"]["Date"], y=processed_data["history"]["MA200"], mode='lines', name='MA200', line=dict(color='purple', width=1.5)))
            fig.add_trace(go.Scatter(x=processed_data["max_point"]["Date"], y=processed_data["max_point"]["High"], mode='markers', name='최고점', marker=dict(color='green', size=10, symbol='triangle-up'), hovertemplate='최고가: %{y:.2f}<br>%{x}'))
            fig.add_trace(go.Scatter(x=processed_data["min_point"]["Date"], y=processed_data["min_point"]["Low"], mode='markers', name='최저점', marker=dict(color='red', size=10, symbol='triangle-down'), hovertemplate='최저가: %{y:.2f}<br>%{x}'))
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)

        with metrics_col:
            # CSS Flexbox를 사용하여 지표들을 유연하게 배치
            metrics_html = "<div style='display: flex; flex-wrap: wrap; gap: 15px; align-items: center; height: 450px;'>"
            
            # 지표 데이터와 설명을 리스트로 관리
            metrics_list = [
                {"label": "RSI(14)", "value": f"{finviz_data.get('RSI', 0):.2f}", "help": "주가 추세의 강도를 나타내는 모멘텀 지표. 70 이상은 과매수, 30 이하는 과매도 구간으로 해석될 수 있습니다."},
                {"label": "P/E", "value": finviz_data.get("P/E", "N/A"), "help": "주가수익비율. 주가를 주당순이익으로 나눈 값."},
                {"label": "PEG", "value": finviz_data.get("PEG", "N/A"), "help": "주가수익성장비율. P/E를 주당순이익 증가율로 나눈 값."},
                {"label": f"매출 CAGR(5y)", "value": processed_data['cagr'].get('매출', 'N/A'), "help": "최근 5년간의 연평균 매출 성장률."},
                {"label": f"순이익 CAGR(5y)", "value": processed_data['cagr'].get('순이익', 'N/A'), "help": "최근 5년간의 연평균 순이익 성장률."}
            ]
            
            # 각 지표를 HTML로 생성 (Streamlit의 help 기능을 모방)
            for m in metrics_list:
                metrics_html += f"""
                <div style='flex-grow: 1; min-width: 120px;'>
                    <span title='{m['help']}' style='font-size: 1.1em; font-weight: bold;'>{m['label']} ❓</span>
                    <br>
                    <span style='font-size: 1.5em;'>{m['value']}</span>
                </div>
                """
            metrics_html += "</div>"
            st.markdown(metrics_html, unsafe_allow_html=True)

    else:
        st.error(f"'{ticker}'에 대한 데이터를 찾을 수 없습니다.")
    
    st.session_state.run_search = False

else:
    st.info("우측 상단의 검색창에 종목 코드를 입력하거나, 사이드바의 즐겨찾기를 클릭하여 분석을 시작하세요.")
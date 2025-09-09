# app.py

import streamlit as st
import polars as pl
import yfinance as yf
from requests_html import HTMLSession
import plotly.graph_objects as go
from github import Github, UnknownObjectException
import json

# --- 페이지 설정 ---
st.set_page_config(page_title="Stock Analysis Dashboard", page_icon="📊", layout="wide")

# --- UI 커스텀 CSS ---
st.markdown("""
<style>
/* 사이드바의 즐겨찾기 버튼을 텍스트처럼 보이게 만듭니다 */
div[data-testid="stSidebarNav"] + div div[data-testid="stButton"] > button {
    border: none;
    background-color: transparent;
    text-align: left;
    padding-left: 0;
    color: inherit; /* 현재 테마의 글자색을 따름 */
}
div[data-testid="stSidebarNav"] + div div[data-testid="stButton"] > button:hover {
    color: #FF4B4B; /* 마우스를 올렸을 때 색상 */
    background-color: transparent;
}
</style>
""", unsafe_allow_html=True)


# --- GitHub 연동 (즐겨찾기 영구 저장) ---
FAVORITES_FILE_PATH = "favorites.json"

try:
    g = Github(st.secrets["GITHUB_TOKEN"])
    repo = g.get_repo(st.secrets["GITHUB_REPO"])
except Exception as e:
    st.sidebar.error("GitHub 인증 실패. Secrets를 확인하세요.")
    st.stop()

@st.cache_data(ttl=60) # 캐시 시간을 줄여 즐겨찾기 변경이 더 빨리 반영되도록 함
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
        contents = json.dumps(sorted(list(set(favorites_list))), indent=4) # 중복 제거 및 정렬
        try:
            file = repo.get_contents(FAVORITES_FILE_PATH)
            repo.update_file(FAVORITES_FILE_PATH, "Update favorites", contents, file.sha)
        except UnknownObjectException:
            repo.create_file(FAVORITES_FILE_PATH, "Create favorites", contents)
        st.cache_data.clear() # 즐겨찾기를 쓴 후 캐시를 지워 바로 반영
        return True
    except Exception as e:
        st.error(f"즐겨찾기 저장 실패: {e}")
        return False

# --- 데이터 로딩 및 처리 함수들 (이전과 동일) ---
@st.cache_data(ttl=600)
def fetch_full_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        hist_pd = ticker.history(period="2y", interval="1d")
        if hist_pd.empty: return None
        recommendations = ticker.recommendations
        financials = ticker.financials
        return {"info": info, "history": hist_pd, "recommendations": recommendations, "financials": financials}
    except Exception as e:
        st.error(f"데이터 로딩 중 오류 발생: {e}")
        return None

def process_data(full_data):
    hist_pl = pl.from_pandas(full_data["history"].reset_index())
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
    ]).drop_nulls()
    view_data = hist_pl.tail(252)
    max_point = view_data.filter(pl.col("High") == view_data["High"].max())
    min_point = view_data.filter(pl.col("Low") == view_data["Low"].min())
    cross_signal = pl.when(pl.col("MA50") > pl.col("MA200")).then(1).otherwise(-1)
    cross_events = view_data.with_columns(cross_signal.diff().alias("cross")).filter(pl.col("cross") != 0)
    financials_pl = pl.from_pandas(full_data["financials"].transpose().reset_index())
    cagr = {}
    for col in ["Total Revenue", "Net Income"]:
        if col in financials_pl.columns and financials_pl[col].drop_nulls().len() > 1:
            start_val = financials_pl[col].drop_nulls().last()
            end_val = financials_pl[col].drop_nulls().first()
            if start_val and end_val and start_val > 0:
                num_years = financials_pl[col].drop_nulls().len() - 1
                if num_years > 0:
                    cagr_val = ((end_val / start_val) ** (1 / num_years)) - 1
                    cagr[col] = f"{cagr_val:.2%}"
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
        metrics_to_get = ["P/E", "ROE", "PEG", "EV/EBITDA", "Target Price"]
        metrics = {name: data_map.get(name, "N/A") for name in metrics_to_get}
        return metrics
    except Exception:
        return {name: "Error" for name in metrics_to_get}

def get_rsi_guidance(rsi_value):
    if rsi_value > 70: return " <span style='color:orange;'>(과매수)</span>"
    if rsi_value < 30: return " <span style='color:lightblue;'>(과매도)</span>"
    return ""

# --- UI 렌더링 시작 ---

# 1. 사이드바 구성
if 'favorites' not in st.session_state:
    st.session_state.favorites = read_favorites_from_github()

for fav_ticker in st.session_state.favorites:
    if st.sidebar.button(fav_ticker, key=f"fav_{fav_ticker}"):
        st.session_state.ticker_to_search = fav_ticker
        st.session_state.run_search = True

st.sidebar.info("💡 앱 우측 상단의 점 세 개(⋮) 메뉴 > Settings에서 테마를 변경할 수 있습니다.")

# 2. 메인 화면 상단 (검색창)
_, search_col = st.columns([0.75, 0.25]) # 오른쪽 정렬을 위한 빈 공간
with search_col:
    with st.form(key="search_form"):
        ticker_input = st.text_input("종목 검색", "MSFT", label_visibility="collapsed")
        run_button = st.form_submit_button("🔍")

if run_button:
    st.session_state.ticker_to_search = ticker_input
    st.session_state.run_search = True

# 3. 분석 실행 로직
if "ticker_to_search" not in st.session_state:
    st.session_state.ticker_to_search = "MSFT" # 초기 실행 종목

if "run_search" not in st.session_state:
    st.session_state.run_search = True

if st.session_state.get("run_search", False):
    ticker = st.session_state.ticker_to_search
    full_data = fetch_full_data(ticker)
    
    if full_data:
        processed_data = process_data(full_data)
        finviz_data = scrape_finviz_data(ticker)
        
        # --- 메인 UI 렌더링 ---
        # 3-1. 제목 및 즐겨찾기 별
        title_col, star_col = st.columns([0.9, 0.1])
        with title_col:
            company_name = full_data["info"].get('longName', ticker)
            st.markdown(f"""
            <span style="font-size: 2.5em; font-weight: bold;">{company_name}</span>
            <span style="font-size: 1.5em; color: grey;">{ticker}</span>
            """, unsafe_allow_html=True)
        
        with star_col:
            is_favorite = ticker in st.session_state.favorites
            star_icon = "⭐" if is_favorite else "★"
            if st.button(star_icon, key="fav_toggle"):
                if is_favorite:
                    st.session_state.favorites.remove(ticker)
                else:
                    st.session_state.favorites.append(ticker)
                
                if write_favorites_to_github(st.session_state.favorites):
                    st.rerun()

        st.markdown("---")

        # 3-2. 7:3 레이아웃
        chart_col, metrics_col = st.columns([0.7, 0.3])

        with chart_col:
            # (차트 로직은 이전과 동일)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=processed_data["history"]["Date"], open=processed_data["history"]["Open"], high=processed_data["history"]["High"], low=processed_data["history"]["Low"], close=processed_data["history"]["Close"], name="주가"))
            fig.add_trace(go.Scatter(x=processed_data["history"]["Date"], y=processed_data["history"]["MA50"], mode='lines', name='MA50', line=dict(color='orange')))
            fig.add_trace(go.Scatter(x=processed_data["history"]["Date"], y=processed_data["history"]["MA200"], mode='lines', name='MA200', line=dict(color='purple')))
            fig.add_trace(go.Scatter(x=processed_data["max_point"]["Date"], y=processed_data["max_point"]["High"], mode='markers', name='최고점', marker=dict(color='green', size=10, symbol='triangle-up'), hovertemplate='최고가: %{y:.2f}<br>%{x}'))
            fig.add_trace(go.Scatter(x=processed_data["min_point"]["Date"], y=processed_data["min_point"]["Low"], mode='markers', name='최저점', marker=dict(color='red', size=10, symbol='triangle-down'), hovertemplate='최저가: %{y:.2f}<br>%{x}'))
            for _, row in processed_data["cross_events"].to_pandas().iterrows():
                if row["cross"] > 0:
                    fig.add_trace(go.Scatter(x=[row["Date"]], y=[row["MA50"]], mode='markers', name='골든크로스', marker=dict(color='gold', size=12, symbol='star'), hovertemplate='골든크로스'))
                else:
                    fig.add_trace(go.Scatter(x=[row["Date"]], y=[row["MA50"]], mode='markers', name='데드크로스', marker=dict(color='black', size=12, symbol='x'), hovertemplate='데드크로스'))
            fig.update_layout(xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)

        with metrics_col:
            latest = processed_data["history"].row(-1, named=True)
            rsi_val = latest['RSI']
            st.metric(label="RSI(14)", value=f"{rsi_val:.2f}", help="Relative Strength Index: 주가 추세의 강도를 나타내는 모멘텀 지표입니다. 70 이상은 과매수, 30 이하는 과매도 구간으로 해석될 수 있습니다.")
            
            st.markdown(f"<p style='text-align: right; color: grey;'>{get_rsi_guidance(rsi_val)}</p>", unsafe_allow_html=True)

            st.markdown("---")
            st.metric(label="P/E", value=finviz_data.get("P/E", "N/A"), help="Price-to-Earnings Ratio: 주가수익비율. 주가를 주당순이익(EPS)으로 나눈 값으로, 기업의 수익성에 비해 주가가 높은지 낮은지를 나타냅니다.")
            st.metric(label="PEG", value=finviz_data.get("PEG", "N/A"), help="Price/Earnings to Growth Ratio: 주가수익성장비율. P/E 비율을 주당순이익 증가율로 나눈 값으로, 기업의 성장성을 고려한 밸류에이션 지표입니다.")
            st.metric(label="EV/EBITDA", value=finviz_data.get("EV/EBITDA", "N/A"), help="Enterprise Value to EBITDA: 기업가치를 세전영업이익으로 나눈 값으로, 기업이 벌어들이는 현금흐름 대비 기업가치를 나타냅니다.")
            
            st.markdown("---")
            st.markdown("**성장성 (3년 CAGR)**", help="Compound Annual Growth Rate: 연평균 성장률")
            st.markdown(f"**총매출:** {processed_data['cagr'].get('Total Revenue', 'N/A')}")
            st.markdown(f"**순이익:** {processed_data['cagr'].get('Net Income', 'N/A')}")
            
            st.markdown("---")
            st.markdown("**애널리스트 의견**")
            recom = full_data["recommendations"]
            # --- 여기가 버그 수정 부분 ---
            if recom is not None and not recom.empty and "To Grade" in recom.columns:
                recom_summary = recom["To Grade"].value_counts().to_dict()
                for grade, count in recom_summary.items():
                    st.markdown(f"- **{grade}:** {count}명")
            else:
                st.markdown("정보 없음")

    else:
        st.error(f"'{ticker}'에 대한 데이터를 찾을 수 없습니다.")
    
    st.session_state.run_search = False

else:
    st.info("우측 상단의 검색창에 종목 코드를 입력하고 돋보기 버튼을 누르거나, 사이드바의 즐겨찾기를 클릭해주세요.")
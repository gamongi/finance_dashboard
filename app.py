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

# --- GitHub 연동 (즐겨찾기 영구 저장) ---
FAVORITES_FILE_PATH = "favorites.json"

# GitHub API 인증
try:
    g = Github(st.secrets["GITHUB_TOKEN"])
    repo = g.get_repo(st.secrets["GITHUB_REPO"])
except Exception as e:
    st.sidebar.error("GitHub 인증 실패. Secrets를 확인하세요.")
    st.stop()

def read_favorites_from_github():
    """GitHub에서 즐겨찾기 파일을 읽어옵니다."""
    try:
        content = repo.get_contents(FAVORITES_FILE_PATH)
        return json.loads(content.decoded_content.decode())
    except UnknownObjectException:
        # 파일이 없으면 기본 목록으로 새로 생성
        return ["MSFT", "AAPL", "GOOG", "NVDA"]
    except Exception as e:
        st.sidebar.error(f"즐겨찾기 로딩 실패: {e}")
        return []

def write_favorites_to_github(favorites_list):
    """즐겨찾기 목록을 GitHub 파일에 씁니다."""
    try:
        contents = json.dumps(favorites_list, indent=4)
        try:
            # 파일이 이미 있는지 확인
            file = repo.get_contents(FAVORITES_FILE_PATH)
            repo.update_file(FAVORITES_FILE_PATH, "Update favorites", contents, file.sha)
        except UnknownObjectException:
            # 파일이 없으면 새로 생성
            repo.create_file(FAVORITES_FILE_PATH, "Create favorites", contents)
        return True
    except Exception as e:
        st.sidebar.error(f"즐겨찾기 저장 실패: {e}")
        return False

# --- 데이터 로딩 함수들 ---
@st.cache_data(ttl=600)
def fetch_full_data(ticker_symbol):
    """yfinance에서 모든 관련 데이터를 가져오는 통합 함수"""
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # 1. 기업 정보 (이름 등)
        info = ticker.info
        
        # 2. 주가 데이터 (MA 계산을 위해 2년치 로딩)
        hist_pd = ticker.history(period="2y", interval="1d")
        if hist_pd.empty: return None
        
        # 3. 애널리스트 추천
        recommendations = ticker.recommendations
        
        # 4. 재무 데이터 (CAGR 계산용)
        financials = ticker.financials
        
        return {
            "info": info,
            "history": hist_pd,
            "recommendations": recommendations,
            "financials": financials
        }
    except Exception as e:
        st.error(f"데이터 로딩 중 오류 발생: {e}")
        return None

def process_data(full_data):
    """가져온 데이터를 Polars로 변환하고 모든 지표를 계산합니다."""
    # 주가 데이터 처리
    hist_pl = pl.from_pandas(full_data["history"].reset_index())
    
    # 기술적 지표 계산
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

    # 최고/최저점 찾기
    view_data = hist_pl.tail(252)
    max_point = view_data.filter(pl.col("High") == view_data["High"].max())
    min_point = view_data.filter(pl.col("Low") == view_data["Low"].min())

    # 골든/데드크로스 찾기
    cross_signal = pl.when(pl.col("MA50") > pl.col("MA200")).then(1).otherwise(-1)
    cross_events = view_data.with_columns(
        cross_signal.diff().alias("cross")
    ).filter(pl.col("cross") != 0)
    
    # CAGR 계산
    financials_pl = pl.from_pandas(full_data["financials"].transpose().reset_index())
    cagr = {}
    for col in ["Total Revenue", "Net Income"]:
        if col in financials_pl.columns and financials_pl[col].drop_nulls().len() > 1:
            # --- 여기가 핵심 수정 부분 ---
            # yfinance는 최신 데이터를 위쪽에 배치하므로, last()가 가장 오래된 데이터(시작 값)
            start_val = financials_pl[col].drop_nulls().last() 
            # first()가 가장 최신 데이터(종료 값)
            end_val = financials_pl[col].drop_nulls().first()
            
            if start_val and end_val and start_val > 0:
                # drop_nulls()를 했으므로 실제 데이터 길이로 기간 계산
                num_years = financials_pl[col].drop_nulls().len() - 1
                if num_years > 0:
                    cagr_val = ((end_val / start_val) ** (1 / num_years)) - 1
                    cagr[col] = f"{cagr_val:.2%}"
    
    return {
        "history": view_data,
        "max_point": max_point,
        "min_point": min_point,
        "cross_events": cross_events,
        "cagr": cagr
    }

@st.cache_data(ttl=600)
def scrape_finviz_data(ticker_symbol):
    # (이전과 동일, PEG, EV/EBITDA 추가)
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
        return {name: "Error" for name in ["P/E", "ROE", "PEG", "EV/EBITDA", "Target Price"]}

# --- 지표 가이드 함수 ---
def get_rsi_guidance(rsi_value):
    if rsi_value > 70: return " <span style='color:orange;'>(과매수 구간)</span>"
    if rsi_value < 30: return " <span style='color:lightblue;'>(과매도 구간)</span>"
    return ""

# --- UI 구성 ---

# 즐겨찾기 로딩 및 사이드바 구성
if 'favorites' not in st.session_state:
    st.session_state.favorites = read_favorites_from_github()

st.sidebar.header("⭐ 즐겨찾기")
for fav_ticker in st.session_state.favorites:
    if st.sidebar.button(fav_ticker, key=f"fav_{fav_ticker}"):
        st.session_state.ticker_to_search = fav_ticker
        st.session_state.run_search = True

st.sidebar.header("조회 설정")
with st.sidebar.form(key="search_form"):
    ticker_input = st.text_input("종목 코드를 입력하세요", "MSFT").upper()
    run_button = st.form_submit_button("분석 실행")

# 다크모드 토글 (Streamlit 자체 테마 설정 존중)
st.sidebar.markdown("---")
st.sidebar.info("💡 햄버거 메뉴(☰) > Settings에서 다크/라이트 테마를 설정할 수 있습니다.")


if run_button:
    st.session_state.ticker_to_search = ticker_input
    st.session_state.run_search = True

if st.session_state.get("run_search", False):
    ticker = st.session_state.ticker_to_search
    
    full_data = fetch_full_data(ticker)
    
    if full_data:
        processed_data = process_data(full_data)
        finviz_data = scrape_finviz_data(ticker)
        
        # --- 메인 UI 렌더링 ---
        # 1. 제목 (회사명 + 티커)
        company_name = full_data["info"].get('longName', ticker)
        st.markdown(f"""
        <span style="font-size: 2.5em; font-weight: bold; color: primary;">{company_name}</span>
        <span style="font-size: 1.5em; color: grey;">{ticker}</span>
        """, unsafe_allow_html=True)
        
        # 즐겨찾기 추가/삭제 버튼
        if ticker in st.session_state.favorites:
            if st.button(f"⭐ {ticker} 즐겨찾기에서 삭제"):
                st.session_state.favorites.remove(ticker)
                if write_favorites_to_github(st.session_state.favorites):
                    st.success("삭제되었습니다.")
                    st.rerun()
        else:
            if st.button(f"⭐ {ticker} 즐겨찾기에 추가"):
                st.session_state.favorites.append(ticker)
                if write_favorites_to_github(st.session_state.favorites):
                    st.success("추가되었습니다.")
                    st.rerun()

        st.markdown("---")

        # 2. 7:3 레이아웃
        col1, col2 = st.columns([0.7, 0.3])

        with col1: # 왼쪽 차트 영역
            st.subheader("주가 차트")
            fig = go.Figure()
            # 캔들스틱 차트
            fig.add_trace(go.Candlestick(x=processed_data["history"]["Date"],
                                         open=processed_data["history"]["Open"],
                                         high=processed_data["history"]["High"],
                                         low=processed_data["history"]["Low"],
                                         close=processed_data["history"]["Close"],
                                         name="주가"))
            # 이동평균선
            fig.add_trace(go.Scatter(x=processed_data["history"]["Date"], y=processed_data["history"]["MA50"], mode='lines', name='MA50', line=dict(color='orange')))
            fig.add_trace(go.Scatter(x=processed_data["history"]["Date"], y=processed_data["history"]["MA200"], mode='lines', name='MA200', line=dict(color='purple')))
            
            # 최고/최저점 마커
            fig.add_trace(go.Scatter(x=processed_data["max_point"]["Date"], y=processed_data["max_point"]["High"], mode='markers', name='최고점', marker=dict(color='green', size=10, symbol='triangle-up'), hovertemplate='최고가: %{y:.2f}<br>%{x}'))
            fig.add_trace(go.Scatter(x=processed_data["min_point"]["Date"], y=processed_data["min_point"]["Low"], mode='markers', name='최저점', marker=dict(color='red', size=10, symbol='triangle-down'), hovertemplate='최저가: %{y:.2f}<br>%{x}'))

            # 골든/데드크로스 마커
            for _, row in processed_data["cross_events"].to_pandas().iterrows():
                if row["cross"] > 0: # 골든크로스
                    fig.add_trace(go.Scatter(x=[row["Date"]], y=[row["MA50"]], mode='markers', name='골든크로스', marker=dict(color='gold', size=12, symbol='star'), hovertemplate='골든크로스'))
                else: # 데드크로스
                    fig.add_trace(go.Scatter(x=[row["Date"]], y=[row["MA50"]], mode='markers', name='데드크로스', marker=dict(color='black', size=12, symbol='x'), hovertemplate='데드크로스'))

            fig.update_layout(xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)

        with col2: # 오른쪽 지표 영역
            st.subheader("주요 지표")
            latest = processed_data["history"].row(-1, named=True)
            
            rsi_val = latest['RSI']
            st.markdown(f"**RSI(14):** {rsi_val:.2f}{get_rsi_guidance(rsi_val)}", unsafe_allow_html=True)
            
            st.markdown("---")
            st.subheader("밸류에이션")
            for name in ["P/E", "PEG", "EV/EBITDA"]:
                st.markdown(f"**{name}:** {finviz_data.get(name, 'N/A')}")
            
            st.markdown("---")
            st.subheader("성장성 (3년 CAGR)")
            st.markdown(f"**총매출:** {processed_data['cagr'].get('Total Revenue', 'N/A')}")
            st.markdown(f"**순이익:** {processed_data['cagr'].get('Net Income', 'N/A')}")
            
            st.markdown("---")
            st.subheader("애널리스트 의견")
            if full_data["recommendations"] is not None and not full_data["recommendations"].empty:
                recom_summary = full_data["recommendations"]["To Grade"].value_counts().to_dict()
                for grade, count in recom_summary.items():
                    st.markdown(f"- **{grade}:** {count}명")
            else:
                st.markdown("정보 없음")

    else:
        st.error(f"'{ticker}'에 대한 데이터를 찾을 수 없습니다.")
    
    st.session_state.run_search = False
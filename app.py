import streamlit as st
import yfinance as yf
import polars as pl
from streamlit_lottie import st_lottie
import requests

# --------------------------------------------------------------------------------
# 1. 페이지 설정 (Page Config)
# --------------------------------------------------------------------------------
st.set_page_config(
    page_title="Fox Stock Dashboard",
    page_icon="🦊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------------------------------------
# 2. 데이터 로드 및 캐싱 함수
# --------------------------------------------------------------------------------
@st.cache_data(ttl=3600) # 1시간 동안 캐시 유지
def get_ticker_data(ticker_symbol):
    """yfinance를 사용하여 주식 데이터를 가져오고 캐싱하는 함수"""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        hist = ticker.history(period="2d") # 현재가 및 전일비 계산을 위해 2일치 데이터 요청

        if hist.empty or len(hist) < 2:
            return None # 데이터가 부족하면 None 반환

        # 필요한 데이터 추출
        data = {
            "longName": info.get("longName", ticker_symbol),
            "currentPrice": hist['Close'].iloc[-1],
            "previousClose": hist['Close'].iloc[-2],
            "marketCap": info.get("marketCap"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "priceToBook": info.get("priceToBook"),
            "dividendYield": info.get("dividendYield"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        }
        return data
    except Exception as e:
        # st.error(f"Error fetching data for {ticker_symbol}: {e}")
        return None

# --------------------------------------------------------------------------------
# 3. Lottie 애니메이션 로드 함수
# --------------------------------------------------------------------------------
def load_lottieurl(url: str):
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()

lottie_url = "https://lottie.host/b3644a2c-19b8-40b9-9a84-bee9b8a32c52/tN9g32Ea5l.json"
lottie_json = load_lottieurl(lottie_url)

# --------------------------------------------------------------------------------
# 4. CSS 스타일링 (Figma 디자인 및 기능 개선 기반)
# --------------------------------------------------------------------------------
st.markdown("""
<style>
    /* Streamlit 기본 요소 숨기기 */
    .stDeployButton, #stDecoration { display: none; }

    /* 헤더 스타일 */
    .header-container {
        display: flex;
        align-items: center;
        gap: 15px; /* 요소 사이의 간격 */
    }
    .stock-name { font-size: 28px; font-weight: bold; }
    .stock-ticker { font-size: 20px; color: #888; margin-left: 8px; }
    .stock-price { font-size: 28px; font-weight: bold; }
    .stock-change-positive { font-size: 18px; color: #4CAF50; /* 초록색 */ }
    .stock-change-negative { font-size: 18px; color: #F44336; /* 빨간색 */ }

    /* 즐겨찾기 별 버튼 스타일 */
    .stButton > button {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        font-size: 28px;
        color: #FFCA28; /* 노란색 */
    }
    .stButton > button:hover {
        opacity: 0.7;
    }

    /* 사이드바 버튼 (텍스트 스타일) */
    .st-emotion-cache-16txtl3 h2 { font-size: 20px; font-weight: bold; margin-bottom: 1rem; }
    .st-emotion-cache-16txtl3 .stButton > button {
        background: transparent;
        border: none;
        color: #555;
        text-align: left;
        padding: 8px 0;
        font-size: 16px;
        width: 100%;
        transition: color 0.2s;
    }
    .st-emotion-cache-16txtl3 .stButton > button:hover {
        color: #FF4B4B;
    }
    /* 선택된 항목 스타일은 Python에서 st.markdown으로 직접 적용 */
    .selected-watchlist-item {
        padding: 8px 0;
        font-size: 16px;
        font-weight: bold;
        color: #FF4B4B;
    }

    /* 검색창 스타일 */
    .stTextInput > div > div > input {
        background-color: #F0F2F6; border: none; border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------
# 5. 세션 상태 초기화 (Session State)
# --------------------------------------------------------------------------------
if 'ticker' not in st.session_state:
    st.session_state.ticker = 'AAPL'
if 'favorites' not in st.session_state:
    st.session_state.favorites = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA']

# --------------------------------------------------------------------------------
# 6. 사이드바 구현 (Sidebar)
# --------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<h2>My Watchlist</h2>", unsafe_allow_html=True)

    # 즐겨찾기 목록 표시
    for fav_ticker in st.session_state.favorites:
        # 현재 선택된 티커는 강조된 텍스트로 표시
        if fav_ticker == st.session_state.ticker:
            st.markdown(f'<p class="selected-watchlist-item">{fav_ticker}</p>', unsafe_allow_html=True)
        else:
            # 나머지는 버튼으로 만들어 클릭 가능하게 함
            if st.button(fav_ticker, key=f"fav_{fav_ticker}"):
                st.session_state.ticker = fav_ticker
                st.rerun()

# --------------------------------------------------------------------------------
# 7. 메인 화면 구현 (Main Content)
# --------------------------------------------------------------------------------

# --- 7.1. 데이터 가져오기 ---
data = get_ticker_data(st.session_state.ticker)

if not data:
    st.error(f"'{st.session_state.ticker}'에 대한 데이터를 가져올 수 없습니다. 티커를 확인해주세요.")
    st.stop()

# --- 7.2. 헤더 (Header) ---
header_cols = st.columns([0.8, 5, 2]) # [별+로티], [주식정보], [검색창]

with header_cols[0]:
    # 헤더 컨테이너 시작
    st.markdown('<div class="header-container">', unsafe_allow_html=True)

    # 즐겨찾기 버튼 (별)
    is_favorite = st.session_state.ticker in st.session_state.favorites
    star_icon = "⭐" if is_favorite else "☆"
    if st.button(star_icon, key="favorite_btn"):
        if is_favorite:
            st.session_state.favorites.remove(st.session_state.ticker)
        else:
            st.session_state.favorites.append(st.session_state.ticker)
        st.rerun()

    # Lottie 애니메이션
    if lottie_json:
        st_lottie(lottie_json, speed=1, width=60, height=60, key="lottie_header")

    st.markdown('</div>', unsafe_allow_html=True)


with header_cols[1]:
    # 가격 및 등락률 계산
    price_change = data['currentPrice'] - data['previousClose']
    price_change_percent = (price_change / data['previousClose']) * 100
    change_class = "stock-change-positive" if price_change >= 0 else "stock-change-negative"
    change_symbol = "+" if price_change >= 0 else ""

    # 헤더 정보 표시
    st.markdown(f"""
    <div class="header-container" style="padding-top: 10px;">
        <span class="stock-name">{data['longName']}</span>
        <span class="stock-ticker">{st.session_state.ticker}</span>
        <span class="stock-price">${data['currentPrice']:.2f}</span>
        <span class="{change_class}">{change_symbol}{price_change:.2f} ({change_symbol}{price_change_percent:.2f}%)</span>
    </div>
    """, unsafe_allow_html=True)

with header_cols[2]:
    # 검색창
    search_ticker = st.text_input(
        "Search Ticker", placeholder="Search Ticker...", label_visibility="collapsed"
    )
    if search_ticker and search_ticker.upper() != st.session_state.ticker:
        st.session_state.ticker = search_ticker.upper()
        st.rerun()

st.markdown("---")

# --- 7.3. 차트 및 주요 지표 영역 ---
main_cols = st.columns([3, 1.2])

with main_cols[0]:
    # TradingView 차트
    tradingview_html = f"""
    <div style="height: 650px; width: 100%;">
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
          "autosize": true,
          "symbol": "{st.session_state.ticker}",
          "interval": "D",
          "timezone": "Etc/UTC",
          "theme": "light",
          "style": "1",
          "locale": "en",
          "enable_publishing": false,
          "allow_symbol_change": false, /* 심볼 변경 비활성화 */
          "container_id": "tradingview_widget_container"
      }});
      </script>
      <div id="tradingview_widget_container" style="height: 100%; width: 100%;"></div>
    </div>
    """
    st.components.v1.html(tradingview_html, height=650)

with main_cols[1]:
    # 주요 지표 (Key Metrics)
    st.markdown("<h4>Key Metrics</h4>", unsafe_allow_html=True)

    # 숫자 포맷팅 함수
    def format_market_cap(mc):
        if mc is None: return "N/A"
        if mc >= 1e12: return f"${mc/1e12:.2f} T"
        if mc >= 1e9: return f"${mc/1e9:.2f} B"
        if mc >= 1e6: return f"${mc/1e6:.2f} M"
        return f"${mc}"

    # 2x3 그리드로 지표 표시
    metric_cols = st.columns(2)
    with metric_cols[0]:
        st.metric("Market Cap", format_market_cap(data['marketCap']))
        st.metric("Trailing P/E", f"{data['trailingPE']:.2f}" if data['trailingPE'] else "N/A")
        st.metric("Dividend Yield", f"{data['dividendYield']*100:.2f}%" if data['dividendYield'] else "N/A")
    with metric_cols[1]:
        st.metric("52-Week High", f"${data['fiftyTwoWeekHigh']:.2f}" if data['fiftyTwoWeekHigh'] else "N/A")
        st.metric("Forward P/E", f"{data['forwardPE']:.2f}" if data['forwardPE'] else "N/A")
        st.metric("Price-to-Book", f"{data['priceToBook']:.2f}" if data['priceToBook'] else "N/A")
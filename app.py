# app.py

import streamlit as st
import polars as pl
import plotly.express as px

# --- 페이지 설정 ---
st.set_page_config(page_title="My Finance Dashboard", page_icon="📈", layout="wide")

# --- 샘플 데이터 생성 (Polars 사용) ---
# 실제로는 이 부분에서 API를 통해 데이터를 가져와 Polars DataFrame으로 만들게 됩니다.
data = {
    'Date': ['2023-08-01', '2023-08-02', '2023-08-03', '2023-08-04', '2023-08-05'],
    'Price': [150.5, 152.3, 151.8, 155.2, 154.9],
    'Volume': [120000, 135000, 110000, 150000, 142000]
}
# Polars DataFrame으로 변환하고, 날짜 문자열을 날짜 타입으로 변경합니다.
df = pl.DataFrame(data).with_columns(
    pl.col("Date").str.to_date(format="%Y-%m-%d")
)

# 최신 가격과 이전 가격을 가져옵니다.
latest_price = df.item(-1, "Price") # 마지막 행의 'Price' 값
prev_price = df.item(-2, "Price")   # 마지막에서 두 번째 행의 'Price' 값
price_change = latest_price - prev_price

# --- 대시보드 UI 구성 ---

# 1. 제목
st.title("📈 나의 금융 대시보드 (Polars Ver.)")
st.markdown("---")

# 2. 핵심 지표 (Metric)
col1, col2, col3 = st.columns(3)
col1.metric(label="현재 가격 (USD)", value=f"${latest_price:,.2f}", delta=f"{price_change:,.2f}")
col2.metric(label="거래량", value=f"{df.item(-1, 'Volume'):,}")
col3.metric(label="RSI (14)", value="68.5", delta="-5.2")

st.markdown("---")

# 3. 시계열 차트 (Line Chart)
# Plotly는 Polars DataFrame을 직접 지원하지 않으므로, Pandas로 변환하여 전달합니다.
fig = px.line(df.to_pandas(), x='Date', y='Price', title='가격 변동 추이', markers=True)
fig.update_layout(xaxis_title='날짜', yaxis_title='가격 (USD)')
st.plotly_chart(fig, use_container_width=True)

# 4. 데이터 테이블
st.subheader("최근 데이터")
st.dataframe(df.tail(5)) # Polars DataFrame을 표로 보여줍니다.

# 5. 사이드바
st.sidebar.header("설정")
stock_symbol = st.sidebar.text_input("종목 코드", "AAPL")
st.sidebar.button("업데이트")

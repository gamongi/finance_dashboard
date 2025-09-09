# screenshot.py

import asyncio
from playwright.async_api import async_playwright
import time # time 라이브러리 추가

# --- ❗ 매우 중요 ❗ ---
# 아래 URL은 이미 본인의 URL로 잘 설정되어 있을 겁니다.
DASHBOARD_URL = "https://financedashboard-nrgnyaexmsn43mkc8fkwws.streamlit.app"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        print(f"Navigating to {DASHBOARD_URL}...")
        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded") # 옵션을 변경하여 조금 더 빠르게 진행
        
        # --- 여기가 핵심 수정 부분 1 ---
        # Streamlit 앱이 잠에서 깨어날 시간을 15초 정도 줍니다.
        print("Waiting for the app to wake up...")
        await page.wait_for_timeout(15000) # 15초 대기
        
        print("Looking for the main content area...")
        # --- 여기가 핵심 수정 부분 2 ---
        # 기다리는 최대 시간을 120초(120000ms)로 늘립니다.
        await page.wait_for_selector("div[data-testid='stAppViewContainer']", timeout=120000)
        
        print("Taking screenshot...")
        # 스크린샷 찍기 전에도 잠시 딜레이를 주어 렌더링을 확실히 합니다.
        await page.wait_for_timeout(5000)
        await page.screenshot(path="dashboard.png", full_page=True)
        
        print("Screenshot saved as dashboard.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
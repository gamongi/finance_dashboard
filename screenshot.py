# screenshot.py

import asyncio
from playwright.async_api import async_playwright

# --- ❗ 매우 중요 ❗ ---
# 아래 URL을 1단계에서 완성한 본인의 Streamlit 대시보드 URL로 교체해주세요!
DASHBOARD_URL = "https://financedashboard-nrgnyaexmsn43mkc8fkwws.streamlit.app/" 

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        print(f"Navigating to {DASHBOARD_URL}...")
        await page.goto(DASHBOARD_URL, wait_until="networkidle")
        
        # Streamlit 앱의 메인 콘텐츠 블록이 렌더링될 때까지 기다립니다.
        # 스크린샷이 비어있는 것을 방지하는 중요한 단계입니다.
        await page.wait_for_selector("div[data-testid='stAppViewContainer']", timeout=60000)
        
        print("Taking screenshot...")
        await page.screenshot(path="dashboard.png", full_page=True)
        
        print("Screenshot saved as dashboard.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
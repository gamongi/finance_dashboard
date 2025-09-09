# screenshot.py

import asyncio
from playwright.async_api import async_playwright, TimeoutError

DASHBOARD_URL = "https://financedashboard-nrgnyaexmsn43mkc8fkwws.streamlit.app"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        try:
            print(f"Navigating to {DASHBOARD_URL}...")
            await page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=60000)
            
            print("Looking for the main content area...")
            await page.wait_for_selector("div[data-testid='stAppViewContainer']", timeout=120000)
            
            print("Taking screenshot of successful page...")
            await page.screenshot(path="dashboard.png", full_page=True)
            print("Screenshot saved as dashboard.png")

        except TimeoutError:
            print("TimeoutError occurred! Taking a screenshot of the current page for debugging.")
            # --- 여기가 핵심 ---
            # 실패했더라도, 현재 보이는 화면을 사진으로 남깁니다.
            await page.screenshot(path="dashboard.png", full_page=True)
            print("Debug screenshot saved as dashboard.png. Please check the repo for the error page.")
            # 오류를 다시 발생시켜 GitHub Actions가 실패했음을 인지하게 합니다.
            raise 
        
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
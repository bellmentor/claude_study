"""크로미움 헤드풀 실행 진단."""
import asyncio
import os
from playwright.async_api import async_playwright


async def main():
    print("DISPLAY =", os.environ.get("DISPLAY"))
    print("WAYLAND_DISPLAY =", os.environ.get("WAYLAND_DISPLAY"))
    async with async_playwright() as p:
        print("chromium.executable_path =", p.chromium.executable_path)
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto("https://example.com", wait_until="domcontentloaded")
        print("page url:", page.url)
        print("창이 떠야 정상. 5초 후 종료합니다...")
        await asyncio.sleep(5)
        await browser.close()


asyncio.run(main())

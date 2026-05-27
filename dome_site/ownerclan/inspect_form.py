import asyncio
from playwright.async_api import async_playwright

LOGIN_URL = "https://ownerclan.com/V2/member/loginform.php"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("URL:", page.url)
        print("TITLE:", await page.title())

        forms = await page.evaluate(
            """() => Array.from(document.querySelectorAll('form')).map(f => ({
                action: f.getAttribute('action'),
                method: f.getAttribute('method'),
                id: f.id,
                name: f.getAttribute('name'),
                inputs: Array.from(f.querySelectorAll('input,button')).map(i => ({
                    tag: i.tagName,
                    type: i.getAttribute('type'),
                    name: i.getAttribute('name'),
                    id: i.id,
                    value: i.getAttribute('value'),
                    placeholder: i.getAttribute('placeholder')
                }))
            }))"""
        )
        for i, f in enumerate(forms):
            print(f"\n--- form #{i} ---")
            print("action:", f["action"], "method:", f["method"], "id:", f["id"], "name:", f["name"])
            for inp in f["inputs"]:
                print(" ", inp)

        await browser.close()

asyncio.run(main())

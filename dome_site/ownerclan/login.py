"""오너클랜 로그인."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import openpyxl

from .session import MODE, close_session, get_page

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_XLSX = ROOT / "계정정보.xlsx"
SCREENSHOT = Path(__file__).with_name("after_login.png")

LOGIN_URL = "https://ownerclan.com/V2/member/loginform.php"
SITE_LABEL = "오너클랜"


def load_credentials(site_label: str = SITE_LABEL) -> tuple[str, str]:
    """계정정보.xlsx 에서 사이트의 (id, pw) 를 반환한다."""
    wb = openpyxl.load_workbook(ACCOUNT_XLSX, data_only=True)
    ws = wb["Sheet1"]
    for row in ws.iter_rows(values_only=True):
        if row and row[0] == site_label:
            user, pw = row[1], row[2]
            if not user or not pw:
                raise RuntimeError(f"[{site_label}] 아이디/비밀번호가 비어있음")
            return str(user), str(pw)
    raise RuntimeError(f"[{site_label}] 행을 찾을 수 없음")


async def login() -> bool:
    """오너클랜에 로그인한다. 모듈 세션을 재사용하며 종료하지 않는다. 성공 여부 반환."""
    user, pw = load_credentials()
    page = await get_page()

    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.fill("#id", user)
    await page.fill("#passwd", pw)
    async with page.expect_navigation(wait_until="domcontentloaded"):
        await page.locator("form[name=loginForm] input[type=submit]").click()

    url = page.url
    title = await page.title()
    print(f"[{SITE_LABEL}] 로그인 후 URL  :", url)
    print(f"[{SITE_LABEL}] 로그인 후 TITLE:", title)
    await page.screenshot(path=str(SCREENSHOT), full_page=False)
    return "loginform.php" not in url and "login.php" not in url


async def _standalone() -> int:
    """단독 실행 진입점: login() 후 세션을 정리한다.

    debug 모드에서는 브라우저 창을 직접 볼 수 있도록 종료 전에 Enter 키를 기다린다.
    """
    try:
        ok = await login()
        if ok:
            print(f"\n[{SITE_LABEL}] 로그인 성공")
        else:
            print(f"\n[{SITE_LABEL}] 로그인 실패")

        if MODE == "debug":
            print("\n[debug] 브라우저 창을 확인하세요. Enter 키를 누르면 종료합니다...")
            await asyncio.to_thread(input)

        return 0 if ok else 1
    finally:
        await close_session()


if __name__ == "__main__":
    sys.exit(asyncio.run(_standalone()))

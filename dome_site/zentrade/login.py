"""젠트레이드 로그인."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import openpyxl

from .session import MODE, close_session, get_page

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_XLSX = ROOT / "계정정보.xlsx"

LOGIN_URL = "https://www.zentrade.co.kr/shop/main/index.php"
SITE_LABEL = "젠트"


def load_credentials(site_label: str = SITE_LABEL) -> tuple[str, str]:
    """계정정보.xlsx에서 사이트의 (id, pw)를 반환한다."""
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
    """젠트레이드에 로그인한다. 성공 여부 반환."""
    user, pw = load_credentials()
    page = await get_page()

    await page.goto(LOGIN_URL, wait_until="domcontentloaded")

    # 팝업창 모두 닫기
    import asyncio as _asyncio
    await _asyncio.sleep(1)
    await page.evaluate("""
        // 입금자 찾기 팝업
        var el = document.getElementById('blnCookie_specialdays');
        if (el) el.style.display = 'none';
        // 마이페이지 레이어
        var el2 = document.getElementById('MypageLayerBox');
        if (el2) el2.style.display = 'none';
    """)
    # 혹시 남은 팝업 닫기 버튼 클릭
    for sel in ["img[src*='popup_bu_close']", "img[src*='close.gif']"]:
        try:
            buttons = await page.locator(sel).all()
            for btn in buttons:
                if await btn.is_visible():
                    await btn.click()
                    await _asyncio.sleep(0.3)
        except Exception:
            pass
    await _asyncio.sleep(0.3)

    await page.fill("input[name='m_id']", user)
    await page.fill("input[name='password']", pw)
    async with page.expect_navigation(wait_until="domcontentloaded"):
        await page.locator("input[type='image'][src*='btn_login']").click()

    # login_ok.php 로 이동한 뒤 메인으로 리다이렉트될 수 있으므로 잠시 대기
    await page.wait_for_load_state("domcontentloaded")
    url = page.url
    title = await page.title()
    print(f"[{SITE_LABEL}] 로그인 후 URL  : {url}")
    print(f"[{SITE_LABEL}] 로그인 후 TITLE: {title}")
    # login_ok.php = 로그인 성공 처리 페이지, loginform = 로그인 실패
    return "loginform" not in url.lower()


async def _standalone() -> int:
    """단독 실행 진입점."""
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

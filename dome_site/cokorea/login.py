"""코코리아(바나나하우스) 로그인 (Cafe24 계열몰)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import openpyxl

from dome_site.logger import SiteLogger
from .session import MODE, close_session, get_page

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_XLSX = ROOT / "계정정보.xlsx"
SCREENSHOT = Path(__file__).with_name("after_login.png")

LOGIN_URL = "https://ds1008.com/member/login.html"
ORDER_LIST_URL = "https://ds1008.com/myshop/order/list.html"
SITE_LABEL = "코코리아"

log = SiteLogger(SITE_LABEL)


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
    """코코리아에 로그인한다. 모듈 세션을 재사용하며 종료하지 않는다. 성공 여부 반환."""
    log.step("로그인", "계정 정보 로딩")
    user, pw = load_credentials()
    page = await get_page()

    # JS 검증 alert 자동 수락 + 메시지 로깅
    page.on(
        "dialog",
        lambda d: (log.warn(f"로그인 alert: {d.message}"), asyncio.create_task(d.accept())),
    )

    # Cafe24 ePlaceholder 때문에 fill() 값이 간헐적으로 빈 값 인식됨 → 실제 키입력(type)+검증+재시도.
    for attempt in range(3):
        log.debug(f"로그인 시도 {attempt + 1}/3")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        idf = page.locator("#member_id")
        pwf = page.locator("#member_passwd")
        await idf.click()
        await idf.fill("")
        await idf.type(user, delay=20)
        await pwf.click()
        await pwf.fill("")
        await pwf.type(pw, delay=20)

        if not (await idf.input_value()):
            log.warn("아이디 입력값이 비어있음 → 재시도")
            continue

        log.debug("로그인 버튼 클릭")
        # 로그인 버튼: <button type="button" ... alt="로그인">Log in</button>
        login_btn = page.locator("button[alt='로그인'], a.btnLogin, button:has-text('Log in')").first
        await login_btn.click()
        try:
            await page.wait_for_url(lambda u: "login" not in u, timeout=10000)
        except Exception:
            await page.wait_for_load_state("networkidle")

        if "login" not in page.url:
            break
        log.warn(f"로그인 재시도 ({attempt + 1}/3): 여전히 로그인 페이지")
        await asyncio.sleep(1)

    # 주문조회 페이지로 이동해 접근 가능한지(로그인 성공) 확인
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    url = page.url
    title = await page.title()
    log.info(f"주문조회 URL: {url}")
    log.info(f"주문조회 TITLE: {title}")
    await page.screenshot(path=str(SCREENSHOT), full_page=False)

    # 주문조회 페이지면 로그인 폼(#member_passwd)이 없어야 성공
    ok = "login" not in url and await page.locator("#member_passwd").count() == 0
    if ok:
        log.success("로그인 성공")
    else:
        log.error("로그인 실패 (주문조회 접근 불가)")
        await log.dump_on_error(page, RuntimeError("로그인 실패"))
    return ok


async def _standalone() -> int:
    """단독 실행 진입점: login() 후 세션을 정리한다."""
    try:
        ok = await login()
        print(f"\n[{SITE_LABEL}] 로그인 {'성공' if ok else '실패'}")
        if MODE == "debug":
            print("\n[debug] 브라우저 창을 확인하세요. Enter 키를 누르면 종료합니다...")
            await asyncio.to_thread(input)
        return 0 if ok else 1
    finally:
        await close_session()


if __name__ == "__main__":
    sys.exit(asyncio.run(_standalone()))

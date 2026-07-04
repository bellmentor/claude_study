"""파라브로 주문목록 조회 및 엑셀 다운로드."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://www.parabro.co.kr/mypage/order_list.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

# 조회 기간 입력 필드. 시작일은 id=picker2, 종료일은 id 없는 두 번째 wDate[] 입력칸.
START_DATE_SEL = "#picker2"
END_DATE_SEL = "input[name='wDate[]']:not([id])"

log = SiteLogger("파라브로")


async def _set_datepicker(page, selector: str, value: str) -> None:
    """데이트피커 입력칸에 날짜를 주입한다.

    js_datepicker 는 readonly 라 fill() 이 막힐 수 있으므로 value 를 직접 세팅하고
    input/change 이벤트를 발생시켜 폼이 값을 인식하게 한다.
    """
    await page.eval_on_selector(
        selector,
        """(el, v) => {
            el.removeAttribute('readonly');
            el.value = v;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문목록을 조회하고 엑셀 파일을 다운로드한다. 다운로드된 파일 경로를 반환."""
    page = await get_page()

    # 1. 주문조회 페이지 이동
    log.step("주문조회", f"기간: {start_date} ~ {end_date}")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")

    # 2. 조회 기간 입력 (시작일/종료일)
    log.debug("조회 기간 입력")
    await _set_datepicker(page, START_DATE_SEL, start_date)
    await _set_datepicker(page, END_DATE_SEL, end_date)

    # 3. 조회 버튼 클릭 → 결과 로딩 대기
    log.step("조회하기")
    query_btn = page.locator("button.btn_date_check").first
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            await query_btn.click()
    except Exception:
        log.debug("네비게이션 미감지 → networkidle 대기로 폴백")
        await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)

    # 4. 엑셀 다운로드
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with page.expect_download() as download_info:
        await page.locator("span.js_order_excel").first.click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_파라브로_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    await download.save_as(str(dest))
    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

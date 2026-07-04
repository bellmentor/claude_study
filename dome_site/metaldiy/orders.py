"""철물박사 주문배송조회 및 엑셀 다운로드.

날짜 직접 입력이 어려워 '6개월' 라디오로 조회한 뒤, 월 필터링은 summarize 에서 한다.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://www.metaldiy.com/mypage/orderList.do"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

log = SiteLogger("철물박사")


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문배송조회(최근 6개월)를 조회하고 엑셀을 다운로드한다. 다운로드된 파일 경로를 반환.

    start_date/end_date 는 인터페이스 통일을 위해 받지만, 조회는 '6개월' 라디오로 하고
    실제 월 필터링은 summarize 단계에서 수행한다.
    """
    page = await get_page()

    # 1. 주문배송조회 페이지 이동
    log.step("주문조회", "최근 6개월 조회")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")

    # 2. '6개월' 라디오 선택
    log.debug("6개월 라디오 선택")
    await page.locator("#date_term_186").check()

    # 3. 조회 버튼(이미지) 클릭 → 결과 로딩 대기
    log.step("조회하기")
    search_btn = page.locator("input[type=image][alt='검색']").first
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            await search_btn.click()
    except Exception:
        log.debug("네비게이션 미감지 → networkidle 대기로 폴백")
        await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)

    # 4. 엑셀 다운로드
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with page.expect_download() as download_info:
        await page.locator("#excelMultiDown").first.click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_철물박사_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    await download.save_as(str(dest))
    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

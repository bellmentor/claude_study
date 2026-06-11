"""오너클랜 주문목록 조회 및 엑셀 다운로드."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from .session import get_page

ORDER_LIST_URL = "https://ownerclan.com/V2/service/orderList.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문목록을 조회하고 엑셀 파일을 다운로드한다. 다운로드된 파일 경로를 반환."""
    page = await get_page()

    # 1. 주문/배송조회 페이지 이동
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")

    # 2. 날짜 입력
    await page.fill("#startDatepicker", start_date)
    await page.fill("#finishDatepicker", end_date)

    # 3. 체크박스: 전체 체크 → 전체 해제 → 필요한 것만 체크
    all_check = page.locator("#all_check")
    if not await all_check.is_checked():
        await all_check.click()
        await asyncio.sleep(0.2)
    await all_check.click()
    await asyncio.sleep(0.2)

    for deli_id in ("#deliType_N", "#deliType_S", "#deliType_Y", "#deliType_E"):
        await page.locator(deli_id).check()
        await asyncio.sleep(0.2)

    # 4. 체크박스마다 getOrderList() 호출되므로 AJAX 완료 대기
    await page.wait_for_load_state("networkidle")

    # 5. 조회하기 클릭 (최대 3회 재시도)
    for attempt in range(3):
        await page.locator("img[alt='조회하기']").click()
        try:
            await page.locator("#tblBody tr").first.wait_for(state="attached", timeout=10000)
            break
        except Exception:
            print(f"[오너클랜] 조회하기 재시도 ({attempt + 1}/3)")
            await asyncio.sleep(1)

    # 6. 엑셀 다운로드
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with page.expect_download() as download_info:
        await page.locator("img[alt='엑셀 다운로드']").click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_오너클랜_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    await download.save_as(str(dest))
    print(f"[오너클랜] 엑셀 다운로드 완료: {dest}")
    return dest

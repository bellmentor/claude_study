"""친구도매(79dome) 구매내역 조회 및 엑셀 다운로드.

날짜를 직접 입력할 수 있어 해당 월 범위로 조회하고 '엑셀파일다운로드' 를 받는다.
다운로드 클릭 시 확인 팝업(confirm)이 뜨므로 자동 수락한다.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://79dome.com/shop/orderinquiry.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

log = SiteLogger("친구도매")


def _normalize_download(dest: Path) -> None:
    """다운로드 파일이 HTML 테이블(첫 행 헤더)이면 진짜 xlsx 로 변환한다."""
    head = dest.read_bytes()[:64].lstrip().lower()
    if not head.startswith(b"<") and b"<html" not in head and b"<meta" not in head:
        return  # 이미 정상 엑셀
    tables = pd.read_html(dest, header=0)
    if not tables:
        log.warn("다운로드 HTML 에서 테이블을 찾지 못해 변환을 건너뜁니다")
        return
    df = max(tables, key=lambda t: t.shape[1])
    df.to_excel(dest, index=False)
    log.debug(f"HTML 다운로드를 진짜 xlsx 로 변환 (행 {len(df)}건)")


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """해당 월(start_date~end_date) 구매내역을 조회해 엑셀로 다운로드한다. 저장 파일 경로를 반환."""
    page = await get_page()

    # 다운로드 확인 팝업(confirm) 자동 수락
    page.on("dialog", lambda d: asyncio.create_task(d.accept()))

    # 1. 구매내역 페이지를 날짜 범위 파라미터와 함께 이동 (조회 적용)
    log.step("주문조회", f"기간: {start_date} ~ {end_date}")
    url = f"{ORDER_LIST_URL}?date1={start_date}&date2={end_date}"
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 2. 엑셀파일다운로드 (confirm 팝업 → 자동 수락 → ../page/excel_order.php 로 POST 다운로드)
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with page.expect_download() as download_info:
        await page.locator("#excel_orders").click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_친구도매_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        await download.save_as(str(dest))
    except PermissionError:
        alt = DOWNLOAD_DIR / (datetime.now().strftime("%y%m%d_%H%M%S") + "_친구도매_매입금.xlsx")
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await download.save_as(str(dest))

    _normalize_download(dest)
    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

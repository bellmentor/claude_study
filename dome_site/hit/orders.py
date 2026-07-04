"""히트가구 주문조회 및 엑셀 다운로드 (Cafe24 계열몰)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://b2b-hitdesign.com/myshop/order/list.html"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

log = SiteLogger("히트가구")


def _normalize_download(dest: Path) -> None:
    """다운로드 파일이 HTML 테이블이면 진짜 xlsx 로 변환한다(엑셀에서 정상 열리게)."""
    head = dest.read_bytes()[:64].lstrip().lower()
    if not head.startswith(b"<"):
        return  # 이미 정상 엑셀
    tables = pd.read_html(dest)
    if not tables:
        log.warn("다운로드 HTML 에서 테이블을 찾지 못해 변환을 건너뜁니다")
        return
    df = max(tables, key=lambda t: t.shape[1])
    df.to_excel(dest, index=False)
    log.debug(f"HTML 다운로드를 진짜 xlsx 로 변환 (행 {len(df)}건)")


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문내역 엑셀을 다운로드한다. 다운로드된 파일 경로를 반환.

    start_date/end_date 는 인터페이스 통일을 위해 받지만, 실제 월 필터링은 summarize 에서 한다.
    """
    page = await get_page()

    # 1. 주문조회 페이지 이동
    log.step("주문조회", f"선택월: {start_date}~{end_date}")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 2. 주문내역 엑셀 다운로드
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with page.expect_download() as download_info:
        await page.locator("#excel_download_btn").first.click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_히트가구_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        await download.save_as(str(dest))
    except PermissionError:
        alt = DOWNLOAD_DIR / (
            datetime.now().strftime("%y%m%d_%H%M%S") + "_히트가구_매입금.xlsx"
        )
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await download.save_as(str(dest))

    _normalize_download(dest)
    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

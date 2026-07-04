"""식자재코리아 주문(거래원장) 조회 및 엑셀 다운로드."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://www.sikjajekr.com/order/order_list.php?mode=order"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

log = SiteLogger("식자재코리아")


def _normalize_download(dest: Path) -> None:
    """다운로드 파일이 HTML 테이블(거래원장)이면 진짜 xlsx 로 변환한다.

    식자재코리아 '거래원장 다운로드' 는 확장자만 .xls 일 뿐 실제 내용은 HTML 테이블이고,
    첫 행이 헤더(구분/주문번호/일자/...)다. read_html(header=0) 으로 읽어 xlsx 로 저장한다.
    """
    head = dest.read_bytes()[:64].lstrip().lower()
    if not head.startswith(b"<") and b"<html" not in head:
        return  # 이미 정상 엑셀
    tables = pd.read_html(dest, header=0)
    if not tables:
        log.warn("다운로드 HTML 에서 테이블을 찾지 못해 변환을 건너뜁니다")
        return
    df = max(tables, key=lambda t: t.shape[1])
    df.to_excel(dest, index=False)
    log.debug(f"HTML 거래원장을 진짜 xlsx 로 변환 (행 {len(df)}건)")


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """거래원장(최근 6개월)을 조회해 엑셀로 다운로드한다. 다운로드된 파일 경로를 반환.

    start_date/end_date 는 인터페이스 통일을 위해 받지만, 조회는 '6개월' 버튼으로 하고
    실제 월 필터링은 summarize 가 한다.
    (기간 버튼: dayButton5=2개월, dayButton6=6개월, dayButton9=전체)
    """
    page = await get_page()

    # 1. 주문관리(거래원장) 페이지 이동
    log.step("주문조회", "최근 6개월 거래원장")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")

    # 2. '6개월' 기간 선택
    log.debug("6개월 기간 선택")
    await page.locator("#dayButton6").click()

    # 3. 조회 버튼 클릭 → 결과 로딩 대기
    log.step("조회하기")
    search_btn = page.locator("input.search[value='조회']").first
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            await search_btn.click()
    except Exception:
        log.debug("네비게이션 미감지 → networkidle 대기로 폴백")
        await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)

    # 4. 거래원장 다운로드 (클릭 시 확인 팝업 → 자동 수락)
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    page.on("dialog", lambda d: asyncio.create_task(d.accept()))

    async with page.expect_download() as download_info:
        await page.locator("input.button3[value='거래원장 다운로드']").first.click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_식자재코리아_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        await download.save_as(str(dest))
    except PermissionError:
        alt = DOWNLOAD_DIR / (
            datetime.now().strftime("%y%m%d_%H%M%S") + "_식자재코리아_매입금.xlsx"
        )
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await download.save_as(str(dest))

    _normalize_download(dest)
    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

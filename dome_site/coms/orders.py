"""컴스마트 주문내역 조회.

이 사이트는 엑셀 다운로드가 없어, 주문내역 페이지의 테이블(table#tblk)을 직접 크롤링해
다른 사이트와 동일하게 downloads/ 에 xlsx 로 저장한다. 월 필터/합산은 summarize 가 한다.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://comsmart.co.kr/cmart/shop/orderinquiry.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

log = SiteLogger("컴스마트")


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문내역 테이블(table#tblk)을 크롤링해 xlsx 로 저장한다. 저장 파일 경로를 반환.

    start_date/end_date 는 인터페이스 통일을 위해 받지만, 월 필터링은 summarize 에서 한다.
    ※ 주문이 많아 페이지네이션이 생기면 여기서 페이지 순회를 추가해야 한다(현재 단일 페이지).
    """
    page = await get_page()

    # 1. 주문내역조회 페이지 이동
    log.step("주문조회", f"선택월: {start_date}~{end_date}")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 2. 주문 테이블 크롤링
    log.step("주문 테이블 크롤링")
    if await page.locator("#tblk").count() == 0:
        await log.dump_on_error(page, RuntimeError("주문 테이블(#tblk)을 찾지 못함"))
        raise RuntimeError("주문 테이블(#tblk)을 찾지 못함")

    html = await page.content()
    tables = pd.read_html(io.StringIO(html), attrs={"id": "tblk"})
    if not tables:
        raise RuntimeError("주문 테이블(#tblk) 파싱 실패")
    df = tables[0]
    log.debug(f"크롤링 행 수: {len(df)} / 컬럼: {list(df.columns)}")

    # 3. xlsx 로 저장
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    filename = date.today().strftime("%y%m%d") + "_컴스마트_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        df.to_excel(dest, index=False)
    except PermissionError:
        alt = DOWNLOAD_DIR / (
            datetime.now().strftime("%y%m%d_%H%M%S") + "_컴스마트_매입금.xlsx"
        )
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        df.to_excel(dest, index=False)

    log.success(f"주문 테이블 저장 완료: {dest}")
    return dest

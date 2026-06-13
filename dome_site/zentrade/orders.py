"""젠트레이드 월별 매출통계 조회 및 엑셀 저장."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

# 매출통계 테이블이 iframe 안에 있으므로 iframe src를 직접 호출
STATS_IFRAME_URL = "https://www.zentrade.co.kr/shop/mypage/log_stat.sales.month.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

log = SiteLogger("젠트")


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """월별 매출통계 iframe 페이지에서 테이블을 스크래핑하여 엑셀로 저장한다."""
    page = await get_page()

    # start_date/end_date에서 년월 추출
    sy, sm = start_date[:4], start_date[5:7]
    ey, em = end_date[:4], end_date[5:7]
    url = f"{STATS_IFRAME_URL}?sy={sy}&sm={sm}&ey={ey}&em={em}"

    # 1. iframe 내부 페이지 직접 이동
    log.step("매출통계 조회", f"기간: {start_date} ~ {end_date}")
    log.debug(f"iframe URL: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # 2. 테이블 대기 (최대 30초, 3회 재시도)
    log.step("테이블 로딩", "table.statistics-list 대기 (최대 30초, 3회 재시도)")
    for attempt in range(3):
        try:
            await page.wait_for_selector("table.statistics-list", timeout=30000)
            log.debug(f"테이블 발견 (시도 {attempt + 1})")
            break
        except Exception:
            log.warn(f"테이블 로딩 재시도 ({attempt + 1}/3)")
            if attempt == 2:
                log.error("테이블 로딩 3회 실패")
                await log.dump_on_error(page, RuntimeError("테이블 로딩 3회 실패"))
            await page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)

    # 3. 데이터 행 스크래핑 (헤더행, rndline 구분선 제외)
    log.step("데이터 스크래핑")
    rows = await page.locator("table.statistics-list tbody tr").all()
    log.debug(f"총 행 수: {len(rows)}")
    table_data = []
    for row in rows:
        # 구분선 행 건너뛰기
        if await row.locator("td.rndline").count() > 0:
            continue
        cells = await row.locator("td").all()
        if not cells:
            continue
        cell_texts = []
        for cell in cells:
            text = (await cell.inner_text()).strip()
            cell_texts.append(text)
        if cell_texts and len(cell_texts) >= 2:
            table_data.append(cell_texts)

    if not table_data:
        err = RuntimeError("매출통계 테이블에서 데이터를 찾을 수 없습니다")
        await log.dump_on_error(page, err)
        raise err

    # 4. DataFrame 생성
    columns = ["날짜", "매출금액", "주문건수", "전달대비 매출증감", "전달대비 주문건수", "상품금액", "배송비"]
    df = pd.DataFrame(table_data, columns=columns[:len(table_data[0])])
    log.info(f"매출통계 테이블: {len(df)}행 조회됨")

    # 5. 엑셀 저장
    log.step("엑셀 저장")
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    filename = date.today().strftime("%y%m%d") + "_젠트_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    df.to_excel(dest, index=False)
    log.success(f"엑셀 저장 완료: {dest}")
    return dest

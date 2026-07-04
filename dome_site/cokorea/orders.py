"""코코리아(바나나하우스) 주문목록 크롤링.

엑셀 다운로드가 없어 주문목록 페이지(.orderList)를 직접 크롤링한다.
'6개월' 기간으로 조회하고, 페이지가 여러 개면 전부 순회해 (날짜, 판매가)를 모아
다른 사이트와 동일하게 downloads/ 에 xlsx 로 저장한다. 월 필터/계산은 summarize 가 한다.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://ds1008.com/myshop/order/list.html"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

DATE_SEL = "span.date[title='주문일자']"
PRICE_SEL = "span.price[title='판매가']"

log = SiteLogger("코코리아")


async def _crawl_current_page(page) -> list[dict]:
    """현재 페이지의 (날짜, 판매가) 목록을 반환한다. span.date 와 span.price 는 1:1."""
    dates = await page.locator(DATE_SEL).all_inner_texts()
    prices = await page.locator(PRICE_SEL).all_inner_texts()
    if len(dates) != len(prices):
        log.warn(f"날짜({len(dates)})와 가격({len(prices)}) 개수가 다름 — 최소 개수만 사용")
    rows = []
    for d, p in zip(dates, prices):
        rows.append({"날짜": d.strip(), "판매가": p.strip()})
    return rows


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """3개월 주문목록을 전 페이지 순회 크롤링해 xlsx 로 저장한다. 저장 파일 경로를 반환.

    start_date/end_date 는 인터페이스 통일을 위해 받지만, 조회는 '3개월' 버튼으로 하고
    실제 월 필터/계산은 summarize 가 한다.
    """
    page = await get_page()

    # 1. 주문조회 페이지 이동
    log.step("주문조회", "최근 6개월")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 2. '6개월' 기간 선택 (days: 00=오늘, 30=1개월, 90=3개월, 180=6개월)
    log.debug("6개월 기간 선택")
    period = page.locator("a.btnNormal[days='180']")
    if await period.count():
        await period.first.click()
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

    # 3. 페이지 링크 수집 (페이징 ol 의 각 li a href 에 날짜범위+page 파라미터가 들어있음)
    paging = page.locator(".xans-myshop-orderhistorypaging").first
    page_hrefs: list[str] = []
    if await paging.count():
        links = paging.locator("ol li a")
        for i in range(await links.count()):
            h = await links.nth(i).get_attribute("href")
            if h and h.startswith("?") and h not in page_hrefs:
                page_hrefs.append(h)
    page_urls = [ORDER_LIST_URL + h for h in page_hrefs] or [page.url]
    log.step("주문 크롤링", f"{len(page_urls)}페이지")

    # 4. 각 페이지 순회 크롤링
    all_rows: list[dict] = []
    for idx, url in enumerate(page_urls, start=1):
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        rows = await _crawl_current_page(page)
        log.debug(f"페이지 {idx}/{len(page_urls)}: {len(rows)}건")
        all_rows.extend(rows)

    log.info(f"총 크롤링 주문: {len(all_rows)}건")
    df = pd.DataFrame(all_rows, columns=["날짜", "판매가"])

    # 5. xlsx 저장 (다른 도매처와 동일 규칙)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    filename = date.today().strftime("%y%m%d") + "_코코리아_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        df.to_excel(dest, index=False)
    except PermissionError:
        alt = DOWNLOAD_DIR / (datetime.now().strftime("%y%m%d_%H%M%S") + "_코코리아_매입금.xlsx")
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await asyncio.to_thread(df.to_excel, str(dest), index=False)

    log.success(f"주문목록 저장 완료: {dest}")
    return dest

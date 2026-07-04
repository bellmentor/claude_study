"""JTC코리아 주문목록 크롤링.

엑셀 다운로드가 없어 주문목록 테이블(.mypage_table_type)을 직접 크롤링한다.
기간은 '1년'으로 조회한다(이 사이트엔 6개월 버튼이 없고 3개월/1년만 있어, 오래된 달
누락을 피하려고 1년 사용). 페이지가 여러 개면 전부 순회해 (날짜, 가격)을 모아
다른 사이트와 동일하게 downloads/ 에 xlsx 로 저장한다. 월 필터/계산은 summarize 가 한다.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://www.1001094.com/mypage/order_list.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

# 기간 버튼 data-value: 0=오늘,7,15,30=1개월,90=3개월,365=1년 (6개월 없음)
PERIOD_VALUE = "365"

_DATE_RE = re.compile(r"\d{4}/\d{2}/\d{2}")
_PRICE_RE = re.compile(r"([\d,]+)\s*원")

log = SiteLogger("JTC코리아")


async def _crawl_current_page(page) -> list[dict]:
    """현재 페이지 테이블의 각 주문행에서 (날짜, 가격)을 추출한다.

    행 텍스트에서 날짜(YYYY/MM/DD)와 첫 금액(NN,NNN원)을 뽑는다. 날짜가 없는 행(헤더 등)은 건너뛴다.
    """
    rows = page.locator(".mypage_table_type table tr")
    n = await rows.count()
    out: list[dict] = []
    for i in range(n):
        text = await rows.nth(i).inner_text()
        dm = _DATE_RE.search(text)
        if not dm:
            continue  # 헤더/빈 행
        pm = _PRICE_RE.search(text)
        if not pm:
            continue
        out.append({"날짜": dm.group(0), "가격": pm.group(1) + "원"})
    return out


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문목록(1년)을 전 페이지 순회 크롤링해 xlsx 로 저장한다. 저장 파일 경로를 반환.

    start_date/end_date 는 인터페이스 통일을 위해 받지만, 실제 월 필터/계산은 summarize 가 한다.
    """
    page = await get_page()

    # 1. 주문관리 페이지 이동
    log.step("주문조회", "최근 1년")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 2. 기간(1년) 선택 후 조회
    log.debug("1년 기간 선택 + 조회")
    period = page.locator(f"button[data-value='{PERIOD_VALUE}']")
    if await period.count():
        await period.first.click()
    await page.locator("button.btn_date_check").first.click()
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)

    # 3. 페이지 링크 수집 (.pagination 의 각 li a href 에 page/날짜범위 파라미터가 들어있음)
    page_urls: list[str] = [page.url]
    pag = page.locator(".pagination").first
    if await pag.count():
        links = pag.locator("ul li a")
        for i in range(await links.count()):
            h = await links.nth(i).get_attribute("href")
            if h:
                u = urljoin(page.url, h)
                if u not in page_urls:
                    page_urls.append(u)
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
    df = pd.DataFrame(all_rows, columns=["날짜", "가격"])

    # 5. xlsx 저장 (다른 도매처와 동일 규칙)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    filename = date.today().strftime("%y%m%d") + "_JTC코리아_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        df.to_excel(dest, index=False)
    except PermissionError:
        alt = DOWNLOAD_DIR / (datetime.now().strftime("%y%m%d_%H%M%S") + "_JTC코리아_매입금.xlsx")
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        df.to_excel(dest, index=False)

    log.success(f"주문목록 저장 완료: {dest}")
    return dest

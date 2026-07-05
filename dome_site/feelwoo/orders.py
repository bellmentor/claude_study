"""필우커머스 주문조회 및 엑셀 다운로드. (고도몰 계열 — 파라브로와 동일 솔루션)

날짜를 직접 입력할 수 있어 해당 월 범위로 조회한다.
주문상태 체크박스(입금대기/결제완료/상품준비중/배송중/배송완료/구매확정)를 모두 체크해 조회한다
(취소/반품류는 목록에 없어 자동 제외됨).
'엑셀다운로드'(스타일 span)는 확장자만 .xlsx 이고 실제 내용은 HTML 이라 진짜 xlsx 로 변환한다.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import Page

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://www.feelwoo.com/mypage/order_list.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

# 조회 기간 입력 필드. 시작일은 id=picker2, 종료일은 id 없는 두 번째 wDate[] 입력칸 (파라브로와 동일).
START_DATE_SEL = "#picker2"
END_DATE_SEL = "input[name='wDate[]']:not([id])"

# 주문상태 체크박스 input id (취소/반품류는 목록에 없어 자동 제외)
STATUS_CHECKBOXES = [
    "#orderStatus_o1",  # 입금대기
    "#orderStatus_p1",  # 결제완료
    "#orderStatus_g1",  # 상품준비중
    "#orderStatus_d1",  # 배송중
    "#orderStatus_d2",  # 배송완료
    "#orderStatus_s1",  # 구매확정
]

log = SiteLogger("필우커머스")


async def _set_datepicker(page: Page, selector: str, value: str) -> None:
    """데이트피커 입력칸에 날짜를 주입한다. readonly 대비 value 직접 세팅 + 이벤트 발생."""
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


def _normalize_download(dest: Path) -> None:
    """다운로드 파일이 HTML 테이블이면 엑셀에서 정상적으로 열리는 진짜 .xlsx 로 변환한다."""
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
    """해당 월(start_date~end_date) 주문을 조회해 엑셀로 다운로드한다. 저장 파일 경로를 반환."""
    page = await get_page()

    # 1. 주문조회 페이지 이동
    log.step("주문조회", f"기간: {start_date} ~ {end_date}")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 2. 조회 기간 입력
    log.debug("조회 기간 입력")
    await _set_datepicker(page, START_DATE_SEL, start_date)
    await _set_datepicker(page, END_DATE_SEL, end_date)

    # 3. 주문상태 체크박스 전체 체크 (고도몰 커스텀 UI 라 JS 로 checked 설정)
    for sel in STATUS_CHECKBOXES:
        try:
            await page.eval_on_selector(
                sel,
                """(el) => {
                    if (!el.checked) {
                        el.checked = true;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""",
            )
        except Exception as e:
            log.warn(f"체크박스 {sel} 체크 실패(무시): {e}")

    # 4. 조회 버튼 클릭 → 결과 로딩 대기
    log.step("조회하기")
    query_btn = page.locator("button.cl-find").first
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            await query_btn.click()
    except Exception:
        log.debug("네비게이션 미감지 → networkidle 대기로 폴백")
        await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)

    # 5. 엑셀 다운로드
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with page.expect_download() as download_info:
        await page.locator("span:has-text('엑셀다운로드')").first.click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_필우커머스_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        await download.save_as(str(dest))
    except PermissionError:
        alt = DOWNLOAD_DIR / (datetime.now().strftime("%y%m%d_%H%M%S") + "_필우커머스_매입금.xlsx")
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await download.save_as(str(dest))

    _normalize_download(dest)
    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

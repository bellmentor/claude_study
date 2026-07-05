"""3MRO 주문/배송조회 및 엑셀 다운로드.

날짜를 직접 입력할 수 있어 해당 월 범위로 조회한다.
주문상태 체크박스(입금확인/배송준비중/배송중/배송완료)를 모두 체크해 조회한다
(취소류는 여기서 체크하지 않아 자동 제외됨).
'엑셀다운로드' 클릭 시 새 창(팝업)이 뜨고, 그 안의 '3MRO양식' 버튼을 눌러야 실제 다운로드된다.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import Page

from dome_site.logger import SiteLogger
from .session import get_context, get_page

ORDER_LIST_URL = "https://www.3mro.co.kr/shop/mypage.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

# 조회할 주문상태 체크박스 (취소류는 목록에 없으므로 체크하지 않아 자동 제외된다)
STATUS_CHECKBOXES = ["#od_status1", "#od_status2", "#od_status3", "#od_status4"]

log = SiteLogger("3MRO")


async def _set_date(page: Page, selector: str, value: str) -> None:
    """datepicker 입력칸에 날짜(YYYY-MM-DD)를 넣는다. readonly 대비 JS 주입 폴백."""
    try:
        await page.fill(selector, value, timeout=3000)
        if (await page.locator(selector).input_value()) == value:
            return
    except Exception:
        pass
    # 폴백: value 직접 주입 + input/change 이벤트 발생
    await page.eval_on_selector(
        selector,
        """(el, v) => {
            el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )


def _read_xls_ole2(path: Path) -> pd.DataFrame:
    """구형 .xls 바이너리(OLE2)를 xlrd 로 직접 읽어 DataFrame 으로 반환한다.

    ★ 3MRO 의 .xls 는 xlrd 가 'Workbook corruption' 으로 판단하는 경우가 있어(월마다 다름)
      pd.read_excel(engine='xlrd') 로는 실패하거나 값을 잘못 읽는다.
      → ignore_workbook_corruption=True 로 열어서 첫 행을 헤더로, 나머지를 데이터로 파싱한다.
    """
    import xlrd

    wb = xlrd.open_workbook(str(path), ignore_workbook_corruption=True)
    sheet = wb.sheet_by_index(0)
    rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
    if not rows:
        return pd.DataFrame()
    header = [str(h).strip() for h in rows[0]]
    return pd.DataFrame(rows[1:], columns=header)


def _normalize_download(dest: Path) -> None:
    """다운로드 파일을 진짜 xlsx(PK) 로 변환한다.

    3MRO '3MRO양식' 다운로드는 확장자만 .xlsx 이고 실제 내용은 구형 .xls 바이너리(OLE2)다.
    또한 일부 사이트는 HTML 테이블을 내려주기도 한다. 두 경우 모두 진짜 xlsx 로 다시 저장한다.
    """
    raw = dest.read_bytes()
    magic = raw[:8]

    if magic.startswith(b"PK"):
        return  # 이미 진짜 xlsx

    if magic.startswith(b"\xd0\xcf\x11\xe0"):  # OLE2 = 구형 .xls 바이너리
        df = _read_xls_ole2(dest)
        df.to_excel(dest, index=False)
        log.debug(f".xls 바이너리를 진짜 xlsx 로 변환 (행 {len(df)}건)")
        return

    head = raw[:64].lstrip().lower()
    if head.startswith(b"<") or b"<html" in head or b"<meta" in head:  # HTML 테이블
        tables = pd.read_html(dest, header=0)
        if not tables:
            log.warn("다운로드 HTML 에서 테이블을 찾지 못해 변환을 건너뜁니다")
            return
        df = max(tables, key=lambda t: t.shape[1])
        df.to_excel(dest, index=False)
        log.debug(f"HTML 다운로드를 진짜 xlsx 로 변환 (행 {len(df)}건)")


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """해당 월(start_date~end_date) 주문을 조회해 엑셀로 다운로드한다. 저장 파일 경로를 반환."""
    page = await get_page()
    context = await get_context()

    # 혹시 모를 확인 팝업(dialog) 자동 수락
    page.on("dialog", lambda d: asyncio.create_task(d.accept()))

    # 1. 주문/배송조회 페이지 이동
    log.step("주문조회", f"기간: {start_date} ~ {end_date}")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 2. 조회기간 입력
    await _set_date(page, "#fr_date", start_date)
    await _set_date(page, "#to_date", end_date)
    log.debug(f"조회기간 입력: {start_date} ~ {end_date}")

    # 3. 주문상태 체크박스 전체 체크 (취소류는 목록에 없어 자동 제외)
    #    그누보드 커스텀 UI 라 실제 input 이 화면 밖에 숨겨져 있어(뷰포트 밖) 클릭이 안 된다.
    #    → JS 로 checked=true 를 직접 설정하고 change 이벤트를 발생시킨다.
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

    # 4. 조회 버튼 클릭
    log.debug("조회 버튼 클릭")
    await page.locator("input[type=submit][value='검색']").first.click()
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)

    # 5. 엑셀다운로드 → 새 창(팝업) → '3MRO양식' 버튼 → 실제 다운로드
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    log.debug("엑셀다운로드 클릭 (새 창 대기)")
    async with context.expect_page() as popup_info:
        await page.locator("button:has-text('엑셀다운로드')").first.click()
    popup = await popup_info.value
    await popup.wait_for_load_state("domcontentloaded")
    popup.on("dialog", lambda d: asyncio.create_task(d.accept()))

    log.debug("팝업에서 '3MRO양식' 클릭")
    excel_link = popup.locator("a[onclick*=\"downorder('3mro')\"]").first
    if await excel_link.count() == 0:
        excel_link = popup.locator("a:has-text('3MRO양식')").first

    async with popup.expect_download() as download_info:
        await excel_link.click()
    download = await download_info.value

    filename = date.today().strftime("%y%m%d") + "_3MRO_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        await download.save_as(str(dest))
    except PermissionError:
        alt = DOWNLOAD_DIR / (datetime.now().strftime("%y%m%d_%H%M%S") + "_3MRO_매입금.xlsx")
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await download.save_as(str(dest))

    try:
        await popup.close()
    except Exception:
        pass

    _normalize_download(dest)
    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

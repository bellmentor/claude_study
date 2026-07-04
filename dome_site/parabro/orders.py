"""파라브로 주문목록 조회 및 엑셀 다운로드."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from .session import get_page

ORDER_LIST_URL = "https://www.parabro.co.kr/mypage/order_list.php"
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

# 조회 기간 입력 필드. 시작일은 id=picker2, 종료일은 id 없는 두 번째 wDate[] 입력칸.
START_DATE_SEL = "#picker2"
END_DATE_SEL = "input[name='wDate[]']:not([id])"

log = SiteLogger("파라브로")


def parabro_query_range(start_date: str) -> tuple[str, str]:
    """선택한 월(start_date=해당월 1일)로부터 파라브로에 넣을 넓은 조회기간을 계산한다.

    파라브로는 '해당월 1일 ~ 말일' 처럼 딱 맞춰 조회하면 서버 오류로 주문목록을 제대로
    내려주지 못한다. 그래서 앞뒤로 넉넉히 잡아 조회하고, 실제 계산은 summarize 에서
    선택한 월만 필터링한다.

    규칙:
      - 조회 시작일 = (선택월 전달의 마지막 날) − 3일
      - 조회 종료일 = 선택월 다음달의 3일
    (윤년/30·31일 차이는 date 연산이 자동 처리한다.)

    예) 2026-03 선택 → ('2026-02-25', '2026-04-03')
    """
    y, m = int(start_date[:4]), int(start_date[5:7])
    sel_first = date(y, m, 1)
    prev_last = sel_first - timedelta(days=1)          # 전달 마지막 날
    q_start = prev_last - timedelta(days=3)            # 전달 마지막 날에서 3일 전
    q_end = date(y + 1, 1, 3) if m == 12 else date(y, m + 1, 3)  # 다음달 3일
    return q_start.isoformat(), q_end.isoformat()


def _normalize_download(dest: Path) -> None:
    """다운로드 파일을 엑셀에서 정상적으로 열리는 진짜 .xlsx 로 변환한다.

    파라브로 '엑셀다운로드' 는 확장자만 .xlsx 일 뿐 실제 내용은 HTML 테이블이라
    엑셀에서 바로 열면 데이터가 깨져 보인다. HTML 이면 파싱해 진짜 xlsx 로 덮어쓴다.
    """
    head = dest.read_bytes()[:64].lstrip().lower()
    if not head.startswith(b"<"):
        return  # 이미 정상 엑셀
    tables = pd.read_html(dest)
    if not tables:
        log.warn("다운로드 HTML 에서 테이블을 찾지 못해 변환을 건너뜁니다")
        return
    df = tables[0]
    df.to_excel(dest, index=False)
    log.debug(f"HTML 다운로드를 진짜 xlsx 로 변환 (행 {len(df)}건)")


async def _set_datepicker(page, selector: str, value: str) -> None:
    """데이트피커 입력칸에 날짜를 주입한다.

    js_datepicker 는 readonly 라 fill() 이 막힐 수 있으므로 value 를 직접 세팅하고
    input/change 이벤트를 발생시켜 폼이 값을 인식하게 한다.
    """
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


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문목록을 조회하고 엑셀 파일을 다운로드한다. 다운로드된 파일 경로를 반환.

    start_date/end_date 는 사용자가 선택한 '해당 월' 범위이며, 파라브로에는 서버 오류
    회피를 위해 앞뒤로 넉넉히 넓힌 기간(parabro_query_range)을 넣어 조회한다.
    """
    page = await get_page()

    q_start, q_end = parabro_query_range(start_date)

    # 1. 주문조회 페이지 이동
    log.step("주문조회", f"선택월: {start_date}~{end_date} / 실제조회: {q_start}~{q_end}")
    await page.goto(ORDER_LIST_URL, wait_until="domcontentloaded")

    # 2. 조회 기간 입력 (넓힌 기간)
    log.debug("조회 기간 입력")
    await _set_datepicker(page, START_DATE_SEL, q_start)
    await _set_datepicker(page, END_DATE_SEL, q_end)

    # 3. 조회 버튼 클릭 → 결과 로딩 대기
    log.step("조회하기")
    query_btn = page.locator("button.btn_date_check").first
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            await query_btn.click()
    except Exception:
        log.debug("네비게이션 미감지 → networkidle 대기로 폴백")
        await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)

    # 4. 엑셀 다운로드
    log.step("엑셀 다운로드")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    async with page.expect_download() as download_info:
        await page.locator("span.js_order_excel").first.click()

    download = await download_info.value
    filename = date.today().strftime("%y%m%d") + "_파라브로_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        await download.save_as(str(dest))
    except PermissionError:
        # 기존 파일이 엑셀 등에서 열려 있어 잠긴 경우 → 타임스탬프 붙여 다른 이름으로 저장
        alt = DOWNLOAD_DIR / (
            datetime.now().strftime("%y%m%d_%H%M%S") + "_파라브로_매입금.xlsx"
        )
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await download.save_as(str(dest))

    # 5. HTML 다운로드를 정상 xlsx 로 변환
    _normalize_download(dest)

    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

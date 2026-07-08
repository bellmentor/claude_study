"""베어B2B(고도몰 관리자) 주문통합리스트 조회 및 엑셀 다운로드.

고도몰 관리자 특성 (2026-07 실측):
  - 직접 URL 이동(goto)은 ERR_BLOCKED_BY_RESPONSE 로 차단됨 → 반드시 메뉴 링크 클릭으로 이동.
  - PG 안내 팝업 오버레이가 일반 클릭을 가로챔 → 모든 클릭은 JS(el.click())로 수행.
  - 엑셀은 [엑셀 버튼 → 레이어에서 양식 선택 → 요청 → 서버 생성 대기 → 다운로드] 2단계 방식.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

from dome_site.logger import SiteLogger
from .session import get_page

DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"

MENU_ORDER_SEL = "#menu_order"  # 상단 GNB '주문/배송' → /order/order_list_all.php
EXCEL_FORM_TITLE = "정산"  # 다운로드 양식명에 포함될 키워드 (실제 양식명: '정산용')

# 정산용 양식은 개인정보 컬럼이 많아 비밀번호 설정이 필수 (영문/숫자/특수문자 2종, 10~16자).
# 다운로드 직후 msoffcrypto 로 복호화해 평문 xlsx 로 저장하므로 고정값을 쓴다.
EXCEL_PASSWORD = "bearb2b2026!@"

log = SiteLogger("베어B2B")


async def _js_click(page, selector: str) -> None:
    """오버레이(PG 팝업 등)를 무시하고 요소를 JS 로 클릭한다."""
    await page.eval_on_selector(selector, "el => el.click()")


async def _goto_order_list(page) -> None:
    """주문통합리스트로 이동한다 (메뉴 클릭 방식, 깨진 탭이면 reload 복구)."""
    if "order_list_all.php" in page.url:
        # 이미 리스트에 있으면 초기 상태로 리셋하기 위해 메뉴를 다시 클릭
        pass

    # 메뉴가 없으면(에러 페이지 등) reload 로 복구
    if await page.locator(MENU_ORDER_SEL).count() == 0:
        log.debug("관리자 메뉴가 없어 reload 로 복구 시도")
        await page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(2)
    await page.locator(MENU_ORDER_SEL).first.wait_for(state="attached", timeout=20000)

    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
            await _js_click(page, MENU_ORDER_SEL)
    except Exception:
        log.debug("메뉴 클릭 네비게이션 미감지 → 현재 URL 확인")
    if "order_list_all.php" not in page.url:
        raise RuntimeError(f"주문통합리스트 진입 실패 (현재: {page.url})")


async def _set_search_conditions(page, start_date: str, end_date: str) -> None:
    """조회 기간(주문일 기준)과 결제수단(예치금만)을 설정한다."""
    # 기간 기준: 주문일 (첫 옵션 o.regDt 가 기본값이지만 명시적으로 지정)
    await page.eval_on_selector(
        "#treatDateFl",
        """el => {
            el.value = 'o.regDt';
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
    )

    # 기간 입력 (treatDate[] 2개: 시작/끝)
    await page.evaluate(
        """([start, end]) => {
            const els = document.querySelectorAll('input[name="treatDate[]"]');
            if (els.length < 2) throw new Error('treatDate 입력칸이 2개가 아님: ' + els.length);
            els[0].value = start;
            els[1].value = end;
            for (const el of [els[0], els[1]]) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        [start_date, end_date],
    )

    # 결제수단: 전체 해제 → 예치금(gd)만 체크
    await page.evaluate(
        """() => {
            const boxes = document.querySelectorAll('input[name="settleKind[]"]');
            for (const b of boxes) b.checked = (b.value === 'gd');
            const gd = document.querySelector('input[name="settleKind[]"][value="gd"]');
            if (!gd) throw new Error('예치금(gd) 체크박스를 찾지 못함');
            gd.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
    )
    log.debug(f"조회 조건 설정: 주문일 {start_date}~{end_date}, 결제수단=예치금만")


async def _submit_search(page) -> None:
    """검색 버튼을 눌러 조회한다."""
    sel = 'input[type="submit"][value="검색"]'
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            await _js_click(page, sel)
    except Exception:
        log.debug("검색 네비게이션 미감지 → networkidle 대기로 폴백")
        await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1)


async def _request_excel(page) -> str:
    """엑셀 레이어를 열고 양식(정산용)을 골라 생성을 요청한다. 요청한 고유 파일명 반환."""
    # 1) 엑셀 버튼 클릭 → 레이어 열림
    await page.locator("button.js-excel-download").first.wait_for(state="attached", timeout=20000)
    await _js_click(page, "button.js-excel-download")

    # 2) 양식 목록(AJAX)이 채워질 때까지 대기
    form_sel = 'select[name="formSno"]'
    for _ in range(20):
        count = await page.locator(f"{form_sel} option").count()
        if count > 1:
            break
        await asyncio.sleep(0.5)
    else:
        raise RuntimeError("엑셀 양식 목록이 로드되지 않았습니다")

    # 3) '정산금' 포함 양식 선택
    picked = await page.evaluate(
        """(kw) => {
            const sel = document.querySelector('select[name="formSno"]');
            const opts = Array.from(sel.options);
            let opt = opts.find(o => (o.textContent || '').includes(kw));
            if (!opt) return null;
            sel.value = opt.value;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            return (opt.textContent || '').trim();
        }""",
        EXCEL_FORM_TITLE,
    )
    if picked is None:
        titles = await page.eval_on_selector_all(
            f"{form_sel} option", "els => els.map(o => o.textContent.trim())"
        )
        raise RuntimeError(f"'{EXCEL_FORM_TITLE}' 양식을 찾지 못했습니다. 양식 목록: {titles}")
    log.info(f"엑셀 양식 선택: {picked}")

    # 4) 고유 파일명 + 필수 비밀번호 입력 (정산용 양식은 개인정보 포함 → 비밀번호 필수)
    unique_title = "정산용_" + datetime.now().strftime("%y%m%d_%H%M%S")
    await page.evaluate(
        """([title, pw]) => {
            const name = document.querySelector('input[name="downloadFileName"]');
            if (name) {
                name.value = title;
                name.dispatchEvent(new Event('input', { bubbles: true }));
            }
            for (const sel of ['input[name="password"]', 'input[name="rePassword"]']) {
                const el = document.querySelector(sel);
                if (!el) throw new Error(sel + ' 를 찾지 못함');
                el.value = pw;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        [unique_title, EXCEL_PASSWORD],
    )
    log.debug(f"파일명: {unique_title} / 비밀번호 설정 완료")

    # 5) 요청 버튼 클릭 (생성 시작)
    await _js_click(page, 'input[type="submit"][value="요청"]')
    await asyncio.sleep(1)
    return unique_title


async def _select_download_reason(page) -> str | None:
    """'엑셀 다운로드 사유' 모달이 떠 있으면 첫 사유를 선택하고 확인을 누른다."""
    return await page.evaluate(
        """() => {
            // 보이는 셀렉트 중 기본옵션이 '사유 선택' 인 것 = 사유 모달의 셀렉트
            const sels = Array.from(document.querySelectorAll('select')).filter(
                s => s.offsetParent !== null && (s.options[0]?.textContent || '').includes('사유')
            );
            const target = sels[0];
            if (!target || target.options.length < 2) return null;
            target.selectedIndex = 1;  // 첫 실제 사유
            target.dispatchEvent(new Event('change', { bubbles: true }));
            const reason = (target.options[1].textContent || '').trim();
            // 모달 안의 '확인' 버튼 클릭 (셀렉트에서 위로 올라가며 탐색)
            let node = target;
            for (let i = 0; i < 10 && node; i++) {
                node = node.parentElement;
                if (!node) break;
                const btn = Array.from(node.querySelectorAll('button, input[type="button"], a')).find(
                    b => (b.textContent || b.value || '').trim() === '확인' && b.offsetParent !== null
                );
                if (btn) { btn.click(); return reason; }
            }
            return null;
        }""",
    )


def _normalize_download(dest: Path) -> None:
    """다운로드 파일을 pandas 가 바로 읽을 수 있는 진짜 xlsx 로 변환한다.

    고도몰 엑셀 다운로드는 [비밀번호 ZIP 안에 HTML 테이블(.xls)] 구조다 (2026-07 실측).
    ZIP 이면 요청 때 설정한 비밀번호로 내부 파일을 꺼내고, HTML 테이블이면 파싱해
    진짜 xlsx 로 덮어쓴다. 이미 정상 xlsx 면 그대로 둔다.
    """
    import io
    import zipfile

    import pandas as pd

    data = dest.read_bytes()

    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if "[Content_Types].xml" in names:
                return  # 진짜 xlsx (zip 컨테이너) — 변환 불필요
            # 고도몰 비밀번호 ZIP → 내부 파일 추출
            data = z.read(z.infolist()[0], pwd=EXCEL_PASSWORD.encode())
        log.debug("비밀번호 ZIP 추출 완료")

    if data.lstrip()[:1] == b"<":
        # HTML 테이블 → 진짜 xlsx 로 변환
        df = pd.read_html(io.BytesIO(data), header=0)[0]
        df.to_excel(dest, index=False)
        log.debug(f"HTML 테이블을 xlsx 로 변환 (행 {len(df)}건)")
    else:
        dest.write_bytes(data)


async def _download_generated(page, title: str) -> Path:
    """내가 요청한 파일명(title) 행의 생성 완료를 기다렸다가 다운로드해 저장한다."""
    # 내 파일명 행이 나타나고 '생성완료' 가 될 때까지 대기
    row = page.locator("#tblExcelRequest tbody tr", has_text=title)
    for _ in range(60):  # 최대 2분
        if await row.count() > 0 and "생성완료" in await row.first.inner_text():
            break
        await asyncio.sleep(2)
    else:
        raise RuntimeError(f"엑셀 생성이 제한시간(2분) 안에 완료되지 않았습니다 (파일명: {title})")

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    async with page.expect_download(timeout=60000) as download_info:
        await row.first.locator(".js-excel-request-download").first.evaluate("el => el.click()")
        # '엑셀 다운로드 사유' 모달 처리 (사유 선택 후 확인 → 다운로드 시작)
        await asyncio.sleep(1.5)
        reason = await _select_download_reason(page)
        if reason:
            log.debug(f"다운로드 사유 선택: {reason}")
    download = await download_info.value

    filename = date.today().strftime("%y%m%d") + "_베어B2B_매입금.xlsx"
    dest = DOWNLOAD_DIR / filename
    try:
        await download.save_as(str(dest))
    except PermissionError:
        alt = DOWNLOAD_DIR / (datetime.now().strftime("%y%m%d_%H%M%S") + "_베어B2B_매입금.xlsx")
        log.warn(f"기존 파일이 열려있어(잠김) 다른 이름으로 저장합니다: {alt.name}")
        dest = alt
        await download.save_as(str(dest))

    # 비밀번호 ZIP/HTML → 진짜 xlsx 변환 (pandas 가 바로 읽을 수 있게)
    _normalize_download(dest)
    return dest


async def fetch_orders(start_date: str, end_date: str) -> Path:
    """주문통합리스트에서 예치금 주문을 조회하고 '전체(정산금)' 엑셀을 다운로드한다."""
    page = await get_page()

    log.step("주문통합리스트 이동")
    await _goto_order_list(page)

    log.step("조회 조건 설정", f"{start_date} ~ {end_date} / 예치금만")
    await _set_search_conditions(page, start_date, end_date)

    log.step("검색")
    await _submit_search(page)

    log.step("엑셀 생성 요청", f"양식: {EXCEL_FORM_TITLE}")
    title = await _request_excel(page)

    log.step("엑셀 다운로드")
    dest = await _download_generated(page, title)

    log.success(f"엑셀 다운로드 완료: {dest}")
    return dest

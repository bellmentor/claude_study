"""오너클랜 실시간 매입가/매입배송비 조회 ("그때그때" 탭 전용 신규 오퍼레이션).

'DB 다운로드'(https://ownerclan.com/V2/service/productDownload.php) 에서
"판매자관리코드로 검색"(is_search_selfcode=Y) + "플레이오토" 양식으로 세트를
만들면, 요청한 코드들의 현재가를 담은 엑셀 하나를 통째로 받을 수 있다.
플레이오토 양식 컬럼 중 `업체상품코드`(=판매자관리코드) / `표준공급가`(매입가) /
`배송비`(매입배송비) 를 그대로 쓴다.

⚠ 처음엔 상품상세 페이지(view.php?selfcode=)를 코드 하나씩 순회 조회하도록
만들었는데, 상품이 수천 개 규모(실측 3,600개+)라 순차/병렬 방문 모두 오너클랜의
Cloudflare 레이트리밋(Error 1015, 접속 임시 차단)에 걸렸다. DB 다운로드는 세트
하나당 요청 몇 번(생성→완료대기→다운로드)이면 끝나 이 문제 자체가 없다.

메인 웹은 subprocess(`python -m dome_site.ownerclan.product_price <입력.json> <출력.json>`)
로 이 파일을 직접 실행한다 — uvicorn 프로세스 안에서 Playwright를 import할 수
없기 때문(CLAUDE.md Web UI 연동 규칙). 그래서 다른 오퍼레이션 파일과 달리
이 파일에도 `__main__` 진입점을 둔다.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dome_site.logger import SiteLogger
from .login import login
from .session import MODE, close_session, get_context, get_page

SITE_LABEL = "오너클랜"
BASE_URL = "https://ownerclan.com"
DOWNLOAD_LIST_URL = f"{BASE_URL}/V2/service/productDownloadList.php"
DOWNLOAD_FORM_URL = f"{BASE_URL}/V2/service/productDownload.php"
FORM_ENTER_BUTTON = 'img[src*="product-download-button_new.png"]'

DB_DOWNLOAD_DIR = Path(__file__).resolve().parent / "db_downloads"

NAV_TIMEOUT = 30000  # ms
SET_READY_TIMEOUT_SEC = 900  # 상품 수천 개 규모라 여유있게 잡는다
SET_READY_POLL_SEC = 5

log = SiteLogger(SITE_LABEL)


def _abs_url(href: str) -> str:
    """상대경로 href 를 절대 URL 로 만든다."""
    if href.startswith("http"):
        return href
    return BASE_URL.rstrip("/") + "/" + href.lstrip("/")


def _to_int(value) -> int | None:
    """숫자류 셀 값을 정수로. 빈 값/실패는 None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


# ── 세트 생성 ───────────────────────────────────────────────
async def _open_create_form(page) -> None:
    """DB다운로드 세트 생성 폼을 연다. 직접 이동 실패 시 목록의 '세트 만들기' 버튼을 누른다."""
    await page.goto(DOWNLOAD_FORM_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    if await page.locator('input[name="solution"]').count() > 0:
        return

    await page.goto(DOWNLOAD_LIST_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    btn = page.locator(FORM_ENTER_BUTTON).first
    await btn.wait_for(state="visible", timeout=NAV_TIMEOUT)
    await btn.click(timeout=NAV_TIMEOUT)
    await page.locator('input[name="solution"]').first.wait_for(state="visible", timeout=NAV_TIMEOUT)


async def _fill_title(page, title: str) -> None:
    """세트제목 입력칸을 후보 셀렉터로 찾아 채운다. 못 찾아도 진행에는 지장 없다(양식종류로 최신 행을 찾음)."""
    for sel in (
        'input[name="set_title"]', 'input[name="title"]',
        'input#set_title', 'input#title', 'input[name="download_title"]',
    ):
        loc = page.locator(sel)
        if await loc.count() > 0:
            try:
                await loc.first.fill(title)
                return
            except Exception:
                continue
    log.warn("세트제목 입력칸을 찾지 못해 제목 없이 진행합니다(양식종류로 최신 세트를 찾음)")


async def _create_selfcode_set(page, codes: list[str], title: str) -> None:
    """PLAYAUTO 양식 + '판매자관리코드로 검색'으로 세트를 만든다."""
    await _open_create_form(page)
    await _fill_title(page, title)

    await page.locator('input[name="solution"][value="PLAYAUTO"]').first.check()
    await page.wait_for_timeout(300)

    await page.locator('input[name="is_search_selfcode"][value="Y"]').first.check()
    await page.wait_for_timeout(300)

    ta = page.locator('textarea#search_selfcode[name="search_selfcode"]').first
    await ta.wait_for(state="visible", timeout=NAV_TIMEOUT)
    await ta.fill("\n".join(codes))
    await page.wait_for_timeout(400)

    log.step("세트 생성", f"'다운로드세트 만들기' 클릭 ({len(codes)}개 코드, 확인창 자동 처리)")
    await page.locator("button#btn_submit2").first.click(timeout=NAV_TIMEOUT)

    # 제출 후 alert 확인창이 2개 뜬다 — page.on("dialog") 핸들러가 자동 수락한다.
    await page.wait_for_timeout(3000)
    try:
        await page.wait_for_url(lambda u: "productDownloadList.php" in u, timeout=NAV_TIMEOUT)
    except Exception:
        await page.goto(DOWNLOAD_LIST_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)


# ── 완료 대기 ───────────────────────────────────────────────
async def _find_top_row_idx(page) -> str | None:
    """목록에서 '플레이오토' 양식의 맨 위(가장 최근) 행 idx 를 반환한다."""
    rows = page.locator('table#soldoutListTable tbody#tblBody tr[id^="listRow"]')
    count = await rows.count()
    for i in range(count):
        row = rows.nth(i)
        try:
            row_text = (await row.locator("td").first.inner_text()).strip()
        except Exception:
            continue
        if "플레이오토" in row_text:
            row_id = await row.get_attribute("id") or ""
            m = re.search(r"listRow(\d+)", row_id)
            if m:
                return m.group(1)
    return None


async def _row_is_done(page, idx: str) -> bool:
    """해당 idx 행의 작업상태가 '작업완료'인지 확인한다."""
    row = page.locator(f"tr#listRow{idx}")
    if await row.count() == 0:
        return False
    try:
        text = await row.inner_text()
    except Exception:
        return False
    return "작업완료" in text


async def _wait_set_ready(page, title: str) -> str:
    """목록을 새로고침하며 방금 만든 세트가 '작업완료'가 될 때까지 대기, idx 반환."""
    deadline = time.time() + SET_READY_TIMEOUT_SEC
    idx = None
    while time.time() < deadline:
        await page.goto(DOWNLOAD_LIST_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        idx = await _find_top_row_idx(page)
        if idx and await _row_is_done(page, idx):
            return idx
        remaining = int(deadline - time.time())
        log.step("작업완료 대기", f"idx={idx}, 남은시간 {remaining}s")
        await page.wait_for_timeout(SET_READY_POLL_SEC * 1000)
    raise RuntimeError(f"'{title}' 세트가 시간 내에 작업완료되지 않았습니다.")


# ── 다운로드 + 압축해제 ────────────────────────────────────
async def _download_set(context, page, idx: str) -> list[Path]:
    """세트의 다운로드(zip)를 받아 저장·압축해제한다. 추출된 엑셀 경로 리스트 반환."""
    span = page.locator(f"span#downloadSpan{idx}").first
    await span.wait_for(state="visible", timeout=NAV_TIMEOUT)
    await span.click()
    await page.wait_for_timeout(800)

    link_sel = f'a[href*="downloadServer.php?idx={idx}"]'
    try:
        await page.locator(link_sel).first.wait_for(state="visible", timeout=NAV_TIMEOUT)
    except Exception:
        await span.click()
        await page.locator(link_sel).first.wait_for(state="visible", timeout=NAV_TIMEOUT)

    links = page.locator(link_sel)
    n = await links.count()
    hrefs = []
    for i in range(n):
        href = await links.nth(i).get_attribute("href")
        if href:
            hrefs.append(_abs_url(href))
    if not hrefs:
        raise RuntimeError("다운로드 링크를 찾지 못했습니다.")

    day_dir = DB_DOWNLOAD_DIR / datetime.now().strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    xls_files: list[Path] = []
    for seq, url in enumerate(hrefs, start=1):
        resp = await context.request.get(url, timeout=NAV_TIMEOUT)
        if not resp.ok:
            raise RuntimeError(f"다운로드 실패(HTTP {resp.status}): {url}")
        body = await resp.body()

        zip_path = day_dir / f"febstore_selfcode_{idx}_seq{seq}.zip"
        zip_path.write_bytes(body)
        log.info(f"저장: {zip_path}")

        if body[:4] != b"PK\x03\x04":
            xls_files.append(zip_path)
            continue

        out_dir = day_dir / zip_path.stem
        out_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                try:
                    name = name.encode("cp437").decode("cp949")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                target = out_dir / re.sub(r'[\\/:*?"<>|]', "_", name)
                with zf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                if target.suffix.lower() in (".xls", ".xlsx"):
                    xls_files.append(target)

    if not xls_files:
        raise RuntimeError("압축 해제 후 엑셀을 찾지 못했습니다.")
    return xls_files


def _parse_playauto_files(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """플레이오토 양식 엑셀들에서 업체상품코드별 표준공급가/배송비를 읽는다.

    배송비 컬럼에 999999 가 찍히는 상품들이 있다 — 오너클랜 상품상세 페이지에서
    직접 확인해보니 이 값은 실제 금액이 아니라 "개별배송 착불"(택배비가 고정이
    아니라 수취인 부담/건별 산정이라 확정 금액이 없음)의 자리표시 값이었다.
    그대로 보여주면 매입배송비가 99만원인 것처럼 보이는 오해를 줘서, 이 경우는
    금액 없이 문구로만 표시한다.
    """
    SHIP_UNSET_SENTINEL = 999999

    lookup: dict[str, dict[str, Any]] = {}
    for p in paths:
        try:
            df = pd.read_excel(p, dtype=object)
        except Exception as e:
            log.warn(f"{p} 읽기 실패: {e}")
            continue
        if "업체상품코드" not in df.columns:
            continue
        cost_col = "표준공급가" if "표준공급가" in df.columns else None
        ship_col = "배송비" if "배송비" in df.columns else None
        for _, row in df.iterrows():
            code = row.get("업체상품코드")
            if code is None or (isinstance(code, float) and pd.isna(code)):
                continue
            code = str(code).strip()

            cost_ship = _to_int(row.get(ship_col)) if ship_col else None
            ship_note = ""
            if cost_ship == SHIP_UNSET_SENTINEL:
                cost_ship = None
                ship_note = "개별배송 착불(금액 미확정)"

            lookup[code] = {
                "cost": _to_int(row.get(cost_col)) if cost_col else None,
                "cost_ship": cost_ship,
                "ship_note": ship_note,
            }
    return lookup


# ── 메인 ────────────────────────────────────────────────────
async def search_prices(codes: list[str]) -> dict[str, dict[str, Any]]:
    """오너클랜 DB다운로드(판매자관리코드 검색)로 코드별 매입가/매입배송비를 한 번에 조회한다."""
    page = await get_page()
    context = await get_context()
    page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

    title = f"그때그때_페브스토어_{datetime.now():%Y%m%d_%H%M%S}"
    log.step("DB다운로드 세트 생성", f"{len(codes)}개 코드")
    await _create_selfcode_set(page, codes, title)

    idx = await _wait_set_ready(page, title)
    log.success(f"세트 준비 완료 (idx={idx})")

    xls_files = await _download_set(context, page, idx)
    log.info(f"다운로드 완료: {[str(p) for p in xls_files]}")

    lookup = _parse_playauto_files(xls_files)

    results: dict[str, dict[str, Any]] = {}
    for code in codes:
        found = lookup.get(code)
        if found is None:
            results[code] = {"cost": None, "cost_ship": None, "ship_note": "", "error": "조회 실패(상품 없음)"}
        else:
            results[code] = {
                "cost": found["cost"],
                "cost_ship": found["cost_ship"],
                "ship_note": found.get("ship_note", ""),
                "error": "",
            }

    matched = sum(1 for r in results.values() if not r["error"])
    log.success(f"매입가 조회 완료: {len(codes)}개 중 {matched}개 성공")
    return results


async def _run_batch(input_path: Path, output_path: Path) -> int:
    codes = json.loads(input_path.read_text(encoding="utf-8"))
    ok = await login()
    if not ok:
        output_path.write_text(
            json.dumps({"__error__": "로그인 실패"}, ensure_ascii=False), encoding="utf-8"
        )
        return 1

    results = await search_prices(codes)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


async def _standalone(input_path: Path, output_path: Path) -> int:
    try:
        return await _run_batch(input_path, output_path)
    finally:
        if MODE == "debug" and not os.environ.get("WEBUI"):
            print("\n[debug] 브라우저 창을 확인하세요. Enter 키를 누르면 종료합니다...")
            await asyncio.to_thread(input)
        await close_session()


if __name__ == "__main__":
    _input = Path(sys.argv[1])
    _output = Path(sys.argv[2])
    sys.exit(asyncio.run(_standalone(_input, _output)))

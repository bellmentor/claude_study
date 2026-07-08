"""베어B2B(고도몰 관리자) Playwright 세션 관리 — CDP 연결 방식.

다른 도매처와 달리 관리자 로그인을 자동화하지 않는다. 대신:
  1) 전용 프로필 Chrome 을 원격 디버그 포트(9222)로 실행하고
  2) 사용자가 그 창에서 직접 로그인한다 (최초 1회, 세션은 프로필에 유지)
  3) 봇은 connect_over_cdp 로 '연결'만 해서 크롤링한다.

작업이 끝나도 사용자 브라우저는 닫지 않는다. Playwright 연결만 종료한다.
기준 참고: 기타/bearb2b_관리페이지 크롤링 방법 참고용/ (chrome_launcher.py, godomall_bot.py)
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

# 사이트별 실행 모드. CDP 방식은 사용자 Chrome 에 붙으므로 headless 개념이 없지만,
# 단독 실행 시 Enter 대기 여부 등 관례 유지를 위해 둔다.
MODE = "debug"

CDP_PORT = 9222
# localhost 는 IPv6(::1) 로 풀려 연결이 거부될 수 있으므로 127.0.0.1 로 고정한다.
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

# 자동화 전용 Chrome 프로필. 평소 프로필은 기존 Chrome 이 떠 있으면 디버그 포트가
# 안 열리는 충돌이 있어 별도 프로필을 쓴다. 로그인 세션은 이 프로필에 유지된다.
USER_DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "godo_macro_chrome"
)

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

_state: dict[str, Any] = {
    "playwright": None,
    "browser": None,
    "context": None,
    "page": None,
}


def _find_chrome() -> str | None:
    """설치된 chrome.exe 경로를 반환한다. 없으면 None."""
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None


def _launch_chrome() -> None:
    """전용 프로필 Chrome 을 디버그 포트로 실행한다. (이미 떠 있으면 새 창만 열림)"""
    chrome = _find_chrome()
    if chrome is None:
        raise RuntimeError("chrome.exe 를 찾지 못했습니다. session.py 의 CHROME_PATHS 를 확인하세요.")
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    subprocess.Popen([
        chrome,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
    ])


async def _try_connect(pw: Playwright, attempts: int, delay: float) -> Browser | None:
    """CDP 연결을 attempts 회 재시도한다. 실패하면 None."""
    for _ in range(attempts):
        try:
            return await pw.chromium.connect_over_cdp(CDP_URL)
        except Exception:
            await asyncio.sleep(delay)
    return None


def _pick_admin_page(pages: list[Page]) -> Page | None:
    """열린 탭 중 고도몰 관리자(godomall.com) 탭을 우선 반환한다. 없으면 None."""
    for pg in pages:
        try:
            if "godomall.com" in pg.url:
                return pg
        except Exception:
            continue
    return None


async def open_session() -> Page:
    """디버그 Chrome 에 CDP 로 연결하고 사용 가능한 Page 를 반환한다.

    Chrome 이 안 떠 있으면 전용 프로필로 자동 실행한 뒤 연결한다.
    이미 연결돼 있으면 기존 Page 반환.
    """
    page: Page | None = _state["page"]
    if page is not None:
        return page

    pw: Playwright = await async_playwright().start()

    # 1차: 이미 떠 있는 디버그 Chrome 에 연결 시도
    browser = await _try_connect(pw, attempts=2, delay=0.5)
    if browser is None:
        # 없으면 전용 프로필 Chrome 을 띄우고 다시 연결
        _launch_chrome()
        browser = await _try_connect(pw, attempts=10, delay=1.0)
    if browser is None:
        await pw.stop()
        raise RuntimeError(
            "디버그 Chrome(포트 9222) 연결에 실패했습니다. "
            "다른 Chrome 이 이미 이 프로필을 쓰고 있는지 확인하세요."
        )

    if not browser.contexts:
        await pw.stop()
        raise RuntimeError("열린 브라우저 컨텍스트가 없습니다. Chrome 창을 확인하세요.")
    context: BrowserContext = browser.contexts[0]

    pages = context.pages
    new_page = _pick_admin_page(pages) or (pages[0] if pages else await context.new_page())

    # JS alert/confirm 팝업은 자동 수락
    new_page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    _state.update(playwright=pw, browser=browser, context=context, page=new_page)
    return new_page


async def get_page() -> Page:
    """살아있는 Page 를 반환한다. 세션이 없으면 자동으로 새로 연다."""
    page: Page | None = _state["page"]
    if page is None:
        return await open_session()
    return page


def get_context() -> BrowserContext | None:
    """현재 연결된 BrowserContext 를 반환한다 (탭 탐색용). 연결 전이면 None."""
    return _state["context"]


def set_page(page: Page) -> None:
    """작업 대상 Page(탭)를 교체한다. 관리자 탭이 새 창으로 열렸을 때 사용."""
    page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))
    _state["page"] = page


async def close_session() -> None:
    """Playwright 연결만 종료한다. 사용자 Chrome 창은 닫지 않는다."""
    pw: Playwright | None = _state["playwright"]
    if pw is not None:
        try:
            await pw.stop()
        except Exception:
            pass
    _state.update(playwright=None, browser=None, context=None, page=None)

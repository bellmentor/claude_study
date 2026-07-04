"""히트가구 Playwright 세션 관리.

같은 도매처(히트가구) 안의 모든 오퍼레이션은 이 모듈에 보관된 단일 브라우저 세션을 공유한다.
세션을 중간에 닫고 다시 열지 않는다 (로그인 쿠키 유실 방지).
다른 도매처로 전환할 때만 `close_session()` 을 호출한다.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

# 사이트별 실행 모드. "debug" = 브라우저 창 표시(개발/디버깅용), "release" = headless(속도 우선).
# 사이트가 안정화되기 전까지는 "debug" 로 둔다.
MODE = "debug"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_state: dict[str, Any] = {
    "playwright": None,
    "browser": None,
    "context": None,
    "page": None,
}


async def open_session() -> Page:
    """브라우저 세션을 시작하고 사용 가능한 Page 를 반환한다. 이미 열려있으면 기존 Page 반환.

    헤드리스 여부는 모듈 상수 `MODE` 로 결정한다 ("debug" → 창 표시, "release" → headless).
    """
    page: Page | None = _state["page"]
    if page is not None:
        return page

    pw: Playwright = await async_playwright().start()
    browser: Browser = await pw.chromium.launch(headless=(MODE == "release"))
    context: BrowserContext = await browser.new_context(user_agent=_USER_AGENT)
    new_page: Page = await context.new_page()
    _state.update(playwright=pw, browser=browser, context=context, page=new_page)
    return new_page


async def get_page() -> Page:
    """살아있는 Page 를 반환한다. 세션이 없으면 자동으로 새로 연다."""
    page: Page | None = _state["page"]
    if page is None:
        return await open_session()
    return page


async def close_session() -> None:
    """세션 종료. 다른 도매처로 전환할 때만 호출한다. 같은 도매처 작업 중에는 호출 금지."""
    browser: Browser | None = _state["browser"]
    pw: Playwright | None = _state["playwright"]
    if browser is not None:
        await browser.close()
    if pw is not None:
        await pw.stop()
    _state.update(playwright=None, browser=None, context=None, page=None)

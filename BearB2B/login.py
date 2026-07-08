"""베어B2B(고도몰 관리자) 로그인 확인.

CDP 방식이라 로그인을 자동화하지 않는다. 이 모듈은:
  1) 열린 탭 중 고도몰 관리자(godomall.com) 탭을 찾고
  2) 없으면 통합 로그인 페이지를 띄운 뒤 사용자가 직접 로그인/관리자 진입할 때까지 대기한다.
"""

from __future__ import annotations

import asyncio
import sys

from dome_site.logger import SiteLogger
from .session import MODE, close_session, get_context, get_page, set_page

LOGIN_URL = "https://accounts.godo.co.kr/login"
ADMIN_HOST_KEYWORD = "godomall.com"
WAIT_LOGIN_SEC = 600  # 사용자 직접 로그인 최대 대기 (10분)

log = SiteLogger("베어B2B")


def _find_admin_page():
    """열린 탭 중 관리자(godomall.com) 탭을 반환. 없으면 None."""
    context = get_context()
    if context is None:
        return None
    for pg in context.pages:
        try:
            if ADMIN_HOST_KEYWORD in pg.url:
                return pg
        except Exception:
            continue
    return None


async def login() -> bool:
    """고도몰 관리자 접속 확인 (미로그인 시 사용자 직접 로그인 대기)."""
    log.step("관리자 접속 확인")
    page = await get_page()

    # 1) 이미 관리자 탭이 있으면 그대로 사용
    admin = _find_admin_page()
    if admin is not None:
        set_page(admin)
        log.success(f"관리자 탭 확인: {admin.url}")
        return True

    # 2) 없으면 통합 로그인 페이지를 띄우고 사용자에게 안내
    log.info("관리자 탭이 없습니다. 로그인 페이지를 엽니다.")
    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    except Exception as e:
        log.warn(f"로그인 페이지 이동 실패(무시): {e}")

    log.warn("Chrome 창에서 [고도몰 로그인] 후 [쇼핑몰 관리자] 로 들어가 주세요. (최대 10분 대기)")

    # 3) 관리자 탭이 생길 때까지 폴링
    for _ in range(WAIT_LOGIN_SEC // 2):
        await asyncio.sleep(2)
        admin = _find_admin_page()
        if admin is not None:
            set_page(admin)
            log.success(f"관리자 접속 확인: {admin.url}")
            return True

    log.error("제한 시간 안에 관리자 접속이 확인되지 않았습니다.")
    return False


async def _standalone() -> int:
    """단독 실행: 로그인 확인만 수행."""
    import os

    try:
        ok = await login()
        if MODE == "debug" and not os.environ.get("WEBUI"):
            print("\n[debug] 브라우저 창을 확인하세요. Enter 키를 누르면 종료합니다...")
            await asyncio.to_thread(input)
        return 0 if ok else 1
    finally:
        await close_session()


if __name__ == "__main__":
    sys.exit(asyncio.run(_standalone()))

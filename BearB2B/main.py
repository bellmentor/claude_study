"""베어B2B(고도몰) 전체 흐름: 관리자 접속 확인 → 주문통합리스트 엑셀 다운로드 → 매입금 합산."""

from __future__ import annotations

import asyncio
import calendar
import sys

from dome_site.logger import SiteLogger
from .login import login
from .orders import fetch_orders
from .session import MODE, close_session, get_page
from .summarize import summarize_purchase

log = SiteLogger("베어B2B")


async def run(year: int, month: int) -> int:
    """베어B2B 매입금 집계 전체 실행."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year}-{month:02d}-{last_day:02d}"

    log.flow_start(f"{year}년 {month}월 매입금 수집")

    try:
        ok = await login()
        if not ok:
            return 1

        dest = await fetch_orders(start, end)
        log.info(f"저장 경로: {dest}")

        log.step("매입금 합산")
        summarize_purchase(start)

        import os
        if MODE == "debug" and not os.environ.get("WEBUI"):
            print("\n[debug] 브라우저 창을 확인하세요. Enter 키를 누르면 종료합니다...")
            await asyncio.to_thread(input)

        log.flow_end()
        return 0
    except Exception as e:
        log.error(f"오류: {e}")
        try:
            page = await get_page()
            await log.dump_on_error(page, e)
        except Exception:
            pass
        return 1
    finally:
        await close_session()


if __name__ == "__main__":
    _year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    _month = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    sys.exit(asyncio.run(run(_year, _month)))

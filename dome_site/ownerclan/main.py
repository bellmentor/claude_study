"""오너클랜 전체 흐름: 로그인 → 주문조회/엑셀 다운로드 → 매입금 합산."""

from __future__ import annotations

import asyncio
import calendar
import sys

from .login import login
from .orders import fetch_orders
from .session import MODE, close_session
from .summarize import summarize_purchase


async def run(year: int, month: int) -> int:
    """오너클랜 매입금 집계 전체 실행."""
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year}-{month:02d}-{last_day:02d}"

    try:
        ok = await login()
        if not ok:
            print("[오너클랜] 로그인 실패")
            return 1

        dest = await fetch_orders(start, end)
        print(f"\n[오너클랜] 저장 경로: {dest}")

        summarize_purchase(start)

        if MODE == "debug":
            print("\n[debug] 브라우저 창을 확인하세요. Enter 키를 누르면 종료합니다...")
            await asyncio.to_thread(input)

        return 0
    except Exception as e:
        print(f"\n[오너클랜] 오류: {e}")
        return 1
    finally:
        await close_session()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(2026, 5)))

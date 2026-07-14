"""건아유통 집계 매입금 계산 — 일일마감자료 계행 C값을 기간별로 합산한다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .daily_ledger import LedgerDay, load_ledger_folder


def summarize_purchase(ledger_folder: Path, start_date: str, end_date: str) -> dict[str, Any]:
    """선택 기간(start_date~end_date, YYYY-MM-DD)에 해당하는 일일마감자료 계행 총액을 합산한다."""
    days = load_ledger_folder(ledger_folder)
    in_range = [d for d in days if d.date and start_date <= d.date <= end_date]
    in_range.sort(key=lambda d: d.date)

    error_days = [d for d in in_range if not d.valid]
    total = sum(d.total for d in in_range if d.valid)

    return {
        "total": total,
        "days": in_range,
        "error_days": error_days,
        "day_count": len(in_range),
        "error_count": len(error_days),
    }


def build_detail_excel(result: dict[str, Any]) -> bytes:
    """summarize_purchase() 결과를 품목별 상세표 엑셀 바이트로 만든다."""
    import io

    import pandas as pd

    rows: list[dict[str, Any]] = []
    for day in result.get("days", []):
        day: LedgerDay
        for item in day.items:
            rows.append(
                {
                    "날짜": day.date,
                    "상품명": item.name,
                    "수량": item.qty,
                    "단가": item.unit_price,
                    "금액": item.amount,
                    "검증상태": "정상" if day.valid else "; ".join(day.issues),
                }
            )

    summary = pd.DataFrame(
        [
            {"항목": "대상 일수", "값": result.get("day_count")},
            {"항목": "검증오류 일수", "값": result.get("error_count")},
            {"항목": "매입금 합계", "값": result.get("total")},
        ]
    )
    detail = pd.DataFrame(rows)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="건아유통_매입금", index=False, startrow=0)
        detail.to_excel(writer, sheet_name="건아유통_매입금", index=False, startrow=len(summary) + 2)
    return buf.getvalue()

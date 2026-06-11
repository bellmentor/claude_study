"""오너클랜 매입금 합산 → 도매_매입금.xlsx 에 기록."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"


def summarize_purchase(start_date: str) -> int:
    """최신 엑셀에서 총결제금액을 합산하고 도매_매입금.xlsx 에 행을 추가한다. 매입금(원) 반환.

    start_date: 조회 시작일 (YYYY-MM-DD). 여기서 월을 추출한다.
    """
    # 최신 다운로드 파일
    files = sorted(
        [f for f in DOWNLOADS_DIR.glob("*.xlsx") if not f.name.startswith("~")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("다운로드된 엑셀 파일이 없습니다")

    df = pd.read_excel(files[0])
    col = [c for c in df.columns if "결제금액" in c][0]
    total = int(df[col].sum())

    # 조회 기간 기준으로 월 추출
    yy, mm = start_date[2:4], start_date[5:7]
    month = f"{yy}년{mm}월"

    row = {"몇월": month, "도매사이트": "오너클랜", "매입금": total}

    # 기존 파일이 있으면 읽어서 추가, 없으면 새로 생성
    if SUMMARY_XLSX.exists():
        existing = pd.read_excel(SUMMARY_XLSX)
        # 같은 월+사이트 행이 있으면 갱신
        mask = (existing["몇월"] == month) & (existing["도매사이트"] == "오너클랜")
        if mask.any():
            existing.loc[mask, "매입금"] = total
            result = existing
        else:
            result = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        result = pd.DataFrame([row])

    result.to_excel(SUMMARY_XLSX, index=False)
    print(f"[오너클랜] {month} 매입금: {total:,}원 → {SUMMARY_XLSX}")
    return total


if __name__ == "__main__":
    summarize_purchase("2026-05-01")

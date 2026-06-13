"""젠트레이드 매입금 합산 → 도매_매입금.xlsx 에 기록."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

log = SiteLogger("젠트")


def summarize_purchase(start_date: str) -> int:
    """최신 엑셀에서 해당 월 매출금액을 찾아 도매_매입금.xlsx에 기록한다. 매입금(원) 반환."""
    files = sorted(
        [f for f in DOWNLOADS_DIR.glob("*.xlsx") if not f.name.startswith("~")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("다운로드된 엑셀 파일이 없습니다")

    log.debug(f"엑셀 파일: {files[0].name}")
    df = pd.read_excel(files[0])

    # start_date에서 대상 월 추출 ("2026-05-01" → "2026-05")
    target = start_date[:7]  # "2026-05"
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    # 날짜 컬럼에서 해당 월 행 찾기
    date_col = df.columns[0]
    amount_col = df.columns[1]  # 매출금액

    total = 0
    for idx, val in df[date_col].items():
        if target in str(val):
            raw = str(df.loc[idx, amount_col]).replace(",", "").replace(" ", "")
            total = int(raw)
            break

    if total == 0:
        log.warn(f"해당 월({target}) 데이터를 찾지 못했습니다")

    row = {"몇월": month_label, "도매사이트": "젠트", "매입금": total}

    if SUMMARY_XLSX.exists():
        existing = pd.read_excel(SUMMARY_XLSX)
        mask = (existing["몇월"] == month_label) & (existing["도매사이트"] == "젠트")
        if mask.any():
            existing.loc[mask, "매입금"] = total
            result = existing
        else:
            result = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        result = pd.DataFrame([row])

    result.to_excel(SUMMARY_XLSX, index=False)
    log.info(f"{month_label} 매입금: {total:,}원 → {SUMMARY_XLSX}")
    return total

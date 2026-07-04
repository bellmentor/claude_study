"""JTC코리아 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (프롬프트용.txt 기준):
  - '날짜' 에서 해당 월 주문만 남긴다.
  - 각 주문당 (가격 + 배송비 3,500원) 을 계산한다. (부가세 없음)
  - 모두 합하면 해당 월의 매입금.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

SITE_LABEL = "JTC코리아"
SHIPPING_FEE = 3500  # 주문당 배송비

log = SiteLogger(SITE_LABEL)


def _to_int(value) -> int:
    """'15,600원' / 15600.0 등을 정수로 변환. 실패 시 0. (소수점 뒤는 버려 10배 방지)"""
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    s = str(value).split(".")[0]
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _yyyymm(value) -> str:
    """날짜류 값에서 앞 6자리 숫자(YYYYMM)를 추출. 예: '2026/06/29' → '202606'."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:6]


def summarize_purchase(start_date: str) -> int:
    """최신 크롤링 파일에서 해당 월 매입금을 계산하고 도매_매입금.xlsx 에 기록. 매입금 반환.

    start_date: 조회 시작일 (YYYY-MM-DD). 여기서 대상 월을 추출한다.
    """
    files = sorted(
        [f for f in DOWNLOADS_DIR.glob("*.xlsx") if not f.name.startswith("~")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("크롤링된 파일이 없습니다")

    log.debug(f"파일: {files[0].name}")
    df = pd.read_excel(files[0])
    log.debug(f"컬럼: {list(df.columns)}")

    if "날짜" not in df.columns or "가격" not in df.columns:
        raise RuntimeError(f"컬럼(날짜/가격)을 찾지 못했습니다. 컬럼: {list(df.columns)}")

    target = _yyyymm(start_date)
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    n0 = len(df)
    df = df[df["날짜"].map(_yyyymm) == target]
    log.info(f"해당 월({target}) 필터: {n0}건 → {len(df)}건")

    # 각 주문당 (가격 + 배송비) 합산
    total = 0
    for price in df["가격"]:
        total += _to_int(price) + SHIPPING_FEE
    log.info(f"매입금(주문당 (가격+{SHIPPING_FEE}) 합) = {total:,}원 ({len(df)}건)")

    row = {"몇월": month_label, "도매사이트": SITE_LABEL, "매입금": total}

    if SUMMARY_XLSX.exists():
        existing = pd.read_excel(SUMMARY_XLSX)
        mask = (existing["몇월"] == month_label) & (existing["도매사이트"] == SITE_LABEL)
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


if __name__ == "__main__":
    _start = sys.argv[1] if len(sys.argv) > 1 else "2026-06-01"
    summarize_purchase(_start)

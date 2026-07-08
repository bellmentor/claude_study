"""베어B2B(고도몰) 매입금(정산금) 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (bearb2b_get.txt 기준, 베어6월.xlsx '작업용' 시트로 검증):
  - 한 주문에 상품행이 여러 개 있고 '사용된 총 예치금' 이 주문 단위로 반복 기재되므로,
    '주문 번호' 중복 행은 첫 행만 남긴다.
  - 주문상태에 취소/반품/교환/환불 이 포함된 행은 제외한다 (공용 drop_canceled).
  - 남은 행의 '사용된 총 예치금'("N,NNN원" 문자열) 을 합산하면 해당월 매입금.
  - 검증: 2026년 6월 = 1,301,700원.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from dome_site.order_filters import drop_canceled

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "dome_site" / "도매_매입금.xlsx"

SITE_LABEL = "베어B2B"

log = SiteLogger(SITE_LABEL)


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """컬럼명에 keywords 중 하나라도 포함된 첫 컬럼명을 반환. 없으면 None."""
    for col in df.columns:
        name = str(col)
        for kw in keywords:
            if kw in name:
                return col
    return None


def _to_int(value) -> int:
    """'5,000원' / 5000.0 등 다양한 표기를 정수로 변환. 실패 시 0."""
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    # 소수점 뒤는 버린다 ('12440.0' → '12440'). 안 그러면 '.0'의 0까지 붙어 10배가 된다.
    s = str(value).split(".")[0]
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def summarize_purchase(start_date: str) -> int:
    """최신 엑셀에서 매입금을 계산하고 도매_매입금.xlsx 에 기록한다. 매입금(원) 반환."""
    files = sorted(
        [f for f in DOWNLOADS_DIR.glob("*.xlsx") if not f.name.startswith("~")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("다운로드된 엑셀 파일이 없습니다")

    log.debug(f"엑셀 파일: {files[0].name}")
    df = pd.read_excel(files[0])
    n0 = len(df)

    order_col = _find_col(df, ["주문 번호", "주문번호"])
    if order_col is None:
        raise RuntimeError(f"주문번호 컬럼을 찾지 못했습니다. 엑셀 컬럼: {list(df.columns)}")

    deposit_col = _find_col(df, ["사용된 총 예치금"])
    if deposit_col is None:
        raise RuntimeError(f"'사용된 총 예치금' 컬럼을 찾지 못했습니다. 엑셀 컬럼: {list(df.columns)}")

    # 1. 주문번호 중복 행은 첫 행만 남긴다 (예치금이 주문 단위로 반복 기재됨)
    df = df.drop_duplicates(subset=order_col, keep="first")
    log.info(f"주문번호 중복 제거: {n0}건 → {len(df)}건")

    # 2. 주문상태에 취소/반품/교환/환불 포함 행 제외 (공용 필터)
    status_col = _find_col(df, ["주문상태", "배송상태", "상태"])
    df = drop_canceled(df, status_col, log=log)

    # 3. '사용된 총 예치금' 합산
    total = int(df[deposit_col].map(_to_int).sum())
    log.info(f"사용된 총 예치금 합계 ({len(df)}건): {total:,}원")

    # 조회 기간 기준으로 월 추출
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

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

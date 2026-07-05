"""3MRO 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (프롬프트용.txt 지시: "가격 부분 계산, (가격 × 개수) + 배송비(3천원)"):
  - '주문일자' 해당월 필터.
  - '주문상태' 취소류(취소/반품/교환/환불) 제외 (공용 drop_canceled).
    · 조회 단계에서 취소류 체크박스를 켜지 않아 대개 이미 없지만, 표준 일관성을 위해 명시 호출.
  - 매입금 = 상품금액 + 배송비
    · 상품금액 = 각 라인 (가격 × 수량) 합.
    · 배송비 = 송장번호 단위로 1건당 3,000원 (같은 송장=배송 1건, 송장 빈 값은 주문번호로 대체).
  ※ 엑셀의 '배송비' 컬럼은 값이 '선불'(텍스트)이라 금액이 아니므로 쓰지 않고, 고정 3,000원을 적용한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from dome_site.order_filters import drop_canceled

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

SITE_LABEL = "3MRO"

# 주문당 배송비 (고정)
SHIPPING_FEE = 3000

# 송장번호가 '비어있음'으로 간주되는 값(미출고 등). 이 경우 주문번호로 배송 그룹을 대체한다.
BLANK_INVOICE = ["", "nan", "None", "NaN", "-", "0", "0.0"]

log = SiteLogger(SITE_LABEL)


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """컬럼명을 keywords 로 찾는다. 정확 일치 우선, 없으면 부분 포함(공백 제거 후 비교)."""
    import re
    cols = [re.sub(r"\s+", "", str(c)) for c in df.columns]
    for kw in keywords:
        for orig, name in zip(df.columns, cols):
            if name == kw:
                return orig
    for kw in keywords:
        for orig, name in zip(df.columns, cols):
            if kw in name:
                return orig
    return None


def _to_int(value) -> int:
    """'17,300원' / 17300.0 등을 정수로 변환. 실패 시 0. (소수점 뒤는 버려 10배 방지)"""
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    s = str(value).split(".")[0]
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _yyyymm(value) -> str:
    """날짜류 값에서 앞 6자리 숫자(YYYYMM)를 추출. 예: '2026-03-10 12:06:03' → '202603'."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:6]


def summarize_purchase(start_date: str) -> int:
    """최신 엑셀에서 해당 월 매입금을 합산하고 도매_매입금.xlsx 에 기록. 매입금 반환.

    start_date: 조회 시작일 (YYYY-MM-DD). 여기서 대상 월을 추출한다.
    """
    files = sorted(
        [f for f in DOWNLOADS_DIR.glob("*.xlsx") if not f.name.startswith("~")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("다운로드된 엑셀 파일이 없습니다")

    log.debug(f"파일: {files[0].name}")
    df = pd.read_excel(files[0])
    log.debug(f"컬럼: {list(df.columns)}")

    date_col = _find_col(df, ["주문일자", "주문일시", "주문일", "주문날짜"])
    status_col = _find_col(df, ["주문상태", "배송상태", "상태"])
    price_col = _find_col(df, ["가격", "단가"])
    qty_col = _find_col(df, ["수량", "개수"])
    invoice_col = _find_col(df, ["송장번호", "송장"])
    order_col = _find_col(df, ["주문번호"])

    if date_col is None or price_col is None or qty_col is None:
        raise RuntimeError(
            f"필수 컬럼(주문일자/가격/수량)을 찾지 못했습니다. 컬럼: {list(df.columns)}"
        )

    target = _yyyymm(start_date)
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    n0 = len(df)

    # 해당 월만 남기기
    df = df[df[date_col].map(_yyyymm) == target]
    log.info(f"해당 월({target}) 필터: {n0}건 → {len(df)}건")

    # 취소류 제외 (상태 기준, 공용 필터)
    df = drop_canceled(df, status_col, log=log)

    # 상품금액: 각 라인 (가격 × 수량) 합
    product_total = (
        int((df[price_col].map(_to_int) * df[qty_col].map(_to_int)).sum()) if len(df) else 0
    )

    # 배송비: 송장번호 단위로 3,000원 (같은 송장=1배송). 송장이 비면 주문번호로 대체.
    if len(df) == 0:
        shipping_total, ship_count = 0, 0
    elif invoice_col is not None:
        key = df[invoice_col].astype(str).str.strip()
        blank = key.isin(BLANK_INVOICE)
        if order_col is not None:
            key = key.where(~blank, df[order_col].astype(str).str.strip())
        else:
            key = key.where(~blank, pd.Series(df.index.astype(str), index=df.index))
        ship_count = int(key.nunique())
        shipping_total = ship_count * SHIPPING_FEE
    else:
        log.warn("송장번호 컬럼이 없어 행마다 배송비를 매깁니다")
        ship_count = len(df)
        shipping_total = ship_count * SHIPPING_FEE

    total = product_total + shipping_total
    log.info(
        f"상품금액 {product_total:,}원 + 배송비 {shipping_total:,}원(송장 {ship_count}건) "
        f"= {total:,}원 (라인 {len(df)}건)"
    )

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
    _start = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
    summarize_purchase(_start)

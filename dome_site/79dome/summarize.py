"""친구도매(79dome) 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (사용자 지시: "합계액만. 적립금 지우고. 송장번호 같으면 배송비 한번만"):
  - '주문일자' 해당월 필터.
  - '상품명' 에 '적립금' 이 포함된 행 제외.
  - '상태' 에 취소/반품/교환/환불 이 있으면 제외 (공용 drop_canceled).
  - '상태' 에 미결제/입금대기 등 매입 미확정 건 제외 (UNPAID_KEYWORDS).
  - 매입금 = 상품금액 + 배송비
    · 상품금액 = 각 라인 (가격 × 수량) 합.
    · 배송비 = '송장번호' 단위로 1번만(같은 송장=배송 1건). 송장이 비거나 0이면 주문번호로 대체.
  ※ 엑셀의 '합계액'(=주문 총액, 옵션 여러개면 행마다 반복)을 그대로 합하면 배송비·상품이
    중복되므로 쓰지 않고, 위 방식으로 재구성한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from dome_site.order_filters import drop_canceled

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

SITE_LABEL = "친구도매"

# 매입 미확정(결제 전) 주문상태 키워드. 이 단어가 상태에 있으면 매입금에서 제외한다.
UNPAID_KEYWORDS = ["미결제", "입금대기", "미입금", "결제대기"]

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
    """'5,720원' / 5720.0 등을 정수로 변환. 실패 시 0. (소수점 뒤는 버려 10배 방지)"""
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    s = str(value).split(".")[0]
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _yyyymm(value) -> str:
    """날짜류 값에서 앞 6자리 숫자(YYYYMM)를 추출. 예: '2026-05-29 08:10:25' → '202605'."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:6]


def summarize_purchase(start_date: str) -> int:
    """최신 엑셀에서 해당 월 합계액을 합산하고 도매_매입금.xlsx 에 기록. 매입금 반환.

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
    name_col = _find_col(df, ["상품명", "품목", "상품"])
    status_col = _find_col(df, ["상태", "주문상태", "배송상태"])
    price_col = _find_col(df, ["가격", "단가"])
    qty_col = _find_col(df, ["수량"])
    ship_col = _find_col(df, ["배송비"])
    invoice_col = _find_col(df, ["송장번호", "송장"])
    order_col = _find_col(df, ["주문번호"])

    if date_col is None or price_col is None or qty_col is None or ship_col is None:
        raise RuntimeError(
            f"필수 컬럼(주문일자/가격/수량/배송비)을 찾지 못했습니다. 컬럼: {list(df.columns)}"
        )

    target = _yyyymm(start_date)
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    n0 = len(df)

    # 해당 월만 남기기
    df = df[df[date_col].map(_yyyymm) == target]
    log.info(f"해당 월({target}) 필터: {n0}건 → {len(df)}건")

    # 적립금 행 제외 (상품명 기준)
    if name_col is not None:
        point_mask = df[name_col].astype(str).str.contains("적립금", na=False)
        removed = int(point_mask.sum())
        if removed:
            df = df[~point_mask]
            log.info(f"'적립금' 행 {removed}건 제외 → {len(df)}건")
    else:
        log.warn("상품명 컬럼을 찾지 못해 '적립금' 제외를 건너뜁니다")

    # 취소류 제외 (상태 기준, 공용 필터)
    df = drop_canceled(df, status_col, log=log)

    # 미결제/입금대기 등 매입 미확정 주문 제외 (상태 기준)
    if status_col is not None and status_col in df.columns:
        unpaid_mask = df[status_col].astype(str).str.contains(
            "|".join(UNPAID_KEYWORDS), na=False
        )
        removed = int(unpaid_mask.sum())
        if removed:
            df = df[~unpaid_mask]
            log.info(
                f"미결제류({'/'.join(UNPAID_KEYWORDS)}) 주문 {removed}건 제외 → {len(df)}건"
            )
    else:
        log.warn("주문상태 컬럼이 없어 미결제 제외를 건너뜁니다")

    # 상품금액: 각 라인 (가격 × 수량) 합
    product_total = int((df[price_col].map(_to_int) * df[qty_col].map(_to_int)).sum()) if len(df) else 0

    # 배송비: '송장번호' 단위로 1번만 (같은 송장=1배송). 송장이 비면 주문번호로 대체.
    if len(df) == 0:
        shipping_total, ship_count = 0, 0
    elif invoice_col is not None:
        key = df[invoice_col].astype(str).str.strip()
        # 미출고 등으로 송장이 비었거나 '0' 인 건은 주문번호로 대체(같은 '0' 끼리 뭉쳐 과소계산 방지)
        blank = key.isin(BLANK_INVOICE)
        if order_col is not None:
            key = key.where(~blank, df[order_col].astype(str).str.strip())
        else:
            key = key.where(~blank, pd.Series(df.index.astype(str), index=df.index))
        fee = df[ship_col].map(_to_int)
        shipping_total = int(fee.groupby(key).first().sum())
        ship_count = int(key.nunique())
    else:
        log.warn("송장번호 컬럼이 없어 행마다 배송비를 매깁니다")
        shipping_total = int(df[ship_col].map(_to_int).sum())
        ship_count = len(df)

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
    _start = sys.argv[1] if len(sys.argv) > 1 else "2026-05-01"
    summarize_purchase(_start)

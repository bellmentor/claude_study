"""파라브로 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (parabro_get.txt 기준):
  - 파라브로는 앞뒤로 넉넉히 넓힌 기간으로 조회했으므로, 먼저 '주문날짜' 가
    사용자가 선택한 기간(start_date~end_date) 안인 행만 남긴다.
  - 품목명에 '적립금' 이 포함된 행은 제외한다.
  - 같은 송장번호는 한 번의 배송이므로 배송비(3,000원)를 송장 단위로 1번만 더한다.
  - (상품금액 합계) + (3,000원 × 배송건수) = 해당 월의 매입금.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from dome_site.order_filters import drop_canceled

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

SITE_LABEL = "파라브로"
SHIPPING_FEE = 3000  # 상품(행) 당 배송비

log = SiteLogger(SITE_LABEL)


def _read_excel(path: Path) -> pd.DataFrame:
    """파라브로 다운로드 파일을 DataFrame 으로 읽는다.

    파라브로의 '엑셀다운로드' 는 확장자만 .xls 일 뿐 실제로는 HTML 테이블을
    application/vnd.ms-excel 로 내려준다(한국 쇼핑몰에서 흔한 방식). 그래서
    파일 시작 바이트로 HTML 여부를 판별해 read_html / read_excel 을 분기한다.
    """
    head = path.read_bytes()[:64].lstrip().lower()
    if head.startswith(b"<"):
        # HTML 테이블 → 첫 번째 표를 사용
        tables = pd.read_html(path)
        if not tables:
            raise RuntimeError("HTML 안에서 테이블을 찾지 못했습니다")
        return tables[0]
    return pd.read_excel(path)


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """컬럼명에 keywords 중 하나라도 포함된 첫 컬럼명을 반환. 없으면 None."""
    for col in df.columns:
        name = str(col)
        for kw in keywords:
            if kw in name:
                return col
    return None


def _to_int(value) -> int:
    """'6,200' / '6,200원' / 6200.0 등 다양한 표기를 정수로 변환. 실패 시 0."""
    if pd.isna(value):
        return 0
    s = str(value)
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _to_yyyymmdd(value) -> int:
    """날짜류 값에서 앞 8자리 숫자(YYYYMMDD)를 정수로 추출. 예: '2026/06/21' → 20260621."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits[:8]) if len(digits) >= 8 else 0


def summarize_purchase(start_date: str, end_date: str) -> int:
    """최신 엑셀에서 매입금을 계산하고 도매_매입금.xlsx 에 기록한다. 매입금(원) 반환.

    start_date, end_date: 사용자가 선택한 기간 (YYYY-MM-DD). '주문날짜' 필터와 월 라벨에 사용.
    """
    files = sorted(
        [f for f in DOWNLOADS_DIR.glob("*.xlsx") if not f.name.startswith("~")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("다운로드된 엑셀 파일이 없습니다")

    log.debug(f"엑셀 파일: {files[0].name}")
    df = _read_excel(files[0])
    log.debug(f"엑셀 컬럼: {list(df.columns)}")

    # 주문날짜 컬럼: 넓게 조회했으므로 선택 기간만 남긴다.
    date_col = _find_col(df, ["주문날짜", "주문일자", "주문일"])
    if date_col is not None:
        start_i = _to_yyyymmdd(start_date)
        end_i = _to_yyyymmdd(end_date)
        n0 = len(df)
        d = df[date_col].map(_to_yyyymmdd)
        df = df[(d >= start_i) & (d <= end_i)]
        log.info(f"선택 기간({start_date}~{end_date}) 필터: {n0}건 → {len(df)}건")
    else:
        log.warn("주문날짜 컬럼을 찾지 못해 기간 필터를 건너뜁니다")

    # 주문상태에 취소/반품/교환/환불 이 포함된 주문은 제외 (공용 필터)
    status_col = _find_col(df, ["주문상태", "배송상태", "상태"])
    df = drop_canceled(df, status_col, log=log)

    # 품목명 컬럼: '적립금' 행 제외에 사용
    name_col = _find_col(df, ["상품명", "품목", "상품", "제품명"])
    # 금액 컬럼: 상품금액(공급가) 합산에 사용
    amount_col = _find_col(df, ["상품금액", "판매금액", "공급가", "결제금액", "금액", "단가"])
    # 송장번호 컬럼: 배송비를 배송(송장) 단위로 1번만 매기기 위해 사용
    invoice_col = _find_col(df, ["송장"])

    if amount_col is None:
        raise RuntimeError(
            "상품금액 컬럼을 찾지 못했습니다. "
            f"엑셀 컬럼: {list(df.columns)} — summarize.py 의 _find_col 키워드를 확인하세요."
        )

    total_rows = len(df)
    # 적립금 행 제외
    if name_col is not None:
        point_mask = df[name_col].astype(str).str.contains("적립금", na=False)
        removed = int(point_mask.sum())
        df = df[~point_mask]
        log.info(f"'적립금' 행 {removed}건 제외 (전체 {total_rows}건 → {len(df)}건)")
    else:
        log.warn("품목명 컬럼을 찾지 못해 '적립금' 행 제외를 건너뜁니다")

    goods_total = int(df[amount_col].map(_to_int).sum())

    # 배송비: 같은 송장번호는 한 번의 배송이므로 배송비도 1번만 매긴다.
    # 송장번호가 비어있는 행(배송준비 중 등)은 아직 묶을 수 없으므로 각각 1건으로 센다.
    if invoice_col is not None:
        invoice_vals = df[invoice_col].map(lambda v: str(v).strip())
        blank_mask = invoice_vals.isin(["", "nan", "None"])
        unique_invoices = invoice_vals[~blank_mask].nunique()
        blank_count = int(blank_mask.sum())
        ship_count = unique_invoices + blank_count
        log.info(f"배송 건수: 송장 {unique_invoices}건 + 송장없음 {blank_count}건 = {ship_count}건")
    else:
        ship_count = len(df)
        log.warn(f"송장번호 컬럼을 찾지 못해 행(상품) 단위로 배송비를 매깁니다 ({ship_count}건)")

    shipping_total = SHIPPING_FEE * ship_count
    total = goods_total + shipping_total
    log.info(
        f"상품금액 합계 {goods_total:,}원 + 배송비 {SHIPPING_FEE:,}원×{ship_count}건 "
        f"({shipping_total:,}원) = {total:,}원"
    )

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
    import calendar

    _start = sys.argv[1] if len(sys.argv) > 1 else "2026-06-01"
    if len(sys.argv) > 2:
        _end = sys.argv[2]
    else:
        _y, _m = int(_start[:4]), int(_start[5:7])
        _last = calendar.monthrange(_y, _m)[1]
        _end = f"{_y}-{_m:02d}-{_last:02d}"
    summarize_purchase(_start, _end)

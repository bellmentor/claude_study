"""식자재코리아 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (프롬프트용.txt 기준):
  4-1. '일자' 에서 해당 월만 남긴다. (헤더/'일계' 소계행은 일자가 없어 자동 제외)
  4-2. '구분' 에 '관리자 취소/반품/교환/환불/취소' 가 있으면 제외 (공용 drop_canceled).
  4-3. '거래액' 합계 = 해당 월의 매입금. (배송비 행도 거래액에 포함됨)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from dome_site.order_filters import drop_canceled

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

SITE_LABEL = "식자재코리아"

log = SiteLogger(SITE_LABEL)


def _read_ledger(path: Path) -> pd.DataFrame:
    """거래원장 파일을 읽는다. HTML 테이블(첫 행이 헤더)이면 read_html(header=0)."""
    head = path.read_bytes()[:64].lstrip().lower()
    if head.startswith(b"<") or b"<html" in head:
        tables = pd.read_html(path, header=0)
        if not tables:
            raise RuntimeError("HTML 안에서 테이블을 찾지 못했습니다")
        return max(tables, key=lambda t: t.shape[1])
    return pd.read_excel(path)


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """컬럼명을 keywords 로 찾는다. 정확 일치를 우선하고, 없으면 부분 포함으로 찾는다."""
    cols = [str(c) for c in df.columns]
    for kw in keywords:  # 1순위: 정확 일치
        for orig, name in zip(df.columns, cols):
            if name == kw:
                return orig
    for kw in keywords:  # 2순위: 부분 포함
        for orig, name in zip(df.columns, cols):
            if kw in name:
                return orig
    return None


def _to_int(value) -> int:
    """'12,000' / '12,000원' / 12000.0 등을 정수로 변환. 실패 시 0.

    주의: 값이 float('12440.0')이면 str 로 바꿔 숫자만 뽑을 때 소수점 뒤 '0'까지 붙어
    124400(=10배)이 되는 버그가 있었다. 반드시 소수점을 경계로 정수부만 취한다.
    """
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    s = re.sub(r"[^0-9.\-]", "", str(value))  # 콤마·'원'·공백 제거, 숫자/./- 만 남김
    if s in ("", "-", ".", "-."):
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        digits = "".join(ch for ch in s if ch.isdigit())
        return int(digits) if digits else 0


def _yyyymm(value) -> str:
    """날짜류 값에서 앞 6자리 숫자(YYYYMM)를 추출. 예: '2026-05-03 20:30' → '202605'."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:6]


def summarize_purchase(start_date: str) -> int:
    """최신 거래원장에서 해당 월 거래액을 합산하고 도매_매입금.xlsx 에 기록. 매입금 반환.

    start_date: 조회 시작일 (YYYY-MM-DD). 여기서 대상 월을 추출한다.
    """
    files = sorted(
        [f for f in DOWNLOADS_DIR.glob("*.xls*") if not f.name.startswith("~")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("다운로드된 거래원장 파일이 없습니다")

    log.debug(f"파일: {files[0].name}")
    df = _read_ledger(files[0])
    log.debug(f"컬럼: {list(df.columns)}")

    date_col = _find_col(df, ["일자", "주문일시", "주문일", "주문날짜"])
    status_col = _find_col(df, ["구분", "주문상태", "상태"])
    amount_col = _find_col(df, ["거래액", "결제금액", "금액"])

    if date_col is None or amount_col is None:
        raise RuntimeError(
            "필수 컬럼(일자/거래액)을 찾지 못했습니다. "
            f"컬럼: {list(df.columns)} — summarize.py 의 _find_col 키워드를 확인하세요."
        )

    target = _yyyymm(start_date)
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    n0 = len(df)

    # 4-1. 해당 월만 남기기 (헤더/'일계' 소계행은 일자가 없어 자동 제외)
    df = df[df[date_col].map(_yyyymm) == target]
    log.info(f"4-1 해당 월({target}) 필터: {n0}건 → {len(df)}건")

    # 4-2. 취소류(관리자 취소/반품/교환/환불/취소) 제외 (공용 필터, '구분' 컬럼 기준)
    df = drop_canceled(df, status_col, log=log)

    # 4-2b. 매입(거래)이 아닌 행 제외: '차감'(주문 적립금 사용)·'일계'(소계) 등.
    #       이 행들의 거래액은 실제 매입이 아니라 결제수단/소계 표시라 합산에서 뺀다.
    if status_col is not None:
        nonpurchase = df[status_col].astype(str).str.contains("차감|일계|소계|적립", na=False)
        removed = int(nonpurchase.sum())
        if removed:
            df = df[~nonpurchase]
            log.info(f"4-2b 비매입행(차감/일계 등) {removed}건 제외 → {len(df)}건")

    # 4-3. 거래액 합산 (배송비 행 포함)
    total = int(df[amount_col].map(_to_int).sum()) if len(df) else 0
    log.info(f"4-3 거래액 합계 = {total:,}원 ({len(df)}건)")

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

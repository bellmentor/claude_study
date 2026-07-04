"""히트가구 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (프롬프트용.txt 기준):
  4-1. '주문일시' 에서 해당 월만 남긴다.
  4-2. '주문상태' 에 반품/교환/환불 등 취소류가 있으면 제외 (공용 drop_canceled).
  4-3. '실결제금액' 합계 = 해당 월의 매입금.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from dome_site.order_filters import drop_canceled

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

SITE_LABEL = "히트가구"

log = SiteLogger(SITE_LABEL)


def _read_excel(path: Path) -> pd.DataFrame:
    """다운로드 파일을 DataFrame 으로 읽는다(HTML 테이블이면 read_html, 아니면 read_excel)."""
    head = path.read_bytes()[:64].lstrip().lower()
    if head.startswith(b"<"):
        tables = pd.read_html(path)
        if not tables:
            raise RuntimeError("HTML 안에서 테이블을 찾지 못했습니다")
        return max(tables, key=lambda t: t.shape[1])
    return pd.read_excel(path)


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """컬럼명을 keywords 로 찾는다. 정확 일치를 우선하고, 없으면 부분 포함으로 찾는다.

    부분 포함만 쓰면 '주문상태' 를 찾을 때 '주문상태코드'(숫자 코드)가 먼저 걸리는 등
    엉뚱한 컬럼을 잡을 수 있어, 정확 일치를 1순위로 둔다.
    """
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
    """'12,000' / '12,000원' / 12000.0 등을 정수로 변환. 실패 시 0."""
    if pd.isna(value):
        return 0
    s = str(value)
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _yyyymm(value) -> str:
    """날짜류 값에서 앞 6자리 숫자(YYYYMM)를 추출. 예: '2026-06-15 12:00' → '202606'."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:6]


def summarize_purchase(start_date: str) -> int:
    """최신 엑셀에서 규칙대로 필터링해 실결제금액을 합산하고 도매_매입금.xlsx 에 기록. 매입금 반환.

    start_date: 조회 시작일 (YYYY-MM-DD). 여기서 대상 월을 추출한다.
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

    date_col = _find_col(df, ["주문일시", "주문일자", "주문일", "주문날짜"])
    status_col = _find_col(df, ["주문상태", "배송상태", "상태"])
    amount_col = _find_col(df, ["실결제금액", "결제금액", "실결제", "결제금"])

    if date_col is None or amount_col is None:
        raise RuntimeError(
            "필수 컬럼(주문일시/실결제금액)을 찾지 못했습니다. "
            f"엑셀 컬럼: {list(df.columns)} — summarize.py 의 _find_col 키워드를 확인하세요."
        )

    target = _yyyymm(start_date)
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    n0 = len(df)

    # 4-1. 해당 월만 남기기
    df = df[df[date_col].map(_yyyymm) == target]
    log.info(f"4-1 해당 월({target}) 필터: {n0}건 → {len(df)}건")

    # 4-2. 취소류(반품/교환/환불/취소) 주문 제외 (공용 필터)
    df = drop_canceled(df, status_col, log=log)

    # 4-3. 실결제금액 행 단순합.
    # (주의: 사용자 수기 검증 기준 = 다품목 주문이라 실결제금액이 여러 행에 반복돼도
    #  행 단위로 그대로 합산한다. 주문번호 중복 제거는 하지 않는다.)
    total = int(df[amount_col].map(_to_int).sum()) if len(df) else 0
    log.info(f"4-3 실결제금액 행 합계 = {total:,}원 ({len(df)}행)")

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

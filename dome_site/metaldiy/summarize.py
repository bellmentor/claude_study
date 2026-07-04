"""철물박사 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (metaldiy_get.txt 기준):
  3-1. '주문일' 에서 해당 월만 남긴다.
  3-2. 본인 적립금 주문 제외 : (수령자명 == '최종훈') AND (결제방법 == '무통장입금') 인 행.
  3-3. '주문상태' 가 '배송중' 인 행만 남긴다.
  3-4. 남은 행의 '결제금액' 합계 = 해당 월의 매입금.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from dome_site.logger import SiteLogger
from dome_site.order_filters import drop_canceled

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
SUMMARY_XLSX = Path(__file__).resolve().parents[1] / "도매_매입금.xlsx"

SITE_LABEL = "철물박사"
MY_NAME = "최종훈"          # 본인 적립금 주문 판별용 수령자명
MY_PAY = "무통장입금"        # 본인 적립금 주문 판별용 결제방법
KEEP_STATUS = "배송중"       # 남길 주문상태

log = SiteLogger(SITE_LABEL)


def _read_excel(path: Path) -> pd.DataFrame:
    """다운로드 파일을 DataFrame 으로 읽는다.

    한국 쇼핑몰은 '엑셀'을 확장자만 .xls 인 HTML 테이블로 내려주는 경우가 많다.
    파일 첫 바이트로 HTML 여부를 판별해 read_html / read_excel 을 분기한다.
    """
    head = path.read_bytes()[:64].lstrip().lower()
    if head.startswith(b"<"):
        tables = pd.read_html(path)
        if not tables:
            raise RuntimeError("HTML 안에서 테이블을 찾지 못했습니다")
        # 여러 표가 있으면 컬럼 수가 가장 많은(=주문목록) 표를 사용
        return max(tables, key=lambda t: t.shape[1])
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
    """'12,000' / '12,000원' / 12000.0 등을 정수로 변환. 실패 시 0."""
    if pd.isna(value):
        return 0
    s = str(value)
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _yyyymm(value) -> str:
    """날짜류 값에서 앞 6자리 숫자(YYYYMM)를 추출. 예: '2026-06-15' → '202606'."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:6]


def summarize_purchase(start_date: str) -> int:
    """최신 엑셀에서 규칙대로 필터링해 결제금액을 합산하고 도매_매입금.xlsx 에 기록. 매입금 반환.

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

    date_col = _find_col(df, ["주문일", "주문날짜", "주문일자"])
    name_col = _find_col(df, ["수령자명", "수령인", "받는분", "수령자"])
    pay_col = _find_col(df, ["결제방법", "결제수단"])
    status_col = _find_col(df, ["주문상태", "배송상태", "상태"])
    amount_col = _find_col(df, ["결제금액", "실결제금액", "결제금"])

    if date_col is None or amount_col is None:
        raise RuntimeError(
            "필수 컬럼(주문일/결제금액)을 찾지 못했습니다. "
            f"엑셀 컬럼: {list(df.columns)} — summarize.py 의 _find_col 키워드를 확인하세요."
        )

    target = _yyyymm(start_date)  # "202606"
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    n0 = len(df)

    # 3-1. 해당 월만 남기기
    df = df[df[date_col].map(_yyyymm) == target]
    log.info(f"3-1 해당 월({target}) 필터: {n0}건 → {len(df)}건")

    # 3-2. 본인 적립금 주문 제외 (수령자명==최종훈 AND 결제방법==무통장입금)
    if name_col is not None and pay_col is not None:
        own_mask = (
            df[name_col].astype(str).str.contains(MY_NAME, na=False)
            & df[pay_col].astype(str).str.contains(MY_PAY, na=False)
        )
        removed = int(own_mask.sum())
        df = df[~own_mask]
        log.info(f"3-2 본인 적립금 주문 제외({MY_NAME}·{MY_PAY}): {removed}건 제외 → {len(df)}건")
    else:
        log.warn("3-2 수령자명/결제방법 컬럼을 찾지 못해 본인 적립금 제외를 건너뜁니다")

    # (공용) 취소/반품/교환/환불 주문 제외. 철물박사는 아래 3-3 에서 '배송중'만 남기므로
    # 대개 중복이지만, 모든 도매처 공통 표준으로 명시해 둔다.
    df = drop_canceled(df, status_col, log=log)

    # 3-3. '배송중' 만 남기기
    if status_col is not None:
        # 필터 전 주문상태 분포를 남겨, '배송중'이 없어 0원이 되는 경우 원인 파악에 쓴다.
        dist = df[status_col].astype(str).value_counts().to_dict()
        log.info(f"3-3 필터 전 주문상태 분포: {dist}")
        df = df[df[status_col].astype(str).str.contains(KEEP_STATUS, na=False)]
        log.info(f"3-3 '{KEEP_STATUS}' 만 남김 → {len(df)}건")
    else:
        log.warn("3-3 주문상태 컬럼을 찾지 못해 상태 필터를 건너뜁니다")

    # 3-4. 결제금액 합산 (0행이면 빈 합계 처리 이슈가 있어 명시적으로 0 처리)
    total = int(df[amount_col].map(_to_int).sum()) if len(df) else 0
    log.info(f"3-4 결제금액 합계 = {total:,}원 ({len(df)}건)")

    if total == 0:
        log.warn("매입금이 0원입니다. 위 '주문상태 분포' 로그를 확인하세요 (배송중 건이 없을 수 있음).")

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

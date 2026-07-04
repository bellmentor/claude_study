"""컴스마트 매입금 합산 → 도매_매입금.xlsx 에 기록.

계산 규칙 (프롬프트용.txt 기준):
  - '주문일시' 에서 해당 월만 남긴다.
  - '주문상태' 에 취소/반품/교환/환불 이 있으면 제외 (공용 drop_canceled).
  - '입금액' 합계 = 해당 월의 매입금.
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

SITE_LABEL = "컴스마트"

log = SiteLogger(SITE_LABEL)


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """컬럼명을 keywords 로 찾는다. 정확 일치를 우선하고, 없으면 부분 포함으로 찾는다.

    컬럼명에 공백이 섞여 있을 수 있어(예: '상 태') 비교 시 공백을 제거한다.
    """
    cols = [re.sub(r"\s+", "", str(c)) for c in df.columns]
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


def _year_month(value) -> tuple[int, int] | None:
    """날짜류 값에서 (연, 월) 을 뽑는다. 2자리 연도('26-04-10')는 20xx 로 보정.

    예: '26-04-10 16:13 (금)' → (2026, 4),  '2026/06/21' → (2026, 6).
    숫자가 부족하면(잡음 행) None.
    """
    nums = re.findall(r"\d+", str(value))
    if len(nums) < 2:
        return None
    year, month = int(nums[0]), int(nums[1])
    if year < 100:
        year += 2000
    if not (1 <= month <= 12):
        return None
    return year, month


def summarize_purchase(start_date: str) -> int:
    """최신 크롤링 파일에서 해당 월 입금액을 합산하고 도매_매입금.xlsx 에 기록. 매입금 반환.

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

    date_col = _find_col(df, ["주문일시", "주문일자", "주문일", "주문날짜"])
    status_col = _find_col(df, ["주문상태", "배송상태", "상태"])
    amount_col = _find_col(df, ["입금액", "결제금액", "실결제금액", "금액"])

    if date_col is None or amount_col is None:
        raise RuntimeError(
            "필수 컬럼(주문일시/입금액)을 찾지 못했습니다. "
            f"컬럼: {list(df.columns)} — summarize.py 의 _find_col 키워드를 확인하세요."
        )

    target = (int(start_date[:4]), int(start_date[5:7]))
    yy, mm = start_date[2:4], start_date[5:7]
    month_label = f"{yy}년{mm}월"

    n0 = len(df)

    # 해당 월만 남기기 (2자리 연도 형식 '26-04-10' 도 처리)
    df = df[df[date_col].map(_year_month) == target]
    log.info(f"해당 월({target[0]}-{target[1]:02d}) 필터: {n0}건 → {len(df)}건")

    # 취소류(취소/반품/교환/환불) 제외 (공용 필터, 주문상태 컬럼이 있을 때만 동작)
    df = drop_canceled(df, status_col, log=log)

    # 입금액 합산
    total = int(df[amount_col].map(_to_int).sum()) if len(df) else 0
    log.info(f"입금액 합계 = {total:,}원 ({len(df)}건)")

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
    # 컴스마트는 주문내역 단일 페이지만 크롤링한다. 주문이 많아 페이지가 나뉘면 누락된다.
    log.warn("컴스마트 매입금 (페이지 넘어갈시 코드수정필요) — 현재 주문내역 단일 페이지만 크롤링함")
    return total


if __name__ == "__main__":
    _start = sys.argv[1] if len(sys.argv) > 1 else "2026-06-01"
    summarize_purchase(_start)

"""일일마감자료(건아유통 '리차스 거래처관리대장') 엑셀 공용 파서.

건아유통은 매일 예치금 차감 내역을 엑셀 장부로 보내준다. 한 파일 = 하루치이며,
A열에 정확히 "YYYY/MM  계" 형식인 '계행'의 C값이 그날의 진짜 매입 총액이다(신뢰 소스).
같은 금액이 날짜요약행·계행·누계행 세 곳에 리터럴로 중복 등장하므로, C열 전체를
그냥 합산하면 안 되고 계행 값 하나만 채택해야 한다(실제 데이터로 검증 완료).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# 개별 품목 줄: "상품명설명 [규격] / 수량 * 단가"
_ITEM_RE = re.compile(r"^(?P<name>.+?)\s*\[(?P<spec>[^\]]*)\]\s*/\s*(?P<qty>\d+)\s*\*\s*(?P<price>[\d,]+)\s*$")
# 택배비 줄: "택배비N / 수량 * 단가" (대괄호 규격 없음)
_SHIPPING_RE = re.compile(r"^(?P<name>택배비\d*)\s*/\s*(?P<qty>\d+)\s*\*\s*(?P<price>[\d,]+)\s*$")
# 날짜요약행: "YYYY/MM/DD -N" (판매 스냅샷 또는 수금 스냅샷)
_DATE_ROW_RE = re.compile(r"^(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2})\s*-\d+$")
# 계행: "YYYY/MM  계" (연/월 + 공백 2칸 + 계)
_TOTAL_ROW_RE = re.compile(r"^\d{4}/\d{2}\s{2}계$")
# 카톤(대량 묶음) 표기: "<기본표기>*N*8" → 8배 묶음, 단가는 카톤 1개(=8박스) 가격
_CARTON_RE = re.compile(r"^(?P<base>.+\*\d+)\*8$")


@dataclass
class LedgerItem:
    """일일마감자료 한 줄(품목 또는 택배비)."""

    name: str  # 원문 표기 (카톤이면 박스 단위로 환산된 base 표기)
    qty: int  # 박스 단위 수량 (카톤이면 8배로 환산됨)
    unit_price: int  # 박스 1개당 단가 (카톤이면 8로 나눈 값)
    amount: int  # 원문 그대로의 금액(카톤 환산 전, 검증용)


@dataclass
class LedgerDay:
    """일일마감자료 엑셀 1개(하루치) 파싱 결과."""

    file: Path
    date: str  # YYYY-MM-DD, 못 찾으면 빈 문자열
    total: int  # 계행 C값 = 그날 매입 총액(신뢰 소스)
    deposit: int  # 그날 수금(예치금 충전) 합계, 없으면 0
    items: list[LedgerItem]
    valid: bool
    issues: list[str] = field(default_factory=list)


def _s(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _to_int(value) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    s = re.sub(r"[^0-9\-]", "", str(value))
    if s in ("", "-"):
        return 0
    return int(s)


def parse_daily_file(path: Path) -> LedgerDay:
    """일일마감자료 엑셀 1개를 파싱한다.

    계행(A열 'YYYY/MM  계') C값을 매입 총액으로 채택하고, 품목 줄 합계·누계행
    C값과 교차검증한다. 세 값이 모두 일치해야 valid=True.
    """
    raw = pd.read_excel(path, sheet_name=0, header=None)

    date = ""
    total: int | None = None
    cumulative_total: int | None = None
    deposit = 0
    items: list[LedgerItem] = []
    item_sum = 0
    issues: list[str] = []

    for _, row in raw.iterrows():
        vals = row.tolist()
        a = _s(vals[0]) if len(vals) > 0 else ""
        b = _s(vals[1]) if len(vals) > 1 else ""
        c = vals[2] if len(vals) > 2 else None
        d = vals[3] if len(vals) > 3 else None

        date_m = _DATE_ROW_RE.match(a)
        if date_m:
            if not date:
                date = f"{date_m.group('y')}-{date_m.group('m')}-{date_m.group('d')}"
            deposit += _to_int(d)
            continue

        if _TOTAL_ROW_RE.match(a):
            total = _to_int(c)
            continue

        if a == "누계":
            cumulative_total = _to_int(c)
            continue

        m = _ITEM_RE.match(b) or _SHIPPING_RE.match(b)
        if not m:
            continue

        name = m.group("name").strip()
        qty = int(m.group("qty"))
        price = _to_int(m.group("price"))
        amount = _to_int(c) if c is not None else qty * price
        item_sum += amount

        carton_m = _CARTON_RE.match(name)
        if carton_m:
            # 카톤(8박스 묶음) 표기 → 박스 단위로 환산해 기본 표기 버킷에 합류시킨다.
            base = carton_m.group("base")
            items.append(LedgerItem(name=base, qty=qty * 8, unit_price=round(price / 8), amount=amount))
        else:
            items.append(LedgerItem(name=name, qty=qty, unit_price=price, amount=amount))

    if not date:
        issues.append("날짜요약행을 찾지 못함")
    if total is None:
        issues.append("계행('YYYY/MM  계')을 찾지 못함")
    if total is not None and item_sum != total:
        issues.append(f"품목 합계({item_sum:,})가 계행 값({total:,})과 불일치")
    if total is not None and cumulative_total is not None and cumulative_total != total:
        issues.append(f"누계행 값({cumulative_total:,})이 계행 값({total:,})과 불일치")

    valid = not issues
    return LedgerDay(
        file=path,
        date=date,
        total=total or 0,
        deposit=deposit,
        items=items,
        valid=valid,
        issues=issues,
    )


def load_ledger_folder(folder: Path) -> list[LedgerDay]:
    """폴더 안의 'MMDD 마감자료.xlsx' 류 엑셀을 전부 파싱한다(잠금파일 제외)."""
    days: list[LedgerDay] = []
    if not folder.exists():
        return days
    for f in sorted(folder.glob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        try:
            days.append(parse_daily_file(f))
        except Exception as e:  # noqa: BLE001 - 파일 하나가 깨져도 나머지는 계속 처리
            days.append(LedgerDay(file=f, date="", total=0, deposit=0, items=[], valid=False, issues=[f"파싱 실패: {e}"]))
    return days

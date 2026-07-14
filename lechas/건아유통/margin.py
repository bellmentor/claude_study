"""건아유통 주문건별 마진표 — 매출 주문 엑셀에 실제매입가/개당단가/마진/마진율을 매칭한다.

매칭 원리: 매출 주문(판매자상품코드 k시작)의 상품코드를 상품명_매핑.txt 로 건아유통
일일마감자료 표기(접두문자열)로 변환한 뒤, 그 주문일자(±DATE_WINDOW일) 범위의 일일마감
자료 품목 줄에서 실제 매입 단가를 찾아 소비(재고 차감)한다. 같은 매입 줄을 여러 주문이
중복으로 쓰지 않도록 수량 단위로 소비 처리한다. 매핑이 없거나 매입 내역을 못 찾으면
매칭안됨으로 표시한다(추정으로 억지로 채우지 않음 — dome_site order 매칭과 동일 철학).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from dome_site.order_filters import drop_canceled

from .daily_ledger import _s, _to_int, load_ledger_folder

_HEADER_KEYWORDS = ("판매자상품코드", "정산예정금액")
MAPPING_FILE = Path(__file__).resolve().parent / "상품명_매핑.txt"
DATE_WINDOW = 3  # 매칭 날짜를 주문일 기준 ±N일까지 넓혀 재시도


def list_sheets(path: Path) -> list[str]:
    """엑셀 파일의 시트명 목록을 반환한다(업로드 후 시트 선택 드롭다운용)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return wb.sheetnames
    finally:
        wb.close()


def _read_sales_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    """매출 주문 엑셀의 지정 시트를 읽는다. 헤더가 1행이 아닐 수 있어 키워드로 헤더 행을 찾는다."""
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object, nrows=5)
    header_row = None
    for r in range(len(raw)):
        vals = [_s(v) for v in raw.iloc[r].tolist()]
        if all(any(kw in v for v in vals) for kw in _HEADER_KEYWORDS):
            header_row = r
            break
    if header_row is None:
        raise ValueError(f"'{sheet_name}' 시트에서 헤더 행을 찾지 못했습니다 (판매자상품코드/정산예정금액 컬럼 필요)")
    return pd.read_excel(path, sheet_name=sheet_name, header=header_row)


def load_mapping(path: Path = MAPPING_FILE) -> dict[str, str]:
    """상품명_매핑.txt (판매자상품코드 : 건아유통표기) 를 읽는다."""
    mapping: dict[str, str] = {}
    if not path.exists():
        return mapping
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        code, prefix = line.split(":", 1)
        code, prefix = code.strip(), prefix.strip()
        if code and prefix:
            mapping[code] = prefix
    return mapping


def _load_price_table(path: Path) -> dict[str, int]:
    """킹도매몰 단가표(선택, 참고 비교용)에서 상품코드→매입가를 읽는다. 실패하면 빈 dict."""
    try:
        df = pd.read_excel(path, sheet_name=0, header=1)
    except Exception:
        return {}
    code_col = "상품코드" if "상품코드" in df.columns else None
    price_col = "매입가" if "매입가" in df.columns else None
    if not code_col or not price_col:
        return {}
    table: dict[str, int] = {}
    for _, r in df.iterrows():
        code = _s(r.get(code_col))
        if code:
            table[code] = _to_int(r.get(price_col))
    return table


class _PurchasePool:
    """일자별 매입 품목의 남은 수량을 추적하는 소비 가능한 인벤토리."""

    def __init__(self, days):
        self.by_date: dict[str, list[list]] = {}
        for day in days:
            if not day.valid or not day.date:
                continue
            bucket = self.by_date.setdefault(day.date, [])
            for item in day.items:
                bucket.append([item.name, item.unit_price, item.qty])  # [이름, 단가, 남은수량]

    def take(self, prefix: str, need_qty: int, center_date: str, window: int = DATE_WINDOW):
        """center_date 기준 ±window일 범위에서 prefix로 시작하는 품목을 need_qty만큼 소비한다.
        (소비수량, 소비금액, 매칭날짜목록) 반환. 재고 부족하면 소비 가능한 만큼만 반환한다.
        """
        try:
            base = date.fromisoformat(center_date)
        except ValueError:
            return 0, 0, []

        taken_qty = 0
        taken_amount = 0
        matched_dates: list[str] = []

        for delta in range(0, window + 1):
            candidates = [base] if delta == 0 else [base - timedelta(days=delta), base + timedelta(days=delta)]
            for d in candidates:
                if taken_qty >= need_qty:
                    break
                bucket = self.by_date.get(d.isoformat())
                if not bucket:
                    continue
                for entry in bucket:
                    if taken_qty >= need_qty:
                        break
                    name, unit_price, remaining = entry
                    if remaining <= 0 or not name.startswith(prefix):
                        continue
                    take = min(remaining, need_qty - taken_qty)
                    entry[2] -= take
                    taken_qty += take
                    taken_amount += take * unit_price
                    if d.isoformat() not in matched_dates:
                        matched_dates.append(d.isoformat())
            if taken_qty >= need_qty:
                break

        return taken_qty, taken_amount, matched_dates


def calc_margin(
    sales_path: Path,
    sheet_name: str,
    ledger_folder: Path,
    start_date: str | None = None,
    end_date: str | None = None,
    price_table_path: Path | None = None,
    mapping_path: Path = MAPPING_FILE,
) -> dict[str, Any]:
    """매출 주문 엑셀(k코드 건아유통 주문)에 일일마감자료 매입가를 매칭해 마진을 계산한다."""
    df = _read_sales_sheet(sales_path, sheet_name)

    status_col = "주문상태" if "주문상태" in df.columns else None
    df = drop_canceled(df, status_col)

    code_col = "판매자상품코드"
    revenue_col = "정산예정금액(배송비포함)"
    if code_col not in df.columns or revenue_col not in df.columns:
        raise ValueError(f"필요한 컬럼이 없습니다({code_col}/{revenue_col}). 실제 컬럼: {list(df.columns)}")
    date_col = "주문일자(yyyy-MM-dd)." if "주문일자(yyyy-MM-dd)." in df.columns else "주문일시"

    mapping = load_mapping(mapping_path)
    price_table = _load_price_table(price_table_path) if price_table_path else {}
    pool = _PurchasePool(load_ledger_folder(ledger_folder))

    results: list[dict[str, Any]] = []
    matched_count = 0
    margin_sum = 0
    revenue_sum_matched = 0

    for _, row in df.iterrows():
        code = _s(row.get(code_col))
        if not code.upper().startswith("K"):
            continue  # 건아유통(k코드)이 아닌 주문은 이 표에서 제외

        order_date = _s(row.get(date_col))[:10]
        if start_date and end_date and order_date and not (start_date <= order_date <= end_date):
            continue

        qty = _to_int(row.get("수량")) or 1
        revenue = _to_int(row.get(revenue_col))

        item: dict[str, Any] = {
            "date": order_date,
            "code": code,
            "product": _s(row.get("상품명")),
            "qty": qty,
            "revenue": revenue,
            "cost": None,
            "unit_cost": None,
            "margin": None,
            "margin_rate": None,
            "price_table_cost": None,
            "price_table_diff": None,
            "matched": False,
            "reason": "",
        }

        prefix = mapping.get(code)
        if not prefix:
            item["reason"] = "상품 매핑 없음"
            results.append(item)
            continue
        if not order_date:
            item["reason"] = "주문일자 없음"
            results.append(item)
            continue

        taken_qty, taken_amount, _matched_dates = pool.take(prefix, qty, order_date)
        if taken_qty == 0:
            item["reason"] = f"{order_date} 전후 {DATE_WINDOW}일 내 매입내역 없음"
            results.append(item)
            continue

        cost = taken_amount
        unit_cost = round(taken_amount / taken_qty)
        margin = revenue - cost
        item.update(
            cost=cost,
            unit_cost=unit_cost,
            margin=margin,
            margin_rate=round(margin / revenue * 100, 1) if revenue else None,
            matched=True,
        )
        if taken_qty < qty:
            item["reason"] = f"재고부족(부분매칭 {taken_qty}/{qty})"
        matched_count += 1
        margin_sum += margin
        revenue_sum_matched += revenue

        pt_price = price_table.get(code)
        if pt_price is not None:
            pt_cost = pt_price * qty
            item["price_table_cost"] = pt_cost
            item["price_table_diff"] = pt_cost - cost

        results.append(item)

    total_count = len(results)
    avg_margin_rate = round(margin_sum / revenue_sum_matched * 100, 1) if revenue_sum_matched else None

    return {
        "results": results,
        "total_count": total_count,
        "matched_count": matched_count,
        "unmatched_count": total_count - matched_count,
        "margin_sum": margin_sum,
        "avg_margin_rate": avg_margin_rate,
    }


def build_result_excel(result: dict[str, Any]) -> bytes:
    """calc_margin() 결과를 엑셀 바이트로 만든다 (상단 요약 + 상세 표 한 시트)."""
    import io

    summary = pd.DataFrame(
        [
            {"항목": "전체 건수", "값": result.get("total_count")},
            {"항목": "매칭 건수", "값": result.get("matched_count")},
            {"항목": "매칭안됨 건수", "값": result.get("unmatched_count")},
            {"항목": "마진합계", "값": result.get("margin_sum")},
            {"항목": "평균 마진율(%)", "값": result.get("avg_margin_rate")},
        ]
    )
    detail = pd.DataFrame(
        [
            {
                "주문일자": r["date"],
                "판매자상품코드": r["code"],
                "상품명": r["product"],
                "수량": r["qty"],
                "매출(정산예정금액)": r["revenue"],
                "실제매입가": r["cost"],
                "개당단가": r["unit_cost"],
                "마진": r["margin"],
                "마진율(%)": r["margin_rate"],
                "단가표매입가(참고)": r["price_table_cost"],
                "단가표차이(참고)": r["price_table_diff"],
                "매칭상태": "매칭" if r["matched"] else "매칭안됨",
                "비고": r["reason"],
            }
            for r in result.get("results", [])
        ]
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="건아유통_마진표", index=False, startrow=0)
        detail.to_excel(writer, sheet_name="건아유통_마진표", index=False, startrow=len(summary) + 2)
    return buf.getvalue()

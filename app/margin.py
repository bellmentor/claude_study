"""정산마진확인: '대량' 시트 주문건별로 도매사이트 매입금을 매칭해 마진을 계산한다.

매칭 원리: 판매채널 정산엑셀(대량 시트)과 도매사이트 다운로드 주문엑셀은 서로 다른
시스템이라 주문번호가 다르다(마켓 주문번호 ≠ 도매사이트 내부 주문번호). 두 시스템에
공통으로 남는 유일한 값은 택배사가 발급한 '송장번호'뿐이므로, 송장번호를 유일한
매칭키로 쓴다(히트b2b만 예외 — 송장번호가 없어 상품코드+수령자이름으로 매칭).

송장번호 컬럼이 아예 없는 도매사이트(식자재코리아)나, 다운로드 자체가 요약/집계
형태라 주문 단위 데이터가 없는 사이트(젠트레이드/코코리아/JTC코리아)는 매칭 불가로
표시한다. 아직 dome_site 스크래퍼가 없는 사이트(도매토피아/가구도매/셀러프렌드/
아기넷/유니온펫/온채널)와 소소매(도매 아님) 주문도 매칭 불가로 둔다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from dome_site.order_filters import drop_canceled

ROOT = Path(__file__).resolve().parents[1]
DOME_DIR = ROOT / "dome_site"

SHIPPING_FEE = 3000  # 파라브로/3MRO/필우커머스 — 송장(배송) 1건당 고정 배송비

# 판매자상품코드 접두어 → 도매처 매핑 (사용자 제공, 확정).
# 길이 내림차순으로 정렬해 더 구체적인 접두어를 먼저 검사한다.
PREFIX_SITE_MAP: list[dict[str, Any]] = sorted(
    [
        {"prefix": "SIK", "site_name": "식자재코리아", "slug": "sic", "matchable": False, "reason": "송장번호 없음(매칭불가)"},
        {"prefix": "3MRO", "site_name": "쓰리엠알오", "slug": "3mro", "matchable": True, "reason": ""},
        {"prefix": "ZEN", "site_name": "젠트레이드", "slug": "zentrade", "matchable": False, "reason": "주문 라인 데이터 없음"},
        {"prefix": "FWC", "site_name": "필우커머스", "slug": "feelwoo", "matchable": True, "reason": ""},
        {"prefix": "HIT", "site_name": "히트b2b", "slug": "hit", "matchable": True, "reason": ""},
        {"prefix": "COCO", "site_name": "코코리아", "slug": "cokorea", "matchable": False, "reason": "주문 라인 데이터 없음"},
        {"prefix": "JTC", "site_name": "jtc코리아", "slug": "jtc", "matchable": False, "reason": "주문 라인 데이터 없음"},
        {"prefix": "PRB_", "site_name": "파라브로", "slug": "parabro", "matchable": True, "reason": ""},
        {"prefix": "DOTO", "site_name": "도매토피아", "slug": None, "matchable": False, "reason": "사이트 미등록"},
        {"prefix": "GAGU", "site_name": "가구도매", "slug": None, "matchable": False, "reason": "사이트 미등록"},
        {"prefix": "CNW", "site_name": "셀러프렌드", "slug": None, "matchable": False, "reason": "사이트 미등록"},
        {"prefix": "AGI", "site_name": "아기넷", "slug": None, "matchable": False, "reason": "사이트 미등록"},
        {"prefix": "UNION", "site_name": "유니온펫", "slug": None, "matchable": False, "reason": "사이트 미등록"},
        {"prefix": "79", "site_name": "친구도매", "slug": "79dome", "matchable": True, "reason": ""},
        {"prefix": "ch", "site_name": "온채널", "slug": None, "matchable": False, "reason": "사이트 미등록"},
        {"prefix": "cm", "site_name": "철물박사", "slug": "metaldiy", "matchable": True, "reason": ""},
    ],
    key=lambda s: -len(s["prefix"]),
)

# 오너클랜만 접두어가 아니라 코드 자체(또는 'OWNER_' 를 뗀 나머지)가 'W' 로 시작한다.
OWNERCLAN_SITE = {"prefix": "W", "site_name": "오너클랜", "slug": "ownerclan", "matchable": True, "reason": ""}

UNKNOWN_SITE = {"prefix": None, "site_name": None, "slug": None, "matchable": False, "reason": "미분류 코드"}

GROUPED_SLUGS = {"parabro", "3mro", "feelwoo"}  # 상품금액 + 송장당 배송비 1회
SIMPLE_SLUGS = {"ownerclan", "metaldiy"}  # 다운로드 컬럼 값 그대로


def detect_site(product_code: str) -> dict[str, Any]:
    """판매자상품코드에서 도매사이트를 판별한다. 못 찾으면 UNKNOWN_SITE."""
    code = (product_code or "").strip()
    if not code:
        return UNKNOWN_SITE
    code_u = code.upper()

    body = code_u
    if body.startswith("OWNER_"):
        body = body[6:]
    elif body.startswith("OWNER"):
        body = body[5:]
    if body.startswith("W"):
        return OWNERCLAN_SITE

    for site in PREFIX_SITE_MAP:
        if code_u.startswith(site["prefix"].upper()):
            return site
    return UNKNOWN_SITE


# ── 공통 파싱 헬퍼 ─────────────────────────────────────────
def _to_int(value) -> int:
    """'12,000' / '12,000원' / 12000.0 등을 정수로. 실패/빈값은 0."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    s = re.sub(r"[^0-9.\-]", "", str(value))
    if s in ("", "-", ".", "-."):
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        digits = "".join(ch for ch in s if ch.isdigit())
        return int(digits) if digits else 0


def _s(value) -> str:
    """셀 값을 표시용 문자열로. NaN/None 은 빈 문자열."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _norm_key(value) -> str:
    """송장번호 등 매칭키 정규화. 엑셀에서 숫자로 읽혀 '1234.0' 이 된 케이스를 보정."""
    s = _s(value)
    if not s or s.lower() in ("nan", "none"):
        return ""
    if re.match(r"^\d+\.0+$", s):
        s = s.split(".")[0]
    return s


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """컬럼명에 keywords 중 하나라도 포함된 첫 컬럼명을 반환. 없으면 None."""
    for col in df.columns:
        name = str(col)
        for kw in keywords:
            if kw in name:
                return col
    return None


def _read_downloads(slug: str) -> pd.DataFrame:
    """dome_site/<slug>/downloads/ 에 누적된 엑셀 전체를 concat 해 반환."""
    d = DOME_DIR / slug / "downloads"
    if not d.exists():
        return pd.DataFrame()
    frames = []
    for f in sorted(d.glob("*.xlsx")):
        if f.name.startswith("~"):
            continue
        try:
            frames.append(pd.read_excel(f))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ── 사이트별 다운로드 인덱스 구성 ──────────────────────────
def _build_simple_index(slug: str, inv_kw: list[str], amount_kw: list[str]) -> dict[str, list[int]]:
    """송장번호별 [금액, 금액, ...] 리스트 (컬럼 값 그대로가 매입금)."""
    df = _read_downloads(slug)
    if df.empty:
        return {}
    inv_col = _find_col(df, inv_kw)
    amt_col = _find_col(df, amount_kw)
    if inv_col is None or amt_col is None:
        return {}
    idx: dict[str, list[int]] = {}
    for _, r in df.iterrows():
        inv = _norm_key(r.get(inv_col))
        if not inv:
            continue
        idx.setdefault(inv, []).append(_to_int(r.get(amt_col)))
    return idx


def _build_grouped_index(slug: str, inv_kw: list[str], amount_kw: list[str]) -> dict[str, list[int]]:
    """송장번호별 [상품금액, ...] 리스트 (배송비는 매칭 시 송장당 1회 별도 가산)."""
    df = _read_downloads(slug)
    if df.empty:
        return {}
    inv_col = _find_col(df, inv_kw)
    amt_col = _find_col(df, amount_kw)
    if inv_col is None or amt_col is None:
        return {}
    idx: dict[str, list[int]] = {}
    for _, r in df.iterrows():
        inv = _norm_key(r.get(inv_col))
        if not inv:
            continue
        idx.setdefault(inv, []).append(_to_int(r.get(amt_col)))
    return idx


def _build_3mro_index() -> dict[str, list[int]]:
    """3MRO 는 '가격×수량' 이 상품금액(다운로드에 합계 컬럼이 없어 직접 계산)."""
    df = _read_downloads("3mro")
    if df.empty:
        return {}
    inv_col = _find_col(df, ["송장번호", "송장"])
    price_col = _find_col(df, ["가격"])
    qty_col = _find_col(df, ["수량"])
    if inv_col is None or price_col is None or qty_col is None:
        return {}
    idx: dict[str, list[int]] = {}
    for _, r in df.iterrows():
        inv = _norm_key(r.get(inv_col))
        if not inv:
            continue
        amt = _to_int(r.get(price_col)) * _to_int(r.get(qty_col))
        idx.setdefault(inv, []).append(amt)
    return idx


def _build_79dome_index() -> dict[str, list[tuple[int, int]]]:
    """친구도매: 송장번호별 [(상품금액, 배송비), ...]. 배송비는 송장당 1회만 가산."""
    df = _read_downloads("79dome")
    if df.empty:
        return {}
    inv_col = _find_col(df, ["송장번호", "송장"])
    price_col = _find_col(df, ["가격"])
    qty_col = _find_col(df, ["수량"])
    ship_col = _find_col(df, ["배송비"])
    if inv_col is None or price_col is None or qty_col is None or ship_col is None:
        return {}
    idx: dict[str, list[tuple[int, int]]] = {}
    for _, r in df.iterrows():
        inv = _norm_key(r.get(inv_col))
        if not inv:
            continue
        amt = _to_int(r.get(price_col)) * _to_int(r.get(qty_col))
        ship = _to_int(r.get(ship_col))
        idx.setdefault(inv, []).append((amt, ship))
    return idx


def _build_hit_index() -> dict[str, list[int]]:
    """히트b2b: 송장번호가 없어 (상품코드|수령자이름) 조합으로 매칭."""
    df = _read_downloads("hit")
    if df.empty:
        return {}
    prod_col = _find_col(df, ["품목코드", "상품번호"])
    recv_col = _find_col(df, ["수령자이름", "수령자"])
    amt_col = _find_col(df, ["실결제금액", "결제금액", "실결제", "결제금"])
    if prod_col is None or recv_col is None or amt_col is None:
        return {}
    idx: dict[str, list[int]] = {}
    for _, r in df.iterrows():
        prod = _norm_key(r.get(prod_col))
        recv = _norm_key(r.get(recv_col))
        if not prod or not recv:
            continue
        key = f"{prod}|{recv}"
        idx.setdefault(key, []).append(_to_int(r.get(amt_col)))
    return idx


_INDEX_BUILDERS = {
    "ownerclan": lambda: _build_simple_index("ownerclan", ["송장번호", "송장"], ["총결제금액", "결제금액"]),
    "metaldiy": lambda: _build_simple_index("metaldiy", ["송장번호", "송장"], ["결제금액", "실결제금액", "결제금"]),
    "parabro": lambda: _build_grouped_index("parabro", ["송장", "운송장"], ["상품금액", "판매금액", "공급가", "결제금액", "금액"]),
    "feelwoo": lambda: _build_grouped_index("feelwoo", ["운송장", "송장"], ["상품금액", "판매금액", "공급가", "결제금액", "금액"]),
    "3mro": _build_3mro_index,
    "79dome": _build_79dome_index,
    "hit": _build_hit_index,
}


def _match_cost(slug: str, index: dict, used_invoices: set[str], row: pd.Series) -> int | None:
    """대량 시트 한 행에 대해 매입금을 매칭한다. 매칭 실패 시 None."""
    if slug == "hit":
        code = _s(row.get("판매자상품코드"))
        local = re.sub(r"^HIT_?", "", code, flags=re.IGNORECASE)
        recv = _norm_key(row.get("수령자"))
        key = f"{local}|{recv}"
        candidates = index.get(key)
        if not candidates:
            return None
        return candidates.pop(0)

    inv = _norm_key(row.get("송장번호"))
    if not inv:
        return None
    candidates = index.get(inv)
    if not candidates:
        return None

    if slug in SIMPLE_SLUGS:
        return candidates.pop(0)

    if slug in GROUPED_SLUGS:
        base = candidates.pop(0)
        shipping = 0
        if inv not in used_invoices:
            used_invoices.add(inv)
            shipping = SHIPPING_FEE
        return base + shipping

    if slug == "79dome":
        amt, ship = candidates.pop(0)
        shipping = 0
        if inv not in used_invoices:
            used_invoices.add(inv)
            shipping = ship
        return amt + shipping

    return None


# ── '대량' 시트 읽기 ────────────────────────────────────────
_HEADER_KEYWORDS = ("판매자상품코드", "정산예정금액")


def _read_daeryang_sheet(path: Path) -> pd.DataFrame:
    """'대량' 시트를 읽는다. 헤더가 1행이 아닐 수 있어 키워드로 헤더 행을 찾는다.

    헤더 행을 찾은 뒤에는 pd.read_excel(header=N) 로 다시 읽는다 — 직접
    raw.iloc[...] 를 잘라 data.columns 에 대입하면 동명 컬럼이 있을 때
    pandas 가 자동으로 해주는 중복 컬럼명 dedup(".1" 접미사)이 빠져서,
    df[col] 조회 시 Series 여러 개가 겹쳐 나오는 사고가 난다(그 상태로
    금액을 문자열화하면 인덱스 숫자까지 뒤섞여 말도 안 되는 큰 숫자가 됨).
    """
    raw = pd.read_excel(path, sheet_name="대량", header=None, dtype=object, nrows=5)
    header_row = None
    for r in range(len(raw)):
        vals = [_s(v) for v in raw.iloc[r].tolist()]
        if all(any(kw in v for v in vals) for kw in _HEADER_KEYWORDS):
            header_row = r
            break
    if header_row is None:
        raise ValueError("'대량' 시트에서 헤더 행을 찾지 못했습니다 (판매자상품코드/정산예정금액 컬럼 필요)")
    return pd.read_excel(path, sheet_name="대량", header=header_row)


def has_daeryang_sheet(path: Path) -> bool:
    """엑셀에 '대량' 시트가 있는지 확인한다."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        try:
            return "대량" in wb.sheetnames
        finally:
            wb.close()
    except Exception:
        return False


# ── 메인: 주문건별 마진 계산 ────────────────────────────────
def calc_margin(excel_path: Path) -> dict[str, Any]:
    """'대량' 시트를 읽어 주문건별 매입금을 매칭하고 마진/마진율을 계산한다."""
    df = _read_daeryang_sheet(excel_path)

    status_col = "주문상태" if "주문상태" in df.columns else None
    df = drop_canceled(df, status_col)

    code_col = "판매자상품코드"
    revenue_col = "정산예정금액(배송비포함)"
    paid_col = "실결제금액(배송비포함)"
    if code_col not in df.columns or revenue_col not in df.columns:
        raise ValueError(
            f"필요한 컬럼이 없습니다({code_col}/{revenue_col}). 실제 컬럼: {list(df.columns)}"
        )

    site_index_cache: dict[str, dict] = {}
    used_invoices_cache: dict[str, set[str]] = {}

    results: list[dict[str, Any]] = []
    matched_count = 0
    margin_sum = 0
    revenue_sum_matched = 0

    for _, row in df.iterrows():
        code = _s(row.get(code_col))
        site = detect_site(code)
        revenue = _to_int(row.get(revenue_col))
        paid = _to_int(row.get(paid_col)) if paid_col in df.columns else None

        item: dict[str, Any] = {
            "date": _s(row.get("주문일자(yyyy-MM-dd).")) or _s(row.get("주문일시")),
            "market": _s(row.get("쇼핑몰")),
            "code": code,
            "site_name": site["site_name"] or "미분류",
            "product": _s(row.get("상품명")),
            "qty": _to_int(row.get("수량")),
            "recipient": _s(row.get("수령자")),
            "invoice": _s(row.get("송장번호")),
            "paid": paid,
            "revenue": revenue,
            "cost": None,
            "margin": None,
            "margin_rate": None,
            "matched": False,
            "reason": site["reason"],
        }

        slug = site["slug"]
        if site["matchable"] and slug:
            if slug not in site_index_cache:
                site_index_cache[slug] = _INDEX_BUILDERS[slug]()
                used_invoices_cache[slug] = set()
            cost = _match_cost(slug, site_index_cache[slug], used_invoices_cache[slug], row)
            if cost is not None:
                margin = revenue - cost
                item["cost"] = cost
                item["margin"] = margin
                item["margin_rate"] = round(margin / revenue * 100, 1) if revenue else None
                item["matched"] = True
                item["reason"] = ""
                matched_count += 1
                margin_sum += margin
                revenue_sum_matched += revenue
            else:
                item["reason"] = "다운로드에서 못 찾음"

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


# ── 결과 엑셀 내보내기 ──────────────────────────────────────
def build_result_excel(result: dict[str, Any]) -> bytes:
    """calc_margin() 결과를 엑셀 바이트로 만든다 (상단 요약 + 상세 표 한 시트)."""
    import io

    summary = pd.DataFrame([
        {"항목": "전체 건수", "값": result.get("total_count")},
        {"항목": "매칭 건수", "값": result.get("matched_count")},
        {"항목": "매칭안됨 건수", "값": result.get("unmatched_count")},
        {"항목": "마진합계", "값": result.get("margin_sum")},
        {"항목": "평균 마진율(%)", "값": result.get("avg_margin_rate")},
    ])

    detail = pd.DataFrame([
        {
            "주문일자": r["date"],
            "쇼핑몰": r["market"],
            "도매처": r["site_name"],
            "판매자상품코드": r["code"],
            "상품명": r["product"],
            "수량": r["qty"],
            "수령자": r["recipient"],
            "정산예정금액(배송비포함)": r["revenue"],
            "매입금": r["cost"],
            "마진": r["margin"],
            "마진율(%)": r["margin_rate"],
            "매칭여부": "매칭" if r["matched"] else "매칭안됨",
            "비고": r["reason"],
        }
        for r in result.get("results", [])
    ])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="정산마진확인", index=False, startrow=0)
        detail.to_excel(writer, sheet_name="정산마진확인", index=False, startrow=len(summary) + 2)
    return buf.getvalue()

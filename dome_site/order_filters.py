"""도매처 공용 주문 필터.

여러 사이트의 summarize 에서 공통으로 쓰는 주문 제외 규칙을 모아둔다.
(CLAUDE.md 규칙: 공용 헬퍼는 두 번째 사이트부터 추출한다.)
"""

from __future__ import annotations

import pandas as pd

# 매입금 계산에서 제외해야 하는 '취소류' 주문상태 키워드.
# 주문상태 컬럼 값에 이 단어들이 포함되면 해당 주문건을 뺀다.
CANCEL_KEYWORDS = ["취소", "반품", "교환", "환불"]


def drop_canceled(
    df: pd.DataFrame,
    status_col: str | None,
    keywords: list[str] = CANCEL_KEYWORDS,
    log=None,
) -> pd.DataFrame:
    """주문상태에 취소/반품/교환/환불 등이 포함된 행을 제거한 DataFrame 을 반환한다.

    status_col 이 없으면(None/미존재) 원본을 그대로 반환한다.
    log 를 주면 제외 건수를 기록한다.
    """
    if status_col is None or status_col not in df.columns:
        if log is not None:
            log.warn("주문상태 컬럼이 없어 취소/반품/교환/환불 제외를 건너뜁니다")
        return df

    pattern = "|".join(keywords)
    mask = df[status_col].astype(str).str.contains(pattern, na=False)
    removed = int(mask.sum())
    if log is not None:
        log.info(
            f"취소류({'/'.join(keywords)}) 주문 {removed}건 제외 → {len(df) - removed}건"
        )
    return df[~mask]

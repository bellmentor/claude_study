"""도매사이트 공용 디버그 로거.

단계별 진행 로그 + 소요시간 측정 + 에러 시 스크린샷/HTML 덤프.
모든 출력은 print()로 stdout에 찍어서 Web UI subprocess 파이프와 호환된다.
"""

from __future__ import annotations

import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

DUMP_DIR = Path(__file__).resolve().parent / "error_dumps"


class SiteLogger:
    """사이트별 로거. 단계 타이밍과 에러 덤프를 관리한다."""

    def __init__(self, site_label: str) -> None:
        self.site = site_label
        self._step_start: float | None = None
        self._step_name: str = ""
        self._flow_start: float | None = None

    # ── 전체 흐름 ──

    def flow_start(self, name: str) -> None:
        """전체 흐름 시작."""
        self._flow_start = time.time()
        self._print("시작", name)

    def flow_end(self) -> None:
        """전체 흐름 종료 + 총 소요시간."""
        if self._flow_start:
            elapsed = time.time() - self._flow_start
            self._print("완료", f"총 소요시간: {self._fmt_time(elapsed)}")
            self._flow_start = None

    # ── 단계별 ──

    def step(self, name: str, detail: str = "") -> None:
        """새 단계 시작. 이전 단계가 있으면 소요시간 출력."""
        self._close_step()
        self._step_name = name
        self._step_start = time.time()
        msg = name
        if detail:
            msg += f" - {detail}"
        self._print("단계", msg)

    def info(self, msg: str) -> None:
        """일반 정보 로그."""
        prefix = f"[{self._step_name}]" if self._step_name else ""
        self._print("정보", f"{prefix} {msg}" if prefix else msg)

    def debug(self, msg: str) -> None:
        """디버그 상세 로그."""
        prefix = f"[{self._step_name}]" if self._step_name else ""
        self._print("디버그", f"{prefix} {msg}" if prefix else msg)

    def warn(self, msg: str) -> None:
        """경고 로그."""
        self._print("경고", msg)

    def success(self, msg: str) -> None:
        """성공 로그 + 현재 단계 소요시간."""
        self._close_step()
        self._print("성공", msg)

    def error(self, msg: str) -> None:
        """에러 로그."""
        self._print("에러", msg)

    # ── 에러 덤프 ──

    async def dump_on_error(self, page: Page, error: Exception) -> None:
        """에러 발생 시 스크린샷 + HTML 저장."""
        DUMP_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%y%m%d_%H%M%S")
        prefix = f"{ts}_{self.site}"

        # 스크린샷
        try:
            ss_path = DUMP_DIR / f"{prefix}_screenshot.png"
            await page.screenshot(path=str(ss_path), full_page=True)
            self._print("덤프", f"스크린샷 저장: {ss_path}")
        except Exception as e:
            self._print("덤프", f"스크린샷 실패: {e}")

        # HTML
        try:
            html_path = DUMP_DIR / f"{prefix}_page.html"
            content = await page.content()
            html_path.write_text(content, encoding="utf-8")
            self._print("덤프", f"HTML 저장: {html_path}")
        except Exception as e:
            self._print("덤프", f"HTML 저장 실패: {e}")

        # 에러 상세
        self._print("에러", f"{type(error).__name__}: {error}")
        self._print("에러", f"URL: {page.url}")
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        for line in tb:
            for sub in line.rstrip().split("\n"):
                self._print("traceback", sub)

    # ── 내부 ──

    def _close_step(self) -> None:
        """이전 단계 소요시간 출력."""
        if self._step_start and self._step_name:
            elapsed = time.time() - self._step_start
            self._print("소요", f"[{self._step_name}] {self._fmt_time(elapsed)}")
            self._step_start = None

    def _print(self, level: str, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}][{self.site}][{level}] {msg}", flush=True)

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        if seconds < 60:
            return f"{seconds:.1f}초"
        m, s = divmod(seconds, 60)
        return f"{int(m)}분 {s:.1f}초"

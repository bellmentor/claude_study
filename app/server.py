"""매입금 수집 Web UI 서버.

각 도매처 모듈을 subprocess(python -m dome_site.<slug>.main)로 실행하고,
stdout 출력을 WebSocket으로 브라우저에 실시간 전달한다.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

# 서버 콘솔 출력을 UTF-8 로 고정한다.
# (Windows cp949 콘솔/파이프에서 한글·기호가 깨지거나 UnicodeEncodeError 로 죽는 것을 방지)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

import openpyxl
import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# ── 경로 설정 ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent
ACCOUNT_XLSX = ROOT / "계정정보.xlsx"
SITE_LIST_TXT = ROOT / "dome_site" / "도매사이트_폴더_이름.txt"
SUMMARY_XLSX = ROOT / "dome_site" / "도매_매입금.xlsx"
PYTHON = sys.executable

# ── 로그 버퍼 + WebSocket 브로드캐스터 ─────────────────────
# 로그는 HTTP 폴링(상태 조회)으로 받는 것을 1차 채널로 한다. WebSocket 은
# 리로드/늦은 연결 시 메시지를 놓치므로, 버퍼에 쌓아두고 폴링으로 재생한다.
_logs: list[str] = []
_ws_clients: set[WebSocket] = set()
_collect_status: dict[str, dict[str, Any]] = {}
_collect_running = False
_main_loop: asyncio.AbstractEventLoop | None = None


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    yield


# ── FastAPI 앱 ─────────────────────────────────────────────
app = FastAPI(title="매입금 수집", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


async def broadcast_log(message: str) -> None:
    """연결된 모든 WebSocket 클라이언트에 로그 메시지를 전송한다."""
    dead: set[WebSocket] = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


def send_log(message: str) -> None:
    """어느 스레드에서든 호출 가능한 로그 전송. 버퍼에 쌓고 WebSocket 으로도 보낸다."""
    msg = message.strip()
    if not msg:
        return
    _logs.append(msg)  # 폴링으로 재생할 버퍼 (1차 채널)
    if _main_loop:  # 연결돼 있으면 실시간 전송 (보조 채널)
        asyncio.run_coroutine_threadsafe(broadcast_log(msg), _main_loop)


# ── 도매사이트 목록 파싱 ───────────────────────────────────
def load_site_list() -> list[dict[str, str]]:
    """도매사이트_폴더_이름.txt 를 파싱하여 [{name, slug}] 반환."""
    sites: list[dict[str, str]] = []
    text = SITE_LIST_TXT.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("----"):
            break
        if ":" in line:
            name, slug = line.split(":", 1)
            name, slug = name.strip(), slug.strip()
            if slug:
                sites.append({"name": name, "slug": slug})
    return sites


# ── 사이트별 subprocess 실행 ──────────────────────────────
def _run_site_subprocess(slug: str, name: str, year: int, month: int) -> None:
    """별도 스레드에서 python -m dome_site.<slug>.main 을 subprocess로 실행한다."""
    _collect_status[slug] = {"name": name, "status": "실행 중...", "amount": ""}
    send_log(f"[{name}] 수집 시작 ({year}년 {month}월)")

    try:
        env = {**__import__("os").environ, "WEBUI": "1", "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(
            [PYTHON, "-m", f"dome_site.{slug}.main", str(year), str(month)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        for line in proc.stdout:
            line = line.rstrip()
            if line:
                # 서버를 띄운 터미널에도 그대로 출력 (도매처 상세 로그를 콘솔에서 확인)
                print(line, flush=True)
                # 브라우저 로그 박스로 전송
                send_log(line)

        proc.wait()

        if proc.returncode == 0:
            _collect_status[slug]["status"] = "완료"
            send_log(f"[{name}] 수집 완료")
        else:
            _collect_status[slug]["status"] = f"오류 (코드: {proc.returncode})"
            send_log(f"[{name}] 오류 발생 (종료코드: {proc.returncode})")

    except Exception as e:
        _collect_status[slug]["status"] = f"오류: {e}"
        send_log(f"[{name}] 실행 오류: {e}")


def _run_all_sites(sites: list[dict], year: int, month: int) -> None:
    """모든 선택된 사이트를 순차 실행한다. 별도 스레드에서 호출."""
    global _collect_running
    try:
        for site in sites:
            _run_site_subprocess(site["slug"], site["name"], year, month)

        # 완료 후 매입금 읽기
        _read_amounts(year, month)
        send_log("=== 모든 수집 완료 ===")
    finally:
        _collect_running = False


def _read_amounts(year: int, month: int) -> None:
    """도매_매입금.xlsx 에서 해당 월의 매입금을 읽어 status에 반영한다."""
    if not SUMMARY_XLSX.exists():
        return
    try:
        df = pd.read_excel(SUMMARY_XLSX)
        yy, mm = str(year)[2:], f"{month:02d}"
        month_label = f"{yy}년{mm}월"
        # slug → 한글이름 매핑
        site_list = load_site_list()
        slug_to_name = {s["slug"]: s["name"] for s in site_list}
        for slug, info in _collect_status.items():
            korean_name = slug_to_name.get(slug, info["name"])
            row = df[(df["몇월"] == month_label) & (df["도매사이트"] == korean_name)]
            if not row.empty:
                amount = int(row.iloc[0]["매입금"])
                _collect_status[slug]["amount"] = f"{amount:,}"
    except Exception:
        pass


# ── 페이지 ─────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """메인 페이지."""
    sites = load_site_list()
    return templates.TemplateResponse(request, "index.html", {"sites": sites})


# ── 계정 API ──────────────────────────────────────────────
@app.get("/api/accounts")
async def get_accounts():
    """계정정보.xlsx 에서 계정 목록을 읽어 반환한다."""
    if not ACCOUNT_XLSX.exists():
        return {"accounts": [], "error": "계정정보.xlsx 파일이 없습니다"}

    wb = openpyxl.load_workbook(ACCOUNT_XLSX, data_only=True)
    ws = wb["Sheet1"]
    accounts = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        if row and row[0]:
            accounts.append({
                "site": str(row[0]),
                "user_id": str(row[1]) if row[1] else "",
                "password": str(row[2]) if row[2] else "",
            })
    wb.close()
    return {"accounts": accounts}


@app.put("/api/accounts")
async def put_accounts(request: Request):
    """계정정보를 수정하여 xlsx 에 저장한다."""
    if not ACCOUNT_XLSX.exists():
        return {"error": "계정정보.xlsx 파일이 없습니다. 직접 생성해주세요."}

    body = await request.json()
    accounts = body.get("accounts", [])

    wb = openpyxl.load_workbook(ACCOUNT_XLSX)
    ws = wb["Sheet1"]
    for r_idx in range(1, ws.max_row + 1):
        for c_idx in range(1, 4):
            ws.cell(row=r_idx, column=c_idx, value=None)

    for i, acc in enumerate(accounts, start=1):
        ws.cell(row=i, column=1, value=acc.get("site", ""))
        ws.cell(row=i, column=2, value=acc.get("user_id", ""))
        ws.cell(row=i, column=3, value=acc.get("password", ""))

    wb.save(ACCOUNT_XLSX)
    wb.close()
    return {"ok": True}


# ── 수집 API ──────────────────────────────────────────────
@app.post("/api/collect")
async def start_collect(request: Request):
    """매입금 수집을 시작한다."""
    global _collect_running
    if _collect_running:
        return {"error": "이미 수집이 진행 중입니다"}

    body = await request.json()
    sites: list[dict[str, str]] = body.get("sites", [])
    start_date: str = body.get("start_date", "")
    end_date: str = body.get("end_date", "")

    if not sites or not start_date or not end_date:
        return {"error": "사이트 목록과 날짜를 입력해주세요"}

    # start_date에서 year, month 추출
    parts = start_date.split("-")
    year, month = int(parts[0]), int(parts[1])

    _collect_running = True
    _collect_status.clear()
    _logs.clear()  # 새 수집 시작 시 로그 버퍼 초기화

    thread = threading.Thread(
        target=_run_all_sites, args=(sites, year, month), daemon=True
    )
    thread.start()
    return {"ok": True, "message": "수집을 시작했습니다"}


@app.get("/api/collect/status")
async def collect_status(since: int = 0):
    """현재 수집 진행상황 + since 인덱스 이후의 새 로그를 반환한다."""
    new_logs = _logs[since:] if since < len(_logs) else []
    return {
        "running": _collect_running,
        "sites": _collect_status,
        "logs": new_logs,
        "log_count": len(_logs),
    }


# ── WebSocket ─────────────────────────────────────────────
@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    """실시간 로그 WebSocket."""
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)


# ── 실행 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=True)

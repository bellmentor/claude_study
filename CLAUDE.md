# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 저장소 목적

한국 도매(都賣) 전자상거래 사이트 접속후 주문목록을 크롤링,관리하는 저장소다. 각 사이트는 `dome_site/` 하위에 자체 폴더를 가지며, 그 안의 `<site>_get.txt` 파일에 URL, 로그인 엔드포인트 등 스크래핑에 필요한 정보를 정리한다. 현재는 애플리케이션 코드, 빌드 시스템, 테스트가 없는 노트 스캐폴드 단계다.

## 아키텍처

- **사이트별 독립 모듈** (`dome_site/<slug>/`) — 한 도매 사이트의 접속/로그인/주문목록 수집 등 모든 작업 코드를 자체 폴더에 둔다. 사이트끼리는 서로의 코드를 import 하지 않는다. 새 사이트 추가 = 새 폴더 추가.
- **메인 웹 오케스트레이터** (`app/`, 추후 구축) — 로컬에서 돌아가는 웹 UI. 각 사이트 모듈의 함수를 import 해 "오너클랜 → 로그인", "오너클랜 → 주문목록(날짜)" 같은 버튼/엔드포인트에 연결한다.
- **자격 정보 단일 출처**: 저장소 루트의 `계정정보.xlsx`. 모든 사이트 모듈이 이 파일에서 자기 계정을 동적으로 읽는다. 코드/노트 어디에도 ID·비밀번호를 박지 않는다.

## 구조 및 명명 규칙

- `dome_site/<slug>/` 폴더명은 `dome_site/도매사이트_폴더_이름.txt` 의 매핑(한글이름 : slug)과 일치해야 한다. `---- 이하 소소매 --` 구분선 아래는 도매가 아닌 소소매 항목이며 슬러그 부여 대상 아님.
- `dome_site/<slug>/<slug>_get.txt` — 사이트 조사 노트. 첫 줄 `url : <주소>`, 이후 `1. 로그인 : <주소>` 형식의 번호 항목. 기준: `dome_site/ownerclan/ownerclan_get.txt`.
- `계정정보.xlsx` — 계정 정보 워크북. `.gitignore`로 추적에서 제외되어 있으며 절대 커밋하지 않는다. 내용을 추적 파일로 옮기는 것도 금지한다.

## 사이트 모듈 작성 규칙

- **모듈 구성**: 사이트 폴더는 파이썬 패키지로 구성한다 (`__init__.py` 필요). 표준 파일:
  - `main.py` — 도매처 전체 흐름 오케스트레이터 (로그인 → 주문조회/엑셀 다운로드 → 매입금 합산). `run(year, month)` 함수로 진입. 기준 구현: `dome_site/ownerclan/main.py`.
  - `session.py` — 모듈 수준 브라우저 세션 관리 (필수, 사이트마다 하나).
  - `summarize.py` — 다운로드된 엑셀에서 총결제금액 합산 → `dome_site/도매_매입금.xlsx` 에 기록. 기준 구현: `dome_site/ownerclan/summarize.py`.
  - 오퍼레이션 파일들 — `login.py`, `orders.py`, `logout.py` 등 작업 단위로 분리. 한 파일에 한 오퍼레이션 집중. 오퍼레이션 파일은 자기 작업만 수행하고, 흐름 제어는 `main.py`에 맡긴다.
- **함수 명명**: 동사_명사 snake_case 영어. 함수 위에 한 줄 한글 docstring 필수(메인 웹의 버튼 라벨과 1:1 대응되도록).
  - `login()` — 로그인. 성공 시 인증된 Playwright `BrowserContext`/`Page` 반환 가능(세션 재사용 대비).
  - `fetch_orders(start_date, end_date)` — 주문목록 수집. 날짜는 `YYYY-MM-DD` 문자열 또는 `datetime.date`.
  - `logout()`, `close()` — 필요 시.
- **자격 정보 로딩**: 사이트 모듈이 `계정정보.xlsx` (Sheet1, 컬럼 `사이트/아이디/비번`) 에서 한글 사이트명으로 자기 행을 찾는다. 기준 구현: `dome_site/ownerclan/login.py` 의 `load_credentials()`. 공용 헬퍼는 **두 번째 사이트를 만들 때** 추출 (추측 추상화 금지).
- **실행 방식**: 도매처 전체 흐름은 `python -m dome_site.<slug>.main` 으로 실행한다. 개별 오퍼레이션 테스트는 `python -m dome_site.<slug>.login` 등으로 단독 실행. `login.py` 등 개별 테스트가 필요한 모듈만 `if __name__ == "__main__":` 블록을 둔다. 오퍼레이션 파일(orders.py 등)은 순수 함수만 제공하고 단독 실행 블록을 두지 않는다.
- **메인 웹 호출 계약**: 메인 웹은 `from dome_site.<slug>.<op_module> import <op_func>` 로 호출한다. 따라서 부수효과(브라우저 띄우기, 네트워크 요청)는 import 시점이 아니라 함수 호출 시점에 일어나야 한다.
- **Playwright 세션 정책 (필수)**: **같은 도매처 안의 모든 오퍼레이션은 같은 브라우저 세션을 공유**한다. 오퍼레이션마다 브라우저를 닫고 다시 띄우면 로그인 쿠키가 유실되므로 **금지**. 다른 도매처로 전환할 때만 세션을 닫는다. 구현 규칙:
  - 사이트 패키지의 `session.py` 에 모듈 수준 컨테이너로 `playwright`/`browser`/`context`/`page` 인스턴스를 보관한다.
  - 표준 API 3개를 노출한다:
    - `open_session(headless: bool = True) -> Page` — 세션이 없으면 시작, 있으면 기존 Page 반환.
    - `get_page() -> Page` — 살아있는 Page 반환. 없으면 자동으로 `open_session()` 호출.
    - `close_session()` — 세션 종료. **다른 도매처로 전환할 때만 호출** (같은 도매처 작업 중에는 호출 금지).
  - 모든 오퍼레이션 함수(`login`, `fetch_orders` …)는 `get_page()` 만 호출하고 세션 생명주기에는 관여하지 않는다.
  - 기준 구현: `dome_site/ownerclan/session.py`.
- **디버그/릴리즈 모드**: 각 사이트의 `session.py` 최상단에 `MODE` 상수를 둔다.
  - `MODE = "debug"` — 브라우저 창을 띄워서 사람이 직접 보면서 확인 (개발/디버깅 단계 기본값).
  - `MODE = "release"` — headless 로 실행 (속도 우선). 해당 사이트의 크롤링이 안정화된 뒤에만 전환.
  - 단독 실행(`python -m dome_site.<slug>.<op>`) 시 진입점은 `MODE == "debug"` 면 `close_session()` 전에 Enter 키 대기를 넣어 브라우저 창이 즉시 닫히지 않도록 한다 (기준 구현: `dome_site/ownerclan/login.py` 의 `_standalone()`).

## 새 사이트 추가 절차

1. `도매사이트_폴더_이름.txt` 에 `한글이름 : slug` 줄을 추가 (현재 슬러그 미부여: 가구도매, 유니온펫, 온채널).
2. `dome_site/<slug>/` 폴더 생성, `<slug>_get.txt` 에 URL/로그인 엔드포인트 정리.
3. `계정정보.xlsx` 해당 행에 ID/비밀번호 입력 (xlsx 는 커밋되지 않음).
4. `dome_site/<slug>/__init__.py` (빈 파일) 과 `session.py` 작성 — 기준 모델: `dome_site/ownerclan/session.py`. 이어서 `login.py` 작성 (`from .session import get_page` 로 세션 공유). 기준 모델: `dome_site/ownerclan/login.py`.
5. 이후 사용자 지시에 따라 `orders.py` 등 오퍼레이션 모듈을 순서대로 추가.
6. `app/` 메인 웹이 존재한다면, 사이트 등록 지점에 새 사이트를 노출(등록 방식은 메인 웹 설계 시 정의).

## 엑셀 처리

- 엑셀 파일을 읽고 쓸 때는 **pandas를 우선** 사용한다. openpyxl은 pandas가 처리할 수 없는 경우(셀 서식 등)에만 사용.

## 작업 언어 및 인코딩

- 모든 노트, 폴더 라벨, 커밋 메시지, 그리고 Claude의 설명/응답은 **한국어**로 작성한다. (기존 커밋: `도매사이트 수집 txt 추가`, `도매사이트별 폴더 추가`)
- 파일을 생성하거나 수정할 때는 **반드시 UTF-8 인코딩**을 사용해 한글이 깨지지 않도록 한다. BOM 없이 저장하고, 줄바꿈 등으로 인한 한글 손상이 의심되면 즉시 다시 확인한다.

## 진행상황 확인 (필수)

- 작업 시작 전 **반드시 `진행상황.txt`와 `web_ui_진행상황.txt`를 읽고 숙지**한다. 어떤 도매처가 완료/미완료인지, Web UI 구현이 어디까지 진행됐는지 파악한 뒤 작업에 들어간다.
- 작업이 끝나면 `진행상황.txt` 또는 `web_ui_진행상황.txt`를 최신 상태로 업데이트한다.

## 작업 진행 방식

- **권한 질문 금지**: 사용자가 명령을 내렸을 때 Bash 실행, 파일 수정, 프로젝트 내 작업에 대해 추가 확인이나 권한 질문 없이 그대로 진행한다. (실제 권한 프롬프트는 하네스 설정에서 통제되므로, 자주 막힌다면 `.claude/settings.json` 에 allowlist를 추가해 둔다.)
- **Git은 사용자가 직접 한다**: `git status` 포함 모든 git 명령은 "커밋해줘", "푸시해줘" 같은 명확한 지시가 있을 때만 실행. 질문("커밋해도 돼?")은 실행 지시가 아님.

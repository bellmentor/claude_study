// ── 탭 전환 ──────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');

        if (btn.dataset.tab === 'settings') loadAccounts();
    });
});

// ── 달력 ─────────────────────────────────────────
const calMonth = document.getElementById('cal-month');
const calYear = document.getElementById('cal-year');
const calGrid = document.querySelector('#calendar-grid tbody');
const rangeDisplay = document.getElementById('range-display');

let currentYear, currentMonth;
let rangeStart = null, rangeEnd = null;

function initCalendar() {
    const now = new Date();
    currentYear = now.getFullYear();
    currentMonth = now.getMonth();

    // 월 드롭다운
    for (let m = 0; m < 12; m++) {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = (m + 1) + '월';
        calMonth.appendChild(opt);
    }
    // 년 드롭다운
    for (let y = currentYear - 3; y <= currentYear + 1; y++) {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y;
        calYear.appendChild(opt);
    }

    calMonth.value = currentMonth;
    calYear.value = currentYear;

    calMonth.addEventListener('change', () => { currentMonth = +calMonth.value; renderCalendar(); });
    calYear.addEventListener('change', () => { currentYear = +calYear.value; renderCalendar(); });
    document.getElementById('cal-prev').addEventListener('click', () => {
        currentMonth--;
        if (currentMonth < 0) { currentMonth = 11; currentYear--; }
        calMonth.value = currentMonth;
        calYear.value = currentYear;
        renderCalendar();
    });
    document.getElementById('cal-next').addEventListener('click', () => {
        currentMonth++;
        if (currentMonth > 11) { currentMonth = 0; currentYear++; }
        calMonth.value = currentMonth;
        calYear.value = currentYear;
        renderCalendar();
    });

    renderCalendar();
}

function renderCalendar() {
    calGrid.innerHTML = '';
    const firstDay = new Date(currentYear, currentMonth, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const prevDays = new Date(currentYear, currentMonth, 0).getDate();

    const today = new Date();
    const todayStr = fmt(today.getFullYear(), today.getMonth(), today.getDate());

    let cells = [];

    // 이전 달
    for (let i = firstDay - 1; i >= 0; i--) {
        cells.push({ day: prevDays - i, other: true, month: currentMonth - 1, year: currentYear });
    }
    // 현재 달
    for (let d = 1; d <= daysInMonth; d++) {
        cells.push({ day: d, other: false, month: currentMonth, year: currentYear });
    }
    // 다음 달
    const remaining = 42 - cells.length;
    for (let d = 1; d <= remaining; d++) {
        cells.push({ day: d, other: true, month: currentMonth + 1, year: currentYear });
    }

    for (let i = 0; i < cells.length; i += 7) {
        const tr = document.createElement('tr');
        for (let j = 0; j < 7; j++) {
            const cell = cells[i + j];
            const td = document.createElement('td');
            td.textContent = cell.day;

            if (cell.other) {
                td.classList.add('other-month');
            }

            const dateStr = fmt(cell.year, cell.month, cell.day);
            td.dataset.date = dateStr;

            if (dateStr === todayStr) td.classList.add('today');

            // 범위 표시
            if (rangeStart && rangeEnd) {
                if (dateStr === rangeStart) td.classList.add('range-start');
                else if (dateStr === rangeEnd) td.classList.add('range-end');
                else if (dateStr > rangeStart && dateStr < rangeEnd) td.classList.add('in-range');
            } else if (rangeStart && dateStr === rangeStart) {
                td.classList.add('selected');
            }

            td.addEventListener('click', () => onDateClick(dateStr));
            tr.appendChild(td);
        }
        calGrid.appendChild(tr);
    }
}

function fmt(y, m, d) {
    // 월 보정
    if (m < 0) { m = 11; y--; }
    if (m > 11) { m = 0; y++; }
    return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function onDateClick(dateStr) {
    if (!rangeStart || rangeEnd) {
        // 첫 클릭 또는 리셋
        rangeStart = dateStr;
        rangeEnd = null;
    } else {
        // 두 번째 클릭
        if (dateStr < rangeStart) {
            rangeEnd = rangeStart;
            rangeStart = dateStr;
        } else {
            rangeEnd = dateStr;
        }
    }
    updateRangeDisplay();
    renderCalendar();
}

function updateRangeDisplay() {
    if (rangeStart && rangeEnd) {
        rangeDisplay.textContent = `${rangeStart} ~ ${rangeEnd}`;
    } else if (rangeStart) {
        rangeDisplay.textContent = `${rangeStart} (종료일 선택)`;
    } else {
        rangeDisplay.textContent = '날짜를 선택하세요';
    }
}

// ── 전체 체크 ────────────────────────────────────
document.getElementById('check-all').addEventListener('change', (e) => {
    document.querySelectorAll('.site-check').forEach(cb => { cb.checked = e.target.checked; });
});

// ── 수집 시작 ────────────────────────────────────
document.getElementById('btn-collect').addEventListener('click', async () => {
    if (!rangeStart || !rangeEnd) {
        alert('수집 기간을 선택해주세요.\n달력에서 시작일과 종료일을 클릭하세요.');
        return;
    }

    const checked = [];
    document.querySelectorAll('#sites-body tr').forEach(tr => {
        const cb = tr.querySelector('.site-check');
        if (cb && cb.checked) {
            checked.push({ slug: tr.dataset.slug, name: tr.dataset.name });
        }
    });

    if (checked.length === 0) {
        appendLog('수집할 도매사이트를 선택해주세요');
        return;
    }

    // 테이블 초기화
    document.querySelectorAll('#sites-body tr').forEach(tr => {
        tr.querySelector('.col-amount').textContent = '';
        tr.querySelector('.col-status').textContent = '';
    });

    const btn = document.getElementById('btn-collect');
    btn.disabled = true;
    btn.textContent = '수집 중...';

    // 로그 박스 초기화 + 폴링 인덱스 리셋
    document.getElementById('log-box').innerHTML = '';
    logSince = 0;

    try {
        const resp = await fetch('/api/collect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sites: checked, start_date: rangeStart, end_date: rangeEnd }),
        });
        const data = await resp.json();
        if (data.error) {
            appendLog('오류: ' + data.error);
            btn.disabled = false;
            btn.textContent = '수집시작';
        } else {
            appendLog('수집 요청 전송됨');
            startPolling();
        }
    } catch (e) {
        appendLog('요청 실패: ' + e.message);
        btn.disabled = false;
        btn.textContent = '수집시작';
    }
});

// ── 진행상황 + 로그 폴링 ─────────────────────────
let pollTimer = null;
let logSince = 0;  // 서버에서 받은 로그 개수 (다음 요청의 since)

function startPolling() {
    pollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`/api/collect/status?since=${logSince}`);
            const data = await resp.json();

            // 새 로그 출력
            if (Array.isArray(data.logs)) {
                data.logs.forEach(appendLog);
            }
            if (typeof data.log_count === 'number') {
                logSince = data.log_count;
            }

            // 테이블 업데이트
            for (const [slug, info] of Object.entries(data.sites)) {
                const tr = document.querySelector(`#sites-body tr[data-slug="${slug}"]`);
                if (tr) {
                    tr.querySelector('.col-amount').textContent = info.amount || '';
                    tr.querySelector('.col-status').textContent = info.status || '';
                }
            }

            if (!data.running) {
                clearInterval(pollTimer);
                pollTimer = null;
                const btn = document.getElementById('btn-collect');
                btn.disabled = false;
                btn.textContent = '수집시작';
            }
        } catch (e) { /* 무시 */ }
    }, 800);
}

// ── 로그 출력 ────────────────────────────────────
function appendLog(msg) {
    const box = document.getElementById('log-box');
    const line = document.createElement('div');
    const now = new Date().toLocaleTimeString('ko-KR');
    line.textContent = `[${now}] ${msg}`;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
}

// ── 설정 탭: 계정 관리 ──────────────────────────
async function loadAccounts() {
    const resp = await fetch('/api/accounts');
    const data = await resp.json();
    const tbody = document.getElementById('accounts-body');
    tbody.innerHTML = '';

    if (data.error) {
        appendLog('계정 로드 오류: ' + data.error);
        return;
    }

    data.accounts.forEach(acc => addAccountRow(acc.site, acc.user_id, acc.password));
}

function addAccountRow(site = '', userId = '', password = '') {
    const tbody = document.getElementById('accounts-body');
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="acc-site" value="${escapeHtml(site)}"></td>
        <td><input type="text" class="acc-id" value="${escapeHtml(userId)}"></td>
        <td><input type="password" class="acc-pw" value="${escapeHtml(password)}"></td>
        <td><button class="btn-del" onclick="this.closest('tr').remove()">삭제</button></td>
    `;
    tbody.appendChild(tr);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

document.getElementById('btn-add-account').addEventListener('click', () => addAccountRow());

document.getElementById('btn-save-accounts').addEventListener('click', async () => {
    const rows = document.querySelectorAll('#accounts-body tr');
    const accounts = [];
    rows.forEach(tr => {
        accounts.push({
            site: tr.querySelector('.acc-site').value,
            user_id: tr.querySelector('.acc-id').value,
            password: tr.querySelector('.acc-pw').value,
        });
    });

    try {
        const resp = await fetch('/api/accounts', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ accounts }),
        });
        const data = await resp.json();
        if (data.ok) {
            appendLog('계정 정보가 저장되었습니다');
        } else {
            appendLog('저장 오류: ' + (data.error || '알 수 없는 오류'));
        }
    } catch (e) {
        appendLog('저장 실패: ' + e.message);
    }
});

// ── 초기화 ───────────────────────────────────────
initCalendar();

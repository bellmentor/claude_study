// ── 탭 전환 ──────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');

        if (btn.dataset.tab === 'settings') loadAccounts();
        if (btn.dataset.tab === 'settlement') loadSettlement();
        if (btn.dataset.tab === 'aejulnun') loadAejulnun();
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

    // 테이블 초기화 (메모 컬럼(.site-note)은 유지, 매입금/진행상황/에러만 비운다)
    document.querySelectorAll('#sites-body tr').forEach(tr => {
        tr.querySelector('.col-amount').textContent = '';
        const st = tr.querySelector('.col-status .status-text');
        if (st) st.textContent = '';
        const er = tr.querySelector('.col-error .error-text');
        if (er) er.textContent = '';
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
                    const st = tr.querySelector('.col-status .status-text');
                    if (st) st.textContent = info.status || '';
                    const er = tr.querySelector('.col-error .error-text');
                    if (er) er.textContent = info.error || '';
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

// ── 정산엑셀관리 탭 ──────────────────────────────
const ALLOWED_EXCEL_EXT = ['.xlsx', '.xls'];

function hasExcelExt(name) {
    const lower = (name || '').toLowerCase();
    return ALLOWED_EXCEL_EXT.some(ext => lower.endsWith(ext));
}

async function loadSettlement() {
    const box = document.getElementById('settlement-cards');
    try {
        const resp = await fetch('/api/settlement');
        const data = await resp.json();
        renderSettlement(data.slots || []);
    } catch (e) {
        box.innerHTML = '<div class="settlement-error">목록을 불러오지 못했습니다: ' + escapeHtml(e.message) + '</div>';
    }
}

function renderSettlement(slots) {
    const box = document.getElementById('settlement-cards');
    box.innerHTML = '';
    slots.forEach(slot => {
        const card = document.createElement('div');
        card.className = 'settlement-card';

        if (slot.uploaded) card.classList.add('is-uploaded');

        const badge = slot.uploaded
            ? `<span class="settlement-badge on">● 업로드됨</span>`
            : `<span class="settlement-badge off">○ 미업로드</span>`;

        const fileRow = slot.uploaded
            ? `<div class="settlement-file-row">
                   <span class="file-info"><span class="file-ic">📄</span>${escapeHtml(slot.filename)}<span class="file-time">${escapeHtml(slot.uploaded_at)}</span></span>
                   <button class="btn-settle-del" data-key="${slot.key}">삭제</button>
               </div>`
            : '';

        card.innerHTML = `
            <div class="settlement-card-head">
                <span class="settlement-title">${escapeHtml(slot.name)}</span>
                ${badge}
            </div>
            <div class="dropzone" data-key="${slot.key}">
                <div class="dropzone-ic">⬆️</div>
                <div class="dropzone-text">여기로 엑셀 파일을 드래그하거나</div>
                <button class="btn-secondary btn-browse" type="button">파일 찾기</button>
                <input type="file" class="settlement-file" accept=".xlsx,.xls" style="display:none">
            </div>
            ${fileRow}
        `;
        box.appendChild(card);
    });

    // 이벤트 바인딩
    box.querySelectorAll('.dropzone').forEach(zone => {
        const key = zone.dataset.key;
        const fileInput = zone.querySelector('.settlement-file');
        const browseBtn = zone.querySelector('.btn-browse');

        browseBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) uploadSettlement(key, fileInput.files[0]);
        });

        const dzText = zone.querySelector('.dropzone-text');
        const baseText = dzText ? dzText.textContent : '';
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
            if (dzText) dzText.textContent = '여기에 놓으세요';
        });
        zone.addEventListener('dragleave', () => {
            zone.classList.remove('dragover');
            if (dzText) dzText.textContent = baseText;
        });
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (dzText) dzText.textContent = baseText;
            if (e.dataTransfer.files.length) uploadSettlement(key, e.dataTransfer.files[0]);
        });
    });

    box.querySelectorAll('.btn-settle-del').forEach(btn => {
        btn.addEventListener('click', () => deleteSettlement(btn.dataset.key));
    });
}

async function uploadSettlement(key, file) {
    if (!hasExcelExt(file.name)) {
        alert('엑셀 파일(.xlsx, .xls)만 업로드할 수 있습니다.');
        return;
    }
    try {
        // 파일명은 헤더로 전달(URL 에 넣으면 서버 접속로그에 %인코딩으로 찍혀 한글이 안 읽힘)
        const resp = await fetch('/api/settlement/upload/' + key, {
            method: 'POST',
            headers: { 'X-Filename': encodeURIComponent(file.name) },
            body: file,
        });
        const data = await resp.json();
        if (data.error) {
            appendLog('정산엑셀 업로드 오류: ' + data.error);
            alert('업로드 실패: ' + data.error);
        } else {
            appendLog(`정산엑셀 업로드됨: ${file.name} → ${key}`);
            renderSettlement(data.slots || []);
        }
    } catch (e) {
        appendLog('정산엑셀 업로드 실패: ' + e.message);
    }
}

async function deleteSettlement(key) {
    if (!confirm('업로드된 정산엑셀을 삭제할까요?')) return;
    try {
        const resp = await fetch('/api/settlement/' + key, { method: 'DELETE' });
        const data = await resp.json();
        if (data.error) {
            appendLog('정산엑셀 삭제 오류: ' + data.error);
            alert('삭제 실패: ' + data.error);
        } else {
            appendLog('정산엑셀 삭제됨: ' + key);
            renderSettlement(data.slots || []);
        }
    } catch (e) {
        appendLog('정산엑셀 삭제 실패: ' + e.message);
    }
}

// ── 에이준줄눈 탭 (폴더 선택) ────────────────────
async function loadAejulnun() {
    try {
        const resp = await fetch('/api/aejulnun');
        renderAejulnun(await resp.json());
    } catch (e) {
        document.getElementById('aejulnun-result').innerHTML =
            '<div class="settlement-error">불러오기 실패: ' + escapeHtml(e.message) + '</div>';
    }
}

function renderAejulnun(data) {
    const box = document.getElementById('aejulnun-result');
    // 파일 목록이 바뀌면 이전 계산 결과는 무효 → 비운다
    document.getElementById('aejulnun-calc-result').innerHTML = '';

    if (!data || !data.count) {
        box.innerHTML = '<div class="aejulnun-empty">선택된 폴더가 없습니다.</div>';
        return;
    }
    const rows = (data.files || []).map((f, i) =>
        `<tr><td>${i + 1}</td><td>${escapeHtml(f.name)}</td><td class="fsize">${(f.size / 1024).toFixed(1)} KB</td></tr>`
    ).join('');
    box.innerHTML = `
        <div class="aejulnun-summary">
            <span class="aejulnun-badge">📁 ${escapeHtml(data.folder || '(폴더명 없음)')}</span>
            <span class="aejulnun-count">엑셀 ${data.count}개</span>
            <span class="aejulnun-time">${escapeHtml(data.uploaded_at || '')}</span>
            <button class="btn-del" id="aejulnun-clear">비우기</button>
            <button class="btn-primary btn-calc" id="aejulnun-calc">계산하기</button>
        </div>
        <div class="aejulnun-files-wrap">
            <table class="aejulnun-files">
                <thead><tr><th>#</th><th>파일명</th><th>크기</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
    document.getElementById('aejulnun-clear').addEventListener('click', clearAejulnun);
    document.getElementById('aejulnun-calc').addEventListener('click', doAejulnunCalc);
}

async function doAejulnunCalc() {
    const btn = document.getElementById('aejulnun-calc');
    const out = document.getElementById('aejulnun-calc-result');
    btn.disabled = true;
    btn.textContent = '계산 중...';
    out.innerHTML = '<div class="aejulnun-empty">계산 중...</div>';
    try {
        const resp = await fetch('/api/aejulnun/calc', { method: 'POST' });
        renderAejulnunCalc(await resp.json());
        appendLog('에이준줄눈 계산 실행');
    } catch (e) {
        out.innerHTML = '<div class="settlement-error">계산 실패: ' + escapeHtml(e.message) + '</div>';
    } finally {
        btn.disabled = false;
        btn.textContent = '계산하기';
    }
}

function won(v) {
    return (v == null) ? '—' : Number(v).toLocaleString('ko-KR') + '원';
}

function renderAejulnunCalc(data) {
    const out = document.getElementById('aejulnun-calc-result');
    const results = data.results || [];
    if (!results.length) {
        out.innerHTML = '<div class="aejulnun-empty">계산할 파일이 없습니다.</div>';
        return;
    }
    const banner = data.pending
        ? '<div class="aejulnun-pending">⚠️ 계산 규칙이 아직 없어 매입금은 “—” 로 표시됩니다. 규칙을 알려주시면 채워집니다.</div>'
        : '';
    const rows = results.map((r, i) =>
        `<tr><td>${i + 1}</td><td>${escapeHtml(r.name)}</td><td class="won">${won(r.amount)}</td></tr>`
    ).join('');
    const totalRow = `<tr class="total-row"><td></td><td>합계 (${results.length}건)</td><td class="won">${won(data.total)}</td></tr>`;
    out.innerHTML = `
        <h4 class="aejulnun-calc-title">계산 결과</h4>
        ${banner}
        <div class="aejulnun-files-wrap">
            <table class="aejulnun-calc-table">
                <thead><tr><th>#</th><th>파일이름</th><th>매입금</th></tr></thead>
                <tbody>${rows}${totalRow}</tbody>
            </table>
        </div>
    `;
}

// 폴더 드롭 시 디렉토리 엔트리를 재귀 순회해 모든 File 을 수집한다.
function collectFilesFromDrop(dataTransfer) {
    const items = Array.from(dataTransfer.items || []);
    const entries = items
        .map(it => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null))
        .filter(Boolean);

    if (!entries.length) {
        // 엔트리 API 미지원 시 평면 파일 목록으로 폴백
        return Promise.resolve(Array.from(dataTransfer.files || []));
    }

    const files = [];
    function readEntry(entry, prefix) {
        return new Promise((resolve) => {
            if (entry.isFile) {
                entry.file((file) => {
                    // webkitRelativePath 가 비므로 상대경로를 직접 부여
                    try { Object.defineProperty(file, 'webkitRelativePath', { value: prefix + entry.name }); }
                    catch (e) { file._relpath = prefix + entry.name; }
                    files.push(file);
                    resolve();
                }, () => resolve());
            } else if (entry.isDirectory) {
                const reader = entry.createReader();
                const readBatch = () => {
                    reader.readEntries((batch) => {
                        if (!batch.length) return resolve();
                        Promise.all(batch.map(e => readEntry(e, prefix + entry.name + '/'))).then(readBatch);
                    }, () => resolve());
                };
                readBatch();
            } else {
                resolve();
            }
        });
    }
    return Promise.all(entries.map(e => readEntry(e, ''))).then(() => files);
}

function relPathOf(file) {
    return file.webkitRelativePath || file._relpath || file.name;
}

async function uploadAejulnunFolder(files, folderName) {
    const excels = files.filter(f => hasExcelExt(relPathOf(f)));
    if (!excels.length) {
        alert('선택한 폴더에 엑셀(.xlsx/.xls) 파일이 없습니다.');
        return;
    }

    const box = document.getElementById('aejulnun-result');
    box.innerHTML = `<div class="aejulnun-empty">업로드 중... (0/${excels.length})</div>`;

    // 기존 작업폴더 비우고 새 폴더 시작
    await fetch('/api/aejulnun/clear', {
        method: 'POST',
        headers: { 'X-Folder': encodeURIComponent(folderName || '') },
    });

    let done = 0;
    for (const f of excels) {
        await fetch('/api/aejulnun/upload', {
            method: 'POST',
            headers: { 'X-Filename': encodeURIComponent(relPathOf(f)) },
            body: f,
        });
        done++;
        box.innerHTML = `<div class="aejulnun-empty">업로드 중... (${done}/${excels.length})</div>`;
    }

    appendLog(`에이준줄눈 폴더 '${folderName}' 업로드 완료: 엑셀 ${excels.length}개`);
    loadAejulnun();
}

async function clearAejulnun() {
    if (!confirm('선택한 폴더의 업로드 파일을 모두 비울까요?')) return;
    try {
        const resp = await fetch('/api/aejulnun', { method: 'DELETE' });
        renderAejulnun(await resp.json());
        appendLog('에이준줄눈 작업폴더 비움');
    } catch (e) {
        appendLog('에이준줄눈 비우기 실패: ' + e.message);
    }
}

function folderNameFromFiles(files) {
    for (const f of files) {
        const rp = relPathOf(f);
        if (rp.includes('/')) return rp.split('/')[0];
    }
    return '';
}

function initAejulnun() {
    const zone = document.getElementById('aejulnun-dropzone');
    const input = document.getElementById('aejulnun-input');
    const browseBtn = document.getElementById('aejulnun-browse');
    const dzText = document.getElementById('aejulnun-dz-text');
    if (!zone) return;
    const baseText = dzText.textContent;

    browseBtn.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
        const files = Array.from(input.files || []);
        if (files.length) uploadAejulnunFolder(files, folderNameFromFiles(files));
        input.value = '';
    });

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
        dzText.textContent = '여기에 폴더를 놓으세요';
    });
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
        dzText.textContent = baseText;
    });
    zone.addEventListener('drop', async (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        dzText.textContent = baseText;
        const files = await collectFilesFromDrop(e.dataTransfer);
        if (files.length) uploadAejulnunFolder(files, folderNameFromFiles(files));
    });
}

// ── 초기화 ───────────────────────────────────────
initCalendar();
initAejulnun();

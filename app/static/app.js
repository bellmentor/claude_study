// ── 탭 전환 ──────────────────────────────────────
function activateTab(tabName) {
    const btn = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    if (btn) btn.classList.add('active');
    document.getElementById('tab-' + tabName).classList.add('active');

    if (tabName === 'settings') loadAccounts();
    if (tabName === 'settlement') loadSettlement();
    if (tabName === 'margin') loadMargin();
    if (tabName === 'adhoc') loadAdhocFebstore();
    if (tabName === 'aejulnun') loadAejulnun();
    if (tabName === 'bearb2b') loadBearB2B();
}

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
});

// 정산마진확인: 그때그때 탭 안 버튼 → 새 창에서 열기 (1회성 작업이라 탭 전환 대신 새창)
document.getElementById('adhoc-open-margin').addEventListener('click', () => {
    window.open('/?tab=margin', '_blank');
});

// URL에 ?tab=xxx 가 있으면 해당 탭을 바로 활성화 (새창으로 여는 정산마진확인용)
const _initialTab = new URLSearchParams(location.search).get('tab');
if (_initialTab && document.getElementById('tab-' + _initialTab)) {
    activateTab(_initialTab);
}

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

// ── 정산마진확인 탭 ──────────────────────────────
async function loadMargin() {
    const box = document.getElementById('margin-upload-card');
    document.getElementById('margin-result').innerHTML = '';
    try {
        const resp = await fetch('/api/margin');
        const data = await resp.json();
        renderMarginCard(data);
    } catch (e) {
        box.innerHTML = '<div class="settlement-error">불러오기 실패: ' + escapeHtml(e.message) + '</div>';
    }
}

function renderMarginCard(data) {
    const box = document.getElementById('margin-upload-card');
    const calcBar = document.getElementById('margin-calc-bar');
    calcBar.style.display = data.uploaded ? 'block' : 'none';

    const card = document.createElement('div');
    card.className = 'settlement-card';
    if (data.uploaded) card.classList.add('is-uploaded');

    const badge = data.uploaded
        ? `<span class="settlement-badge on">● 업로드됨</span>`
        : `<span class="settlement-badge off">○ 미업로드</span>`;

    const fileRow = data.uploaded
        ? `<div class="settlement-file-row">
               <span class="file-info"><span class="file-ic">📄</span>${escapeHtml(data.filename)}<span class="file-time">${escapeHtml(data.uploaded_at)}</span></span>
               <button class="btn-settle-del" id="margin-del">삭제</button>
           </div>`
        : '';

    card.innerHTML = `
        <div class="settlement-card-head">
            <span class="settlement-title">정산 작업 엑셀 (대량 시트)</span>
            ${badge}
        </div>
        <div class="dropzone" id="margin-dropzone">
            <div class="dropzone-ic">⬆️</div>
            <div class="dropzone-text" id="margin-dz-text">여기로 엑셀 파일을 드래그하거나</div>
            <button class="btn-secondary btn-browse" type="button" id="margin-browse">파일 찾기</button>
            <input type="file" id="margin-file" accept=".xlsx,.xls" style="display:none">
        </div>
        ${fileRow}
    `;
    box.innerHTML = '';
    box.appendChild(card);

    const zone = document.getElementById('margin-dropzone');
    const fileInput = document.getElementById('margin-file');
    const browseBtn = document.getElementById('margin-browse');
    const dzText = document.getElementById('margin-dz-text');
    const baseText = dzText.textContent;

    browseBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) uploadMargin(fileInput.files[0]);
    });
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
        dzText.textContent = '여기에 놓으세요';
    });
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
        dzText.textContent = baseText;
    });
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        dzText.textContent = baseText;
        if (e.dataTransfer.files.length) uploadMargin(e.dataTransfer.files[0]);
    });

    const delBtn = document.getElementById('margin-del');
    if (delBtn) delBtn.addEventListener('click', deleteMargin);
}

async function uploadMargin(file) {
    if (!hasExcelExt(file.name)) {
        alert('엑셀 파일(.xlsx, .xls)만 업로드할 수 있습니다.');
        return;
    }
    try {
        const resp = await fetch('/api/margin/upload', {
            method: 'POST',
            headers: { 'X-Filename': encodeURIComponent(file.name) },
            body: file,
        });
        const data = await resp.json();
        if (data.error) {
            appendLog('정산마진확인 업로드 오류: ' + data.error);
            alert('업로드 실패: ' + data.error);
        } else {
            appendLog(`정산마진확인 업로드됨: ${file.name}`);
            document.getElementById('margin-result').innerHTML = '';
            renderMarginCard(data);
        }
    } catch (e) {
        appendLog('정산마진확인 업로드 실패: ' + e.message);
    }
}

async function deleteMargin() {
    if (!confirm('업로드된 정산 작업 엑셀을 삭제할까요?')) return;
    try {
        const resp = await fetch('/api/margin', { method: 'DELETE' });
        const data = await resp.json();
        if (data.error) {
            appendLog('정산마진확인 삭제 오류: ' + data.error);
            alert('삭제 실패: ' + data.error);
        } else {
            appendLog('정산마진확인 삭제됨');
            document.getElementById('margin-result').innerHTML = '';
            renderMarginCard(data);
        }
    } catch (e) {
        appendLog('정산마진확인 삭제 실패: ' + e.message);
    }
}

async function doMarginCalc() {
    const btn = document.getElementById('margin-calc-run');
    const out = document.getElementById('margin-result');
    btn.disabled = true;
    btn.textContent = '계산 중...';
    out.innerHTML = '<div class="aejulnun-empty">계산 중...</div>';
    try {
        const resp = await fetch('/api/margin/calc', { method: 'POST' });
        const data = await resp.json();
        if (data.error) {
            out.innerHTML = '<div class="settlement-error">' + escapeHtml(data.error) + '</div>';
        } else {
            renderMarginResult(data);
            appendLog(`정산마진확인 계산: ${data.matched_count}/${data.total_count}건 매칭, 마진합계 ${won(data.margin_sum)}`);
        }
    } catch (e) {
        out.innerHTML = '<div class="settlement-error">계산 실패: ' + escapeHtml(e.message) + '</div>';
    } finally {
        btn.disabled = false;
        btn.textContent = '매입금 매칭 계산하기';
    }
}

function renderMarginResult(data) {
    const out = document.getElementById('margin-result');
    const results = data.results || [];
    if (!results.length) {
        out.innerHTML = '<div class="aejulnun-empty">계산할 주문건이 없습니다.</div>';
        return;
    }

    const summary = `
        <div class="aejulnun-summary margin-summary">
            <span class="aejulnun-badge">전체 ${data.total_count}건</span>
            <span class="aejulnun-count">매칭 ${data.matched_count}건</span>
            <span class="margin-unmatched">매칭안됨 ${data.unmatched_count}건</span>
            <span class="margin-total-badge">마진합계 ${won(data.margin_sum)}</span>
            <span class="margin-total-badge">평균 마진율 ${data.avg_margin_rate != null ? data.avg_margin_rate + '%' : '—'}</span>
            <a class="btn-secondary margin-download-btn" href="/api/margin/download">⬇ 결과 엑셀 다운로드</a>
        </div>
    `;

    const rows = results.map(r => `
        <tr class="${r.matched ? '' : 'has-err'}">
            <td>${escapeHtml(r.date)}</td>
            <td>${escapeHtml(r.market)}</td>
            <td>${escapeHtml(r.site_name)}</td>
            <td>${escapeHtml(r.code)}</td>
            <td class="product-cell">${escapeHtml(r.product)}</td>
            <td>${r.qty}</td>
            <td>${escapeHtml(r.recipient)}</td>
            <td class="won">${won(r.revenue)}</td>
            <td class="won">${won(r.cost)}</td>
            <td class="won ${r.matched && r.margin < 0 ? 'margin-neg' : ''}">${won(r.margin)}</td>
            <td>${r.margin_rate != null ? r.margin_rate + '%' : '—'}</td>
            <td class="err">${escapeHtml(r.reason || '')}</td>
        </tr>
    `).join('');

    out.innerHTML = `
        ${summary}
        <div class="aejulnun-calc-wrap margin-table-wrap">
            <table class="aejulnun-calc-table margin-table">
                <thead>
                    <tr>
                        <th>주문일자</th><th>쇼핑몰</th><th>도매처</th><th>판매자상품코드</th>
                        <th>상품명</th><th>수량</th><th>수령자</th>
                        <th>정산예정금액(배송비포함)</th><th>매입금</th><th>마진</th><th>마진율</th><th>비고</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
}

function initMargin() {
    document.getElementById('margin-calc-run').addEventListener('click', doMarginCalc);
}

// ── 그때그때 탭: 페브스토어 판매가/매입가 비교 ────
async function loadAdhocFebstore() {
    const box = document.getElementById('adhoc-febstore-upload-card');
    try {
        const resp = await fetch('/api/adhoc/febstore');
        const data = await resp.json();
        renderAdhocFebstoreCard(data);
        if (data.uploaded) loadAdhocFebstoreTable();
    } catch (e) {
        box.innerHTML = '<div class="settlement-error">불러오기 실패: ' + escapeHtml(e.message) + '</div>';
    }
}

function renderAdhocFebstoreCard(data) {
    const box = document.getElementById('adhoc-febstore-upload-card');
    const controls = document.getElementById('adhoc-febstore-controls');
    controls.style.display = data.uploaded ? 'flex' : 'none';

    const card = document.createElement('div');
    card.className = 'settlement-card';
    if (data.uploaded) card.classList.add('is-uploaded');

    const badge = data.uploaded
        ? `<span class="settlement-badge on">● 업로드됨</span>`
        : `<span class="settlement-badge off">○ 미업로드</span>`;

    const fileRow = data.uploaded
        ? `<div class="settlement-file-row">
               <span class="file-info"><span class="file-ic">📄</span>${escapeHtml(data.filename)}<span class="file-time">${escapeHtml(data.uploaded_at)}</span></span>
               <button class="btn-settle-del" id="adhoc-febstore-del">삭제</button>
           </div>`
        : '';

    card.innerHTML = `
        <div class="settlement-card-head">
            <span class="settlement-title">페브스토어류 엑셀 (도매처별 시트)</span>
            ${badge}
        </div>
        <div class="dropzone" id="adhoc-febstore-dropzone">
            <div class="dropzone-ic">⬆️</div>
            <div class="dropzone-text" id="adhoc-febstore-dz-text">여기로 엑셀 파일을 드래그하거나</div>
            <button class="btn-secondary btn-browse" type="button" id="adhoc-febstore-browse">파일 찾기</button>
            <input type="file" id="adhoc-febstore-file" accept=".xlsx,.xls" style="display:none">
        </div>
        ${fileRow}
    `;
    box.innerHTML = '';
    box.appendChild(card);

    const zone = document.getElementById('adhoc-febstore-dropzone');
    const fileInput = document.getElementById('adhoc-febstore-file');
    const browseBtn = document.getElementById('adhoc-febstore-browse');
    const dzText = document.getElementById('adhoc-febstore-dz-text');
    const baseText = dzText.textContent;

    browseBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) uploadAdhocFebstore(fileInput.files[0]);
    });
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
        dzText.textContent = '여기에 놓으세요';
    });
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
        dzText.textContent = baseText;
    });
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        dzText.textContent = baseText;
        if (e.dataTransfer.files.length) uploadAdhocFebstore(e.dataTransfer.files[0]);
    });

    const delBtn = document.getElementById('adhoc-febstore-del');
    if (delBtn) delBtn.addEventListener('click', deleteAdhocFebstore);
}

async function uploadAdhocFebstore(file) {
    if (!hasExcelExt(file.name)) {
        alert('엑셀 파일(.xlsx, .xls)만 업로드할 수 있습니다.');
        return;
    }
    try {
        const resp = await fetch('/api/adhoc/febstore/upload', {
            method: 'POST',
            headers: { 'X-Filename': encodeURIComponent(file.name) },
            body: file,
        });
        const data = await resp.json();
        if (data.error) {
            appendLog('그때그때 업로드 오류: ' + data.error);
            alert('업로드 실패: ' + data.error);
        } else {
            appendLog(`그때그때 페브스토어 업로드됨: ${file.name}`);
            document.getElementById('adhoc-febstore-table').innerHTML = '';
            renderAdhocFebstoreCard(data);
            loadAdhocFebstoreTable();
        }
    } catch (e) {
        appendLog('그때그때 업로드 실패: ' + e.message);
    }
}

async function deleteAdhocFebstore() {
    if (!confirm('업로드된 페브스토어 엑셀과 조회 결과를 모두 삭제할까요?')) return;
    try {
        const resp = await fetch('/api/adhoc/febstore', { method: 'DELETE' });
        const data = await resp.json();
        if (data.error) {
            appendLog('그때그때 삭제 오류: ' + data.error);
            alert('삭제 실패: ' + data.error);
        } else {
            appendLog('그때그때 페브스토어 삭제됨');
            document.getElementById('adhoc-febstore-table').innerHTML = '';
            renderAdhocFebstoreCard(data);
        }
    } catch (e) {
        appendLog('그때그때 삭제 실패: ' + e.message);
    }
}

async function loadAdhocFebstoreTable() {
    const box = document.getElementById('adhoc-febstore-table');
    box.innerHTML = '<div class="aejulnun-empty">불러오는 중...</div>';
    try {
        const resp = await fetch('/api/adhoc/febstore/table');
        const data = await resp.json();
        if (data.error) {
            box.innerHTML = '<div class="settlement-error">' + escapeHtml(data.error) + '</div>';
        } else {
            renderAdhocFebstoreTable(data);
        }
    } catch (e) {
        box.innerHTML = '<div class="settlement-error">불러오기 실패: ' + escapeHtml(e.message) + '</div>';
    }
}

function renderAdhocFebstoreTable(data) {
    const box = document.getElementById('adhoc-febstore-table');
    const rows = data.rows || [];
    if (!rows.length) {
        box.innerHTML = '<div class="aejulnun-empty">상품이 없습니다.</div>';
        return;
    }

    const shipShow = (v) => (v === 0 ? '무료' : won(v));

    const body = rows.map(r => {
        const isOwner = r.slug === 'ownerclan';
        const costText = isOwner ? won(r.cost) : '미구현';
        let shipText;
        if (!isOwner) shipText = '미구현';
        else if (r.cost_ship != null) shipText = shipShow(r.cost_ship);
        else if (r.ship_note) shipText = escapeHtml(r.ship_note);
        else shipText = '—';
        return `<tr class="${isOwner && r.note ? 'has-err' : ''}">
            <td>${escapeHtml(r.code)}</td>
            <td>${escapeHtml(r.site_name)}</td>
            <td>${escapeHtml(r.status)}</td>
            <td class="won">${won(r.price)}</td>
            <td class="won">${shipShow(r.ship)}</td>
            <td class="won">${costText}</td>
            <td class="won">${shipText}</td>
            <td class="err">${escapeHtml(r.note || '')}</td>
        </tr>`;
    }).join('');

    box.innerHTML = `
        <div class="aejulnun-summary">
            <span class="aejulnun-badge">전체 ${rows.length}건</span>
            <a class="btn-secondary margin-download-btn" href="/api/adhoc/febstore/download">⬇ 결과 엑셀 다운로드</a>
        </div>
        <div class="aejulnun-calc-wrap margin-table-wrap">
            <table class="aejulnun-calc-table margin-table">
                <thead>
                    <tr>
                        <th>판매자관리코드</th><th>도매처</th><th>판매상태</th>
                        <th>판매가</th><th>배송비</th><th>매입가</th><th>매입배송비</th><th>비고</th>
                    </tr>
                </thead>
                <tbody>${body}</tbody>
            </table>
        </div>
    `;
}

let adhocFebstorePollTimer = null;

async function runAdhocFebstorePrice() {
    const btn = document.getElementById('adhoc-febstore-run');
    const statusEl = document.getElementById('adhoc-febstore-run-status');
    btn.disabled = true;
    btn.textContent = '조회 중...';
    try {
        const resp = await fetch('/api/adhoc/febstore/run', { method: 'POST' });
        const data = await resp.json();
        if (data.error) {
            appendLog('오너클랜 매입가 조회 오류: ' + data.error);
            alert(data.error);
            btn.disabled = false;
            btn.textContent = '오너클랜 매입가 조회';
            return;
        }
        appendLog(data.message || '오너클랜 매입가 조회 시작');
        startAdhocFebstorePolling();
    } catch (e) {
        appendLog('요청 실패: ' + e.message);
        btn.disabled = false;
        btn.textContent = '오너클랜 매입가 조회';
    }
}

function startAdhocFebstorePolling() {
    adhocFebstorePollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`/api/adhoc/febstore/status?since=${logSince}`);
            const data = await resp.json();

            if (Array.isArray(data.logs)) data.logs.forEach(appendLog);
            if (typeof data.log_count === 'number') logSince = data.log_count;

            const st = data.status || {};
            const statusEl = document.getElementById('adhoc-febstore-run-status');
            if (statusEl && st.total) {
                statusEl.textContent = `${st.done || 0}/${st.total} 조회 중...`;
            }

            if (!data.running) {
                clearInterval(adhocFebstorePollTimer);
                adhocFebstorePollTimer = null;
                const btn = document.getElementById('adhoc-febstore-run');
                btn.disabled = false;
                btn.textContent = '오너클랜 매입가 조회';
                if (statusEl) statusEl.textContent = st.status === '오류' ? ('오류: ' + (st.error || '')) : '';
                loadAdhocFebstoreTable();
            }
        } catch (e) { /* 무시 */ }
    }, 1000);
}

function initAdhocFebstore() {
    document.getElementById('adhoc-febstore-run').addEventListener('click', runAdhocFebstorePrice);
}

// ── BearB2B 탭 ───────────────────────────────────
let bearb2bPollTimer = null;

async function loadBearB2B() {
    try {
        const resp = await fetch('/api/bearb2b');
        const data = await resp.json();
        renderBearB2B(data);
        // 새로고침/재접속 시 이미 실행 중이면 폴링 재개
        if (data.running && !bearb2bPollTimer) startBearB2BPolling();
    } catch (e) {
        document.getElementById('bearb2b-result').textContent =
            '불러오기 실패: ' + e.message;
    }
}

function renderBearB2B(data) {
    const box = document.getElementById('bearb2b-result');
    const btn = document.getElementById('bearb2b-run');
    const st = data.status || {};

    btn.disabled = !!data.running;
    btn.textContent = data.running ? '수집 중...' : '매입금 수집';

    if (data.running) {
        box.textContent = '수집 중... 하단 로그를 확인하세요.';
    } else if (st.error) {
        box.textContent = '오류: ' + st.error;
    } else if (st.amount) {
        box.textContent = `매입금: ${st.amount}원 (${st.status || '완료'})`;
    } else {
        box.textContent = '';
    }
}

function startBearB2BPolling() {
    bearb2bPollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`/api/bearb2b/status?since=${logSince}`);
            const data = await resp.json();

            if (Array.isArray(data.logs)) data.logs.forEach(appendLog);
            if (typeof data.log_count === 'number') logSince = data.log_count;

            renderBearB2B(data);

            if (!data.running) {
                clearInterval(bearb2bPollTimer);
                bearb2bPollTimer = null;
            }
        } catch (e) { /* 무시 */ }
    }, 800);
}

async function runBearB2B() {
    const year = document.getElementById('bearb2b-year').value;
    const month = document.getElementById('bearb2b-month').value;
    const btn = document.getElementById('bearb2b-run');

    btn.disabled = true;
    btn.textContent = '수집 중...';
    try {
        const resp = await fetch('/api/bearb2b/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ year, month }),
        });
        const data = await resp.json();
        if (data.error) {
            appendLog('오류: ' + data.error);
            btn.disabled = false;
            btn.textContent = '매입금 수집';
            return;
        }
        appendLog(`베어B2B 수집 요청 전송됨 (${year}년 ${month}월)`);
        startBearB2BPolling();
    } catch (e) {
        appendLog('요청 실패: ' + e.message);
        btn.disabled = false;
        btn.textContent = '매입금 수집';
    }
}

function initBearB2B() {
    const ySel = document.getElementById('bearb2b-year');
    const mSel = document.getElementById('bearb2b-month');
    if (!ySel) return;

    const nowY = new Date().getFullYear();
    for (let y = nowY - 3; y <= nowY + 1; y++) {
        ySel.insertAdjacentHTML('beforeend', `<option value="${y}">${y}년</option>`);
    }
    for (let m = 1; m <= 12; m++) {
        mSel.insertAdjacentHTML('beforeend', `<option value="${m}">${m}월</option>`);
    }
    // 기본값: 지난달 (매입금 정산은 보통 전월 기준)
    const prev = new Date();
    prev.setMonth(prev.getMonth() - 1);
    ySel.value = prev.getFullYear();
    mSel.value = prev.getMonth() + 1;

    document.getElementById('bearb2b-run').addEventListener('click', runBearB2B);
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
    const controls = document.getElementById('aejulnun-controls');
    // 파일 목록이 바뀌면 이전 계산 결과는 무효 → 비운다
    document.getElementById('aejulnun-calc-result').innerHTML = '';

    if (!data || !data.count) {
        box.innerHTML = '<div class="aejulnun-empty">선택된 폴더가 없습니다.</div>';
        controls.style.display = 'none';
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
        </div>
        <div class="aejulnun-files-wrap">
            <table class="aejulnun-files">
                <thead><tr><th>#</th><th>파일명</th><th>크기</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
    document.getElementById('aejulnun-clear').addEventListener('click', clearAejulnun);

    // 계산 설정 바 노출 + 폴더명에서 계산 월 기본값 세팅
    controls.style.display = 'flex';
    const ym = parseFolderMonth(data.folder);
    if (ym) {
        document.getElementById('aejulnun-year').value = ym.year;
        document.getElementById('aejulnun-month').value = ym.month;
    }
}

// "26년 6월" / "2026년 06월" 같은 폴더명에서 {year, month} 추출
function parseFolderMonth(folder) {
    if (!folder) return null;
    const m = String(folder).match(/(\d{2,4})\s*년\s*(\d{1,2})\s*월/);
    if (!m) return null;
    let y = parseInt(m[1], 10);
    if (y < 100) y += 2000;
    return { year: y, month: parseInt(m[2], 10) };
}

async function loadAejulnunMasterSheets() {
    const sel = document.getElementById('aejulnun-sheet');
    try {
        const resp = await fetch('/api/aejulnun/master-sheets');
        const data = await resp.json();
        if (data.error) {
            sel.innerHTML = '<option value="">시트 선택</option>';
            sel.disabled = true;
            alert(data.error);
            return;
        }
        const opts = (data.sheets || []).map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
        sel.innerHTML = '<option value="">시트 선택</option>' + opts;
        sel.disabled = false;
        appendLog(`정산엑셀 시트 ${data.sheets.length}개 불러옴`);
    } catch (e) {
        appendLog('정산엑셀 시트 불러오기 실패: ' + e.message);
    }
}

async function doAejulnunCalc() {
    const btn = document.getElementById('aejulnun-calc');
    const out = document.getElementById('aejulnun-calc-result');
    const year = parseInt(document.getElementById('aejulnun-year').value, 10);
    const month = parseInt(document.getElementById('aejulnun-month').value, 10);
    const sheet = document.getElementById('aejulnun-sheet').value;

    btn.disabled = true;
    btn.textContent = '계산 중...';
    out.innerHTML = '<div class="aejulnun-empty">계산 중...</div>';
    try {
        const resp = await fetch('/api/aejulnun/calc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ year, month, sheet }),
        });
        const data = await resp.json();
        if (data.error) {
            out.innerHTML = '<div class="settlement-error">' + escapeHtml(data.error) + '</div>';
        } else {
            renderAejulnunCalc(data);
            appendLog(`에이준줄눈 계산: ${data.month} → ${(data.total || 0).toLocaleString('ko-KR')}원`);
        }
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
    const note = data.master_note
        ? `<div class="aejulnun-pending">⚠️ ${escapeHtml(data.master_note)}</div>`
        : '';
    const rows = results.map((r, i) => {
        const hasDetail = !!r.detail;
        const mark = hasDetail ? '<span class="detail-arrow">▸</span> ' : '';
        const mainRow = `<tr class="calc-row ${r.error ? 'has-err' : ''} ${hasDetail ? 'clickable' : ''}" ${hasDetail ? `data-idx="${i}"` : ''}>
            <td>${i + 1}</td>
            <td>${mark}${escapeHtml(r.name)}</td>
            <td class="won">${won(r.amount)}</td>
            <td class="err">${escapeHtml(r.error || '')}</td>
        </tr>`;
        const detailRow = hasDetail
            ? `<tr class="calc-detail-row" id="calc-detail-${i}" style="display:none"><td colspan="4">${renderAejulnunDetail(r.detail)}</td></tr>`
            : '';
        return mainRow + detailRow;
    }).join('');
    const totalRow = `<tr class="total-row"><td></td><td>합계 (${results.length}건)</td><td class="won">${won(data.total)}</td><td></td></tr>`;
    out.innerHTML = `
        <h4 class="aejulnun-calc-title">계산 결과 <span class="calc-month">${escapeHtml(data.month || '')}</span>
            <span class="calc-hint">첫·마지막 파일(▸)을 클릭하면 상세 계산이 열립니다</span></h4>
        ${note}
        <div class="aejulnun-calc-wrap">
            <table class="aejulnun-calc-table">
                <thead><tr><th>#</th><th>파일이름</th><th>매입금</th><th>에러</th></tr></thead>
                <tbody>${rows}${totalRow}</tbody>
            </table>
        </div>
    `;

    // 첫/마지막 행 클릭 → 상세 토글
    out.querySelectorAll('.calc-row.clickable').forEach(tr => {
        tr.addEventListener('click', () => {
            const idx = tr.dataset.idx;
            const dr = document.getElementById('calc-detail-' + idx);
            const open = dr.style.display === 'none';
            dr.style.display = open ? 'table-row' : 'none';
            const arrow = tr.querySelector('.detail-arrow');
            if (arrow) arrow.textContent = open ? '▾' : '▸';
        });
    });
}

function renderAejulnunDetail(d) {
    const title = d.edge === 'first' ? '첫 파일 보정' : '마지막 파일 보정';
    const removedLabel = d.edge === 'first' ? '제거됨 (전달분)' : '제거됨 (다음달분)';
    const listTable = (rows, cls) => {
        if (!rows.length) return '<div class="detail-empty">없음</div>';
        const body = rows.map(r =>
            `<tr><td>${escapeHtml(r.name)}</td><td class="won">${Number(r.amount).toLocaleString('ko-KR')}</td></tr>`
        ).join('');
        return `<table class="detail-list ${cls}"><tbody>${body}</tbody></table>`;
    };
    return `
        <div class="calc-detail">
            <div class="detail-rule">${title} — <b>${escapeHtml(d.window)}</b> 에 주문한 분만 남깁니다 (부가세 10%)</div>
            <div class="detail-fullnet">파일 전체 순액: <b>${Number(d.full_net).toLocaleString('ko-KR')}원</b></div>
            <div class="detail-cols">
                <div class="detail-col">
                    <div class="detail-col-head keep">남긴 주문 (${d.kept.length}건)</div>
                    ${listTable(d.kept, 'keep')}
                </div>
                <div class="detail-col">
                    <div class="detail-col-head drop">${removedLabel} (${d.removed.length}건)</div>
                    ${listTable(d.removed, 'drop')}
                </div>
            </div>
            <div class="detail-sum">
                순액 <b>${Number(d.net).toLocaleString('ko-KR')}</b>
                + 부가세 <b>${Number(d.vat).toLocaleString('ko-KR')}</b>
                = 매입금 <b class="won">${Number(d.net + d.vat).toLocaleString('ko-KR')}원</b>
            </div>
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

    // 계산 설정 바: 년/월 드롭다운 채우기 + 정적 버튼 바인딩(1회)
    const ySel = document.getElementById('aejulnun-year');
    const mSel = document.getElementById('aejulnun-month');
    const nowY = new Date().getFullYear();
    for (let y = nowY - 3; y <= nowY + 1; y++) {
        ySel.insertAdjacentHTML('beforeend', `<option value="${y}">${y}년</option>`);
    }
    for (let m = 1; m <= 12; m++) {
        mSel.insertAdjacentHTML('beforeend', `<option value="${m}">${m}월</option>`);
    }
    ySel.value = nowY;
    mSel.value = new Date().getMonth() + 1;

    document.getElementById('aejulnun-load-master').addEventListener('click', loadAejulnunMasterSheets);
    document.getElementById('aejulnun-calc').addEventListener('click', doAejulnunCalc);
}

// ── 리차스 탭 ─────────────────────────────────────
// 매입금 수집 탭 달력(33~174행)과 동일한 로직을 prefix 로 분리해 재사용하는 팩토리.
// 기존 collect 탭 달력 코드는 그대로 두고(회귀 위험 최소화), 리차스 탭은 이 팩토리로 별도 인스턴스를 만든다.
function createRangeCalendar(prefix) {
    const monthSel = document.getElementById(prefix + 'cal-month');
    const yearSel = document.getElementById(prefix + 'cal-year');
    const grid = document.querySelector('#' + prefix + 'calendar-grid tbody');
    const display = document.getElementById(prefix + 'range-display');

    let year, month;
    let start = null, end = null;

    function render() {
        grid.innerHTML = '';
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const prevDays = new Date(year, month, 0).getDate();

        const today = new Date();
        const todayStr = fmt(today.getFullYear(), today.getMonth(), today.getDate());

        let cells = [];
        for (let i = firstDay - 1; i >= 0; i--) {
            cells.push({ day: prevDays - i, other: true, month: month - 1, year });
        }
        for (let d = 1; d <= daysInMonth; d++) {
            cells.push({ day: d, other: false, month, year });
        }
        const remaining = 42 - cells.length;
        for (let d = 1; d <= remaining; d++) {
            cells.push({ day: d, other: true, month: month + 1, year });
        }

        for (let i = 0; i < cells.length; i += 7) {
            const tr = document.createElement('tr');
            for (let j = 0; j < 7; j++) {
                const cell = cells[i + j];
                const td = document.createElement('td');
                td.textContent = cell.day;
                if (cell.other) td.classList.add('other-month');

                const dateStr = fmt(cell.year, cell.month, cell.day);
                td.dataset.date = dateStr;
                if (dateStr === todayStr) td.classList.add('today');

                if (start && end) {
                    if (dateStr === start) td.classList.add('range-start');
                    else if (dateStr === end) td.classList.add('range-end');
                    else if (dateStr > start && dateStr < end) td.classList.add('in-range');
                } else if (start && dateStr === start) {
                    td.classList.add('selected');
                }

                td.addEventListener('click', () => onDateClick(dateStr));
                tr.appendChild(td);
            }
            grid.appendChild(tr);
        }
    }

    function onDateClick(dateStr) {
        if (!start || end) {
            start = dateStr;
            end = null;
        } else if (dateStr < start) {
            end = start;
            start = dateStr;
        } else {
            end = dateStr;
        }
        updateDisplay();
        render();
    }

    function updateDisplay() {
        if (start && end) display.textContent = `${start} ~ ${end}`;
        else if (start) display.textContent = `${start} (종료일 선택)`;
        else display.textContent = '날짜를 선택하세요';
    }

    const now = new Date();
    year = now.getFullYear();
    month = now.getMonth();

    for (let m = 0; m < 12; m++) {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = (m + 1) + '월';
        monthSel.appendChild(opt);
    }
    for (let y = year - 3; y <= year + 1; y++) {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y;
        yearSel.appendChild(opt);
    }
    monthSel.value = month;
    yearSel.value = year;

    monthSel.addEventListener('change', () => { month = +monthSel.value; render(); });
    yearSel.addEventListener('change', () => { year = +yearSel.value; render(); });
    document.getElementById(prefix + 'cal-prev').addEventListener('click', () => {
        month--;
        if (month < 0) { month = 11; year--; }
        monthSel.value = month;
        yearSel.value = year;
        render();
    });
    document.getElementById(prefix + 'cal-next').addEventListener('click', () => {
        month++;
        if (month > 11) { month = 0; year++; }
        monthSel.value = month;
        yearSel.value = year;
        render();
    });

    render();

    return { getRange: () => ({ start, end }) };
}

let lechasCalendar = null;

function initLechasCalendar() {
    if (!document.getElementById('lechas-cal-month')) return;
    lechasCalendar = createRangeCalendar('lechas-');

    document.getElementById('lechas-check-all').addEventListener('change', (e) => {
        document.querySelectorAll('.lechas-check').forEach(cb => { cb.checked = e.target.checked; });
    });

    document.getElementById('lechas-collect-run').addEventListener('click', () => {
        const { start, end } = lechasCalendar.getRange();
        if (!start || !end) {
            alert('수집 기간을 선택해주세요.\n달력에서 시작일과 종료일을 클릭하세요.');
            return;
        }

        const checked = [];
        document.querySelectorAll('#lechas-sites-body tr').forEach(tr => {
            const cb = tr.querySelector('.lechas-check');
            if (cb && cb.checked) checked.push(tr.dataset.name);
        });
        if (checked.length === 0) {
            appendLog('[리차스] 수집할 거래처를 선택해주세요');
            return;
        }

        appendLog('[리차스] 아직 구현되지 않은 기능입니다');
    });

    document.querySelectorAll('.lechas-download-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tr = btn.closest('tr');
            const name = tr ? tr.dataset.name : '';
            appendLog(`[리차스] ${name} 다운로드: 아직 구현되지 않은 기능입니다`);
        });
    });
}

// ── 초기화 ───────────────────────────────────────
initCalendar();
initMargin();
initAdhocFebstore();
initAejulnun();
initBearB2B();
initLechasCalendar();

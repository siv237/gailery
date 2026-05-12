// Pipeline module
(function(A) {
var st = null, taskState = {};
var _statusTimer = null, _durationTimer = null;

var STEPS = [
    {id:'ingest', name:'Наполнение', icon:'📂', cls:'c-text'},
    {id:'describe', name:'Описание', icon:'🖼️', cls:'c-info'},
    {id:'faces', name:'Лица', icon:'👤', cls:'c-warn'},
    {id:'exif', name:'EXIF', icon:'📷', cls:'c-exif'},
    {id:'embed', name:'Семантическая индексация', icon:'🔍', cls:'c-embed'},
];

var TASKS = [
    {id:'ingest', name:'Наполнение базы', icon:'📂', desc:'Сканирование фото, добавление записей в базу',
     params:[{k:'ingest_limit',l:'Количество фото',v:100,t:'n'},{k:'exif',l:'Читать EXIF',v:'1',t:'s',opts:[['1','Да'],['0','Нет']]}]},
    {id:'describe', name:'Описание фото', icon:'🖼️', desc:'VLM (Qwen3.5-4B) генерирует описание и флаг лиц',
     params:[{k:'desc_limit',l:'Лимит описаний (0=все)',v:60,t:'n'},{k:'batch_size',l:'Размер батча ВЛМ',v:6,t:'n'}]},
    {id:'faces', name:'Поиск лиц', icon:'👤', desc:'InsightFace: детекция, векторные представления, кластеризация в персоны', params:[]},
    {id:'exif', name:'Чтение EXIF', icon:'📷', desc:'Дата, GPS, камера из метаданных фото', params:[]},
    {id:'embed', name:'Семантическая индексация', icon:'🔍', desc:'Qwen3-Embedding: векторный индекс для смыслового поиска', params:[]},
];

TASKS.forEach(function(t) { taskState[t.id] = {status:'idle', started:null, stopped:null, startPct:0, baseCount:0}; });

A.registerBlock('pipeline_status', 'Статус пайплайна', '📊', function(cid) { A.renderBlock_pipelineStatus(cid); }, function(cid, d) { A.refreshBlock_pipelineStatus(cid, d); });
A.registerBlock('pipeline_tasks', 'Задачи пайплайна', '📋', function(cid) { A.renderBlock_pipelineTasks(cid); }, function(cid, d) { A.refreshBlock_pipelineTasks(cid, d); });

A.renderBlock_pipelineStatus = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div id="psSummary_'+containerId+'"></div><div id="psCyclo_'+containerId+'"></div><div id="psCtrl_'+containerId+'"></div>';
    A.ajax('/api/status', function(d) {
        st = d; A.st = d;
        renderSummaryInto('psSummary_'+containerId);
        renderCycloInto('psCyclo_'+containerId);
        renderCtrlInto('psCtrl_'+containerId, containerId);
    });
};

A.refreshBlock_pipelineStatus = function(containerId, d) {
    if (!d) return;
    st = d; A.st = d;
    var sEl = document.getElementById('psSummary_'+containerId);
    var cEl = document.getElementById('psCyclo_'+containerId);
    if (sEl) sEl.innerHTML = buildSummaryHtml();
    if (cEl) cEl.innerHTML = buildCycloHtml();
    updateCtrlState(containerId);
};

A.renderBlock_pipelineTasks = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div id="psTasks_'+containerId+'"></div>';
    A.ajax('/api/status', function(d) {
        st = d; A.st = d;
        renderTasksInto('psTasks_'+containerId);
    });
};

A.refreshBlock_pipelineTasks = function(containerId, d) {
    if (!d) return;
    st = d; A.st = d;
    var tEl = document.getElementById('psTasks_'+containerId);
    if (tEl) renderTasksInto('psTasks_'+containerId);
};

// Persist param values and open tasks between re-renders
var _paramValues = {};
var _openTasks = [];

function saveParamValues() {
    var els = document.querySelectorAll('.task-body input, .task-body select');
    for (var i=0;i<els.length;i++) {
        if (els[i].id) _paramValues[els[i].id] = els[i].value;
    }
}
function restoreParamValues() {
    for (var id in _paramValues) {
        var el = document.getElementById(id);
        if (el) el.value = _paramValues[id];
    }
}
function restoreOpenTasks() {
    for (var i=0;i<_openTasks.length;i++) {
        var el = document.getElementById(_openTasks[i]);
        if (el) el.classList.add('open');
    }
    restoreParamValues();
}

function stepPct(id) {
    if (!st || (!st.photos_total && id!=='ingest')) return 0;
    if (id==='ingest') return st.pct_ingested||0;
    if (id==='describe') return st.pct_described||0;
    if (id==='faces') return st.pct_faces||0;
    if (id==='exif') return st.pct_exif||0;
    if (id==='embed') return st.pct_embedded||0;
    return 0;
}
function stepCount(id) {
    if (!st) return {done:0,total:0};
    var ct = st.catalog_total||0, ci = st.catalog_ingested||0, ff = st.faces_flagged_in_db||0;
    if (id==='ingest') return {done:ci,total:ct};
    if (id==='describe') return {done:st.catalog_described||0,total:ci||ct};
    if (id==='faces') return {done:st.catalog_faces_done||0,total:ff||ci||ct};
    if (id==='exif') return {done:st.catalog_exif_done||0,total:ci||ct};
    if (id==='embed') return {done:st.photos_embedded||0,total:st.photos_total||0};
    return {done:0,total:0};
}

function buildUI(mode) {
    var el;
    if (mode === 'tasks') {
        el = A.$('page-tasks');
        if (!el) return;
        el.innerHTML = '<h2 class="page-h2">📋 Индивидуальные задачи</h2><div class="tasks" id="taskList-tasks"><div style="color:var(--c-text-muted);padding:12px">⏳ Загрузка...</div></div>';
    } else {
        el = A.$('page-pipeline');
        if (!el) return;
        el.innerHTML =
            '<h2 class="page-h2">🔄 Пайплайн</h2>'+
            '<div class="summary" id="summary"><div style="color:var(--c-text-muted);padding:12px">⏳ Загрузка статуса...</div></div>'+
            '<div class="pipeline-banner idle" id="pipelineBanner">'+
            '<div class="pb-top"><div><div class="pb-title" id="pbTitle">Пайплайн остановлен</div><div class="pb-pipeline-time" id="pbPipelineTime"></div></div><div class="pb-status s-idle" id="pbStatus">IDLE</div></div>'+
            '<div class="cyclo" id="cyclo"></div>'+
            '<div class="pb-ctrl">'+
            '<label>Лимит:</label><input type="number" id="chainLimit" value="100" min="0">'+
            '<label style="margin-left:8px">Источник:</label><select id="chainRoot" class="ctrl-select"></select>'+
            '<button class="btn btn-go" id="btnStart">Запустить цепочку</button>'+
            '<button class="btn btn-stop" id="btnStop" disabled>Остановить всё</button>'+
            '<span class="c-dim" style="font-size:11px" id="chainInfo"></span></div></div>'+
            '<div class="tasks" id="taskList-pipeline"><div style="color:var(--c-text-muted);padding:12px">⏳ Загрузка задач...</div></div>';
        A.$('btnStart').addEventListener('click', runChain);
        A.$('btnStop').addEventListener('click', stopAll);
        A.$('chainRoot').addEventListener('change', loadStatus);
        loadRoots();
    }
}

function buildSummaryHtml() {
    if (!st || !st.photos_total) return '';
    var ct = st.catalog_total || 0, ci = st.catalog_ingested || 0;
    var h = '<div class="summary">';
    h += '<div class="sbox"><div class="sv">'+ci+'</div><div class="sl">Внесено из '+ct+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.catalog_described||0)+'</div><div class="sl">Описано из '+ci+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.catalog_faces_done||0)+'</div><div class="sl">Лица из '+(st.faces_flagged_in_db||0)+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.catalog_exif_done||0)+'</div><div class="sl">EXIF из '+ci+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.photos_embedded||0)+'</div><div class="sl">Индекс из '+(st.photos_total||0)+'</div></div>';
    if (st.videos && st.videos.catalog) {
        h += '<div class="sbox"><div class="sv">'+st.videos.ingested+'</div><div class="sl">Видео из '+st.videos.catalog+'</div></div>';
    } else {
        h += '<div class="sbox"><div class="sv">0</div><div class="sl">Видео</div></div>';
    }
    h += '</div>';
    if (st.per_root && st.per_root.length > 1) {
        h += '<div class="src-section"><div class="src-title">По источникам:</div>';
        for (var i=0;i<st.per_root.length;i++) {
            var r = st.per_root[i];
            h += '<div class="src-row"><span class="src-alias">'+A.esc(r.alias)+'</span><span class="src-counts">'+r.ingested+' / '+r.catalog_total+'</span><span class="src-details">D:'+r.described+' E:'+r.exif_done+' I:'+r.embedded+'</span></div>';
        }
        h += '</div>';
    }
    return h;
}

function buildCycloHtml() {
    if (!st) return '<div class="c-dim" style="padding:12px">Нет данных</div>';
    var cur = (st.step_details||'').toLowerCase();
    var run = st.current_step !== 'idle';
    var h = '<div class="pipeline-banner '+(run?'running':'idle')+'">';
    h += '<div class="pb-top"><div><div class="pb-title '+(run?'c-ok':'c-text')+'">'+(run?'⚡ Пайплайн работает: '+A.esc(st.step_details):'Пайплайн остановлен')+'</div>';
    if (run && st.pipeline_started_at) {
        var ps = new Date(st.pipeline_started_at + (st.pipeline_started_at.indexOf('+')<0&&st.pipeline_started_at.indexOf('Z')<0?'+00:00':''));
        h += '<div class="pb-pipeline-time '+(run?'c-ok':'c-muted')+'">Цепочка идёт: '+A.fmtDur(Date.now()-ps.getTime())+'</div>';
    } else if (!run && st.pipeline_started_at) {
        var ps2 = new Date(st.pipeline_started_at + (st.pipeline_started_at.indexOf('+')<0&&st.pipeline_started_at.indexOf('Z')<0?'+00:00':''));
        h += '<div class="pb-pipeline-time">Последний запуск: '+ps2.toLocaleTimeString()+'</div>';
    }
    h += '</div><div class="pb-status '+(run?'s-run':'s-idle')+'">'+(run?'● '+A.esc(st.step_details):'IDLE')+'</div></div>';
    h += '<div class="cyclo">';
    for (var i=0;i<STEPS.length;i++) {
        var s = STEPS[i], pct = stepPct(s.id), cnt = stepCount(s.id);
        var isActive = (s.id===cur&&run), ts = taskState[s.id], isDone = pct>=100, isFailed = ts&&ts.status==='fail';
        var cls = 'st-wait', badgeHtml = '○ ожидание';
        if (isFailed) { cls = 'st-fail'; badgeHtml = '✗ ошибка'; }
        else if (isActive) { cls = 'st-run'; badgeHtml = '● работает'; }
        else if (isDone) { cls = 'st-done'; badgeHtml = '✓ готово'; }
        var pctStr = A.fmtPct(pct), barW = Math.min(pct,100);
        h += '<div class="cy-step '+cls+'">';
        h += '<div class="cy-icon">'+s.icon+'</div>';
        h += '<div class="cy-name">'+s.name+'</div>';
        h += '<div class="cy-pct">'+pctStr+'</div>';
        h += '<div class="cy-count">'+cnt.done+'/'+cnt.total+'</div>';
        h += '<div class="cy-bar-bg"><div class="cy-bar" style="width:'+barW+'%"></div></div>';
        h += '<div class="cy-badge">'+badgeHtml+'</div>';
        if (isDone&&!isActive) h += '<div class="cy-check">✓</div>';
        h += '</div>';
        if (i<STEPS.length-1) {
            var arrowLit = run && STEPS.slice(0,i+1).some(function(ss){return ss.id===cur;});
            h += '<div class="cy-arrow'+(arrowLit?' lit':'')+'">→</div>';
        }
    }
    h += '</div></div>';
    return h;
}

function renderSummaryInto(cid) {
    var el = document.getElementById(cid);
    if (el) el.innerHTML = buildSummaryHtml();
}
function renderCycloInto(cid) {
    var el = document.getElementById(cid);
    if (el) el.innerHTML = buildCycloHtml();
}

function renderCtrlInto(cid, blockCid) {
    var el = document.getElementById(cid);
    if (!el) return;
    var run = st && st.current_step !== 'idle';
    var pfx = 'ps_'+blockCid+'_';
    el.innerHTML =
        '<div class="pb-ctrl">'+
        '<label>Лимит:</label><input type="number" id="'+pfx+'chainLimit" value="100" min="0">'+
        '<label style="margin-left:8px">Источник:</label><select id="'+pfx+'chainRoot" class="ctrl-select"></select>'+
        '<button class="btn btn-go" id="'+pfx+'btnStart" '+(run?'disabled':'')+'>Запустить цепочку</button>'+
        '<button class="btn btn-stop" id="'+pfx+'btnStop" '+(run?'':'disabled')+'>Остановить всё</button>'+
        '<span class="c-dim" style="font-size:11px" id="'+pfx+'chainInfo"></span></div>';
    document.getElementById(pfx+'btnStart').addEventListener('click', function() { runChainBlock(blockCid); });
    document.getElementById(pfx+'btnStop').addEventListener('click', function() { stopAllBlock(blockCid); });
    loadRootsBlock(blockCid);
}

function updateCtrlState(blockCid) {
    if (!st) return;
    var run = st.current_step !== 'idle';
    var pfx = 'ps_'+blockCid+'_';
    var startBtn = document.getElementById(pfx+'btnStart');
    var stopBtn = document.getElementById(pfx+'btnStop');
    if (startBtn) startBtn.disabled = run;
    if (stopBtn) stopBtn.disabled = !run;
}

function runChainBlock(blockCid) {
    var pfx = 'ps_'+blockCid+'_';
    var limEl = document.getElementById(pfx+'chainLimit');
    var rootEl = document.getElementById(pfx+'chainRoot');
    var infoEl = document.getElementById(pfx+'chainInfo');
    var lim = limEl ? limEl.value : 100;
    var rootId = rootEl ? rootEl.value : '';
    var params = {step:'chain',ingest_limit:lim,desc_limit:lim,batch_size:10,exif:'1'};
    if (rootId) params.root_id = rootId;
    A.post('/api/control/start', params, function(d) {
        if (d.ok) {
            if (infoEl) infoEl.textContent = '⚡ Запущено '+new Date().toLocaleTimeString();
            TASKS.forEach(function(t) { taskState[t.id].baseCount = stepCount(t.id).done; });
        }
    });
}

function stopAllBlock(blockCid) {
    var pfx = 'ps_'+blockCid+'_';
    var infoEl = document.getElementById(pfx+'chainInfo');
    A.post('/api/control/stop', null, function() {
        TASKS.forEach(function(t) {
            if (taskState[t.id].status==='run') taskState[t.id] = {status:'idle',started:taskState[t.id].started,stopped:new Date(),baseCount:0};
        });
        if (infoEl) infoEl.textContent = 'Остановлено '+new Date().toLocaleTimeString();
    });
}

function loadRootsBlock(blockCid) {
    var pfx = 'ps_'+blockCid+'_';
    A.ajax('/api/catalog/roots', function(roots) {
        var sel = document.getElementById(pfx+'chainRoot');
        if (!sel) return;
        sel.innerHTML = '<option value="">Все включённые</option>';
        for (var i=0;i<roots.length;i++) {
            var r = roots[i];
            if (r.enabled) sel.innerHTML += '<option value="'+r.root_id+'">'+A.esc(r.alias)+'</option>';
        }
    });
}
function renderTasksInto(cid) {
    var el = document.getElementById(cid);
    if (!el || !st) return;
    var cur = (st.step_details||'').toLowerCase();
    var run = st.current_step !== 'idle';
    var h = '';
    for (var i=0;i<TASKS.length;i++) {
        var t = TASKS[i], ts = taskState[t.id];
        var isActive = (t.id===cur&&run);
        if (isActive && ts.status !== 'run') ts.status = 'run';
        else if (!isActive && ts.status==='run') ts.status = 'done';
        var badgeCls = 'tb-idle', badgeText = 'Остановлено';
        if (ts.status==='run') { badgeCls='tb-run'; badgeText='● Выполняется'; }
        else if (ts.status==='done') { badgeCls='tb-done'; badgeText='✓ Завершено'; }
        var cnt = stepCount(t.id);
        var descHtml = t.desc;
        if (cnt.total>0) descHtml += ' · <b class="c-info">'+cnt.done+'/'+cnt.total+' ('+A.fmtPct(stepPct(t.id))+')</b>';
        h += '<div class="task"><div class="task-head mini"><div class="task-icon">'+t.icon+'</div>';
        h += '<div class="task-info"><div class="tn">'+t.name+'</div><div class="td">'+descHtml+'</div></div>';
        h += '<div class="task-badge '+badgeCls+'">'+badgeText+'</div></div></div>';
    }
    el.innerHTML = h;
}

function renderSummary() {
    var sec = A.$('summary');
    if (!sec) return;
    if (!st || !st.photos_total) { sec.innerHTML = ''; return; }
    var ct = st.catalog_total || 0, ci = st.catalog_ingested || 0;
    var h = '';
    h += '<div class="sbox"><div class="sv">'+ci+'</div><div class="sl">Внесено из '+ct+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.catalog_described||0)+'</div><div class="sl">Описано из '+ci+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.catalog_faces_done||0)+'</div><div class="sl">Лица из '+(st.faces_flagged_in_db||0)+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.catalog_exif_done||0)+'</div><div class="sl">EXIF из '+ci+'</div></div>';
    h += '<div class="sbox"><div class="sv">'+(st.photos_embedded||0)+'</div><div class="sl">Индекс из '+(st.photos_total||0)+'</div></div>';
    if (st.videos && st.videos.catalog) {
        h += '<div class="sbox"><div class="sv">'+st.videos.ingested+'</div><div class="sl">Видео из '+st.videos.catalog+'</div></div>';
    } else {
        h += '<div class="sbox"><div class="sv">0</div><div class="sl">Видео</div></div>';
    }
    if (st.per_root && st.per_root.length > 1) {
        h += '<div class="src-section"><div class="src-title">По источникам:</div>';
        for (var i=0;i<st.per_root.length;i++) {
            var r = st.per_root[i];
            h += '<div class="src-row"><span class="src-alias">'+A.esc(r.alias)+'</span><span class="src-counts">'+r.ingested+' / '+r.catalog_total+'</span><span class="src-details">D:'+r.described+' E:'+r.exif_done+' I:'+r.embedded+'</span></div>';
        }
        h += '</div>';
    }
    sec.innerHTML = h;
}

function renderCyclo() {
    if (!st) return;
    var cur = (st.step_details||'').toLowerCase();
    var run = st.current_step !== 'idle';
    var banner = A.$('pipelineBanner');
    if (!banner) return;
    var title = A.$('pbTitle'), status = A.$('pbStatus'), btnStart = A.$('btnStart'), btnStop = A.$('btnStop');

    if (run) {
        banner.className = 'pipeline-banner running';
        title.textContent = '⚡ Пайплайн работает: '+A.esc(st.step_details);
        status.className = 'pb-status s-run';
        status.textContent = '● '+A.esc(st.step_details);
        if (btnStart) btnStart.disabled = true;
        if (btnStop) btnStop.disabled = false;
        var pte = A.$('pbPipelineTime');
        if (st.pipeline_started_at) {
            var ps = new Date(st.pipeline_started_at + (st.pipeline_started_at.indexOf('+')<0&&st.pipeline_started_at.indexOf('Z')<0?'+00:00':''));
            pte.innerHTML = 'Цепочка идёт: <span id="pbPipelineDur">'+A.fmtDur(Date.now()-ps.getTime())+'</span> (с '+ps.toLocaleTimeString()+')';
        } else {
            pte.textContent = 'Одиночный шаг: '+A.esc(st.step_details);
        }
    } else {
        banner.className = 'pipeline-banner idle';
        title.textContent = 'Пайплайн остановлен';
        status.className = 'pb-status s-idle';
        status.textContent = 'IDLE';
        if (btnStart) btnStart.disabled = false;
        if (btnStop) btnStop.disabled = true;
        var pte = A.$('pbPipelineTime');
        if (st.pipeline_started_at) {
            var ps = new Date(st.pipeline_started_at + (st.pipeline_started_at.indexOf('+')<0&&st.pipeline_started_at.indexOf('Z')<0?'+00:00':''));
            pte.textContent = 'Последний запуск: '+ps.toLocaleTimeString();
        } else {
            pte.textContent = '';
        }
    }

    var h = '';
    for (var i=0;i<STEPS.length;i++) {
        var s = STEPS[i], pct = stepPct(s.id), cnt = stepCount(s.id);
        var isActive = (s.id===cur&&run), ts = taskState[s.id], isDone = pct>=100, isFailed = ts&&ts.status==='fail';
        var cls = 'st-wait', badgeHtml = '○ ожидание';
        if (isFailed) { cls = 'st-fail'; badgeHtml = '✗ ошибка'; }
        else if (isActive) { cls = 'st-run'; badgeHtml = '● работает'; }
        else if (isDone) { cls = 'st-done'; badgeHtml = '✓ готово'; }
        var pctStr = A.fmtPct(pct), countStr = cnt.done+'/'+cnt.total, barW = Math.min(pct,100);

        h += '<div class="cy-step '+cls+'">';
        h += '<div class="cy-icon">'+s.icon+'</div>';
        h += '<div class="cy-name'+(isActive||isDone?' '+s.cls:'')+'">'+s.name+'</div>';
        h += '<div class="cy-pct">'+pctStr+'</div>';
        h += '<div class="cy-count">'+countStr+'</div>';
        h += '<div class="cy-bar-bg"><div class="cy-bar" style="width:'+barW+'%"></div></div>';
        h += '<div class="cy-badge">'+badgeHtml+'</div>';
        if (isActive && ts.started) {
            h += '<div class="cy-time" id="cyTime_'+s.id+'">'+A.fmtDur(Date.now()-ts.started.getTime())+'</div>';
        } else if (ts.status==='done'&&ts.started&&ts.stopped) {
            h += '<div class="cy-time">'+A.fmtDur(ts.stopped.getTime()-ts.started.getTime())+' · '+A.fmtDur(Date.now()-ts.stopped.getTime())+' назад</div>';
        }
        var cycleDelta = cnt.done - ts.baseCount;
        if (ts.baseCount>0&&cycleDelta>0) {
            h += '<div class="cy-count c-ok">+'+cycleDelta+' за цикл</div>';
        }
        if (isDone&&!isActive) h += '<div class="cy-check">✓</div>';
        if (s.id==='faces'&&isActive&&st.faces_phase) {
            var phaseNames = {loading:'Загрузка',detecting:'Детекция',lance_write:'LanceDB',clustering:'Кластеризация',detection_done:'Завершение',done:'Готово'};
            var phaseLabel = phaseNames[st.faces_phase]||st.faces_phase;
            var detailHtml = st.faces_detail ? A.esc(st.faces_detail) : '';
            h += '<div style="font-size:9px;margin-top:3px" class="c-warn">'+phaseLabel+(detailHtml?': '+detailHtml:'')+'</div>';
        }
        h += '</div>';
        if (i<STEPS.length-1) {
            var arrowLit = run && STEPS.slice(0,i+1).some(function(ss){return ss.id===cur;});
            h += '<div class="cy-arrow'+(arrowLit?' lit':'')+'">→</div>';
        }
    }
    A.$('cyclo').innerHTML = h;
}

function renderTasks() {
    var sec = A.$(A.page==='tasks' ? 'taskList-tasks' : 'taskList-pipeline');
    if (!sec || !st) return;
    var cur = (st.step_details||'').toLowerCase();
    var run = st.current_step !== 'idle';
    saveParamValues();
    var h = '';

    for (var i=0;i<TASKS.length;i++) {
        var t = TASKS[i], ts = taskState[t.id];
        var isActive = (t.id===cur&&run);

        if (isActive && ts.status !== 'run') {
            ts.status = 'run';
            if (!ts.started) {
                if (st.step_started_at) ts.started = new Date(st.step_started_at+(st.step_started_at.indexOf('+')<0&&st.step_started_at.indexOf('Z')<0?'+00:00':''));
                else ts.started = new Date();
            }
            if (!ts.startPct&&ts.startPct!==0) ts.startPct = stepPct(t.id);
            if (!ts.baseCount) ts.baseCount = stepCount(t.id).done;
        } else if (!isActive && ts.status==='run') {
            ts.status = stepPct(t.id)>=100?'done':'done';
            ts.stopped = new Date();
        }

        var badgeCls = 'tb-idle', badgeText = 'Остановлено';
        if (ts.status==='run') { badgeCls = 'tb-run'; badgeText = '● Выполняется'; }
        else if (ts.status==='done') { badgeCls = 'tb-done'; badgeText = '✓ Завершено'; }
        else if (ts.status==='fail') { badgeCls = 'tb-fail'; badgeText = '✗ Ошибка'; }

        var dur = '';
        var eta = '';
        var progressLine = (st.progress_lines||{})[t.id]||'';
        if (ts.status==='run'&&ts.started) dur = A.fmtDur(Date.now()-ts.started.getTime());
        else if (ts.stopped&&ts.started) dur = A.fmtDur(ts.stopped.getTime()-ts.started.getTime());
        if (progressLine) {
            var m = progressLine.match(/осталось ~([^\]]+)/);
            if (m) eta = '~'+m[1];
        }

        var tl = '';
        if (ts.started) tl += '<div class="ev">Запущено: <b>'+A.fmtTime(ts.started.toISOString())+'</b></div>';
        if (ts.stopped) tl += '<div class="ev">Остановлено: <b>'+A.fmtTime(ts.stopped.toISOString())+'</b></div>';
        if (dur) tl += '<div class="ev">Длительность: <b>'+dur+'</b></div>';

        var descHtml = t.desc;
        var cnt = stepCount(t.id);
        if (cnt.total>0) descHtml += ' · <b class="c-info">'+cnt.done+'/'+cnt.total+' ('+A.fmtPct(stepPct(t.id))+')</b>';

        h += '<div class="task">';
        h += '<div class="task-head" data-task="'+t.id+'" data-action="toggle">';
        h += '<div class="task-icon">'+t.icon+'</div>';
        h += '<div class="task-info"><div class="tn">'+t.name+'</div><div class="td">'+descHtml+(dur?' · <b>'+dur+'</b>':'')+(eta?' → '+eta:'')+'</div></div>';
        h += '<div class="task-badge '+badgeCls+'">'+badgeText+'</div>';
        h += '<div class="task-btns" data-stop-propagation>';
        h += '<button class="btn btn-go" data-task="'+t.id+'" data-action="run" '+(run?'disabled':'')+'>Запустить</button>';
        h += '<button class="btn btn-stop" data-task="'+t.id+'" data-action="stop" '+(isActive?'':'disabled')+'>Стоп</button>';
        h += '<button class="btn btn-warn" data-task="'+t.id+'" data-action="reset">Сброс</button>';
        h += '</div></div>';
        h += '<div class="task-body" id="tb_'+t.id+'">';
        if (t.params.length>0) {
            for (var j=0;j<t.params.length;j++) {
                var pp = t.params[j];
                h += '<label>'+pp.l+'</label>';
                if (pp.t==='s') {
                    h += '<select id="p_'+pp.k+'">';
                    for (var o=0;o<pp.opts.length;o++) h += '<option value="'+pp.opts[o][0]+'">'+pp.opts[o][1]+'</option>';
                    h += '</select>';
                } else {
                    h += '<input type="number" id="p_'+pp.k+'" value="'+pp.v+'" min="0">';
                }
            }
        }
        h += '<div class="task-timeline">'+tl+'</div></div></div>';
    }
    sec.innerHTML = h;
    sec.querySelectorAll('.task-head[data-task][data-action="toggle"]').forEach(function(el) {
        el.addEventListener('click', function() { A._toggleTask(this.getAttribute('data-task')); });
    });
    sec.querySelectorAll('.task-btns button[data-task][data-action="run"]').forEach(function(btn) {
        btn.addEventListener('click', function(e) { e.stopPropagation(); A._runTask(this.getAttribute('data-task')); });
    });
    sec.querySelectorAll('.task-btns button[data-task][data-action="stop"]').forEach(function(btn) {
        btn.addEventListener('click', function(e) { e.stopPropagation(); A._stopTask(this.getAttribute('data-task')); });
    });
    sec.querySelectorAll('.task-btns button[data-task][data-action="reset"]').forEach(function(btn) {
        btn.addEventListener('click', function(e) { e.stopPropagation(); A._resetTask(this.getAttribute('data-task')); });
    });
    sec.querySelectorAll('.task-btns[data-stop-propagation]').forEach(function(el) {
        el.addEventListener('click', function(e) { e.stopPropagation(); });
    });
    restoreOpenTasks();
}

A._toggleTask = function(id) {
    var el = A.$('tb_'+id);
    if (el) el.classList.toggle('open');
    _openTasks = [];
    var bodies = document.querySelectorAll('.task-body.open');
    for (var i=0;i<bodies.length;i++) _openTasks.push(bodies[i].id);
};

A._runTask = function(step) {
    var params = {step:step};
    TASKS.forEach(function(t) {
        if (t.id===step) t.params.forEach(function(pp) { params[pp.k] = A.$('p_'+pp.k) ? A.$('p_'+pp.k).value : ''; });
    });
    A.post('/api/control/start', params, function(d) {
        if (d.ok) {
            taskState[step] = {status:'run',started:new Date(),stopped:null,startPct:stepPct(step),baseCount:stepCount(step).done};
            renderCyclo(); renderTasks(); loadStatus();
        }
    });
};

A._stopTask = function(step) {
    A.post('/api/control/stop', {step:step}, function(d) {
        if (d.ok) {
            taskState[step] = {status:'idle',started:taskState[step].started,stopped:new Date(),baseCount:0};
            renderCyclo(); renderTasks(); loadStatus();
        }
    });
};

A._resetTask = function(step) {
    var name = '';
    TASKS.forEach(function(t) { if (t.id===step) name = t.name; });
    if (!confirm('Сбросить результаты шага «'+name+'»?\nЭто обнулит прогресс и позволит выполнить шаг заново.')) return;
    A.post('/api/control/reset', {step:step}, function(d) {
        if (d.ok) {
            taskState[step] = {status:'idle',started:null,stopped:null,startPct:0,baseCount:0};
            renderCyclo(); renderTasks(); loadStatus();
        } else {
            alert('Ошибка: '+(d.error||'неизвестно'));
        }
    });
};

function runChain() {
    var lim = A.$('chainLimit').value;
    var rootId = A.$('chainRoot').value;
    var params = {step:'chain',ingest_limit:lim,desc_limit:lim,batch_size:(A.$('p_batch_size')?A.$('p_batch_size').value:6)||10,exif:(A.$('p_exif')?A.$('p_exif').value:'1')};
    if (rootId) params.root_id = rootId;
    A.post('/api/control/start', params, function(d) {
        if (d.ok) {
            A.$('chainInfo').textContent = '⚡ Запущено '+new Date().toLocaleTimeString();
            TASKS.forEach(function(t) { taskState[t.id].baseCount = stepCount(t.id).done; });
            renderCyclo(); renderTasks(); loadStatus();
        }
    });
}

function stopAll() {
    A.post('/api/control/stop', null, function() {
        TASKS.forEach(function(t) {
            if (taskState[t.id].status==='run') taskState[t.id] = {status:'idle',started:taskState[t.id].started,stopped:new Date(),baseCount:0};
        });
        A.$('chainInfo').textContent = 'Остановлено '+new Date().toLocaleTimeString();
        renderCyclo(); renderTasks(); loadStatus();
    });
}

function loadRoots() {
    A.ajax('/api/catalog/roots', function(roots) {
        var sel = A.$('chainRoot'); if (!sel) return;
        sel.innerHTML = '<option value="">Все включённые</option>';
        for (var i=0;i<roots.length;i++) {
            var r = roots[i];
            if (r.enabled) sel.innerHTML += '<option value="'+r.root_id+'">'+A.esc(r.alias)+'</option>';
        }
    });
}

function loadStatus() {
    A.ajax('/api/status', function(d) {
        st = d; A.st = d;
        var step = (d.step_details||'').toLowerCase();
        if (d.current_step==='idle') {
            TASKS.forEach(function(t) {
                if (taskState[t.id].status==='run') taskState[t.id].status = 'done';
                if (!taskState[t.id].stopped) taskState[t.id].stopped = new Date();
            });
        }
        renderSummary(); renderCyclo(); renderTasks();
        renderMQTT();
    });
}

function renderMQTT() {
    // Topbar MQTT summary uses processes from /api/status
    var proc = (st && st.processes) || {};
    var map = {vlm:'describe',face_pipeline:'faces',embed:'embed'};
    var ms = A.$('mqttSummary');
    if (ms) {
        var active = [];
        for (var k in map) if (proc[k]) active.push(map[k]);
        ms.innerHTML = active.map(function(n) { return '<span class="w run">⚡ '+n+'</span>'; }).join('') || '<span class="c-dim">idle</span>';
    }
}

// Duration timer updates
function updateTimers() {
    for (var i=0;i<STEPS.length;i++) {
        var ts = taskState[STEPS[i].id];
        var el = A.$('cyTime_'+STEPS[i].id);
        if (el && ts.status==='run' && ts.started) el.textContent = A.fmtDur(Date.now()-ts.started.getTime());
    }
    if (st && st.pipeline_started_at) {
        var ps = new Date(st.pipeline_started_at+(st.pipeline_started_at.indexOf('+')<0&&st.pipeline_started_at.indexOf('Z')<0?'+00:00':''));
        var pd = A.$('pbPipelineDur');
        if (pd) pd.textContent = A.fmtDur(Date.now()-ps.getTime());
    }
}

function startPolling() {
    stopPolling();
    loadStatus(); loadRoots();
    _statusTimer = setInterval(function() { loadStatus(); renderTasks(); }, 5000);
    _durationTimer = setInterval(updateTimers, 1000);
}

function stopPolling() {
    if (_statusTimer) { clearInterval(_statusTimer); _statusTimer = null; }
    if (_durationTimer) { clearInterval(_durationTimer); _durationTimer = null; }
}

A.on('navigate', function(page) {
    if (page==='pipeline') { buildUI('pipeline'); startPolling(); }
    else if (page==='tasks') { buildUI('tasks'); startPolling(); }
    else { stopPolling(); }
});

// Initial load
loadStatus(); loadRoots();
_statusTimer = setInterval(function() { loadStatus(); renderTasks(); }, 5000);
_durationTimer = setInterval(updateTimers, 1000);

})(window.Admin);

// Workers module
(function(A) {

var _crashVisible = false;
var _workerTimers = {};

A.registerBlock('workers', 'Воркеры MQTT', '🔌', function(cid) { A.renderBlock_workers(cid); }, function(cid, d) { A.refreshBlock_workers(cid, d); });

A.renderBlock_workers = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML =
        '<div class="workers-panel"><h3>🔌 Воркеры MQTT</h3>'+
        '<div class="workers-grid" id="wkGrid_'+containerId+'"></div>'+
        '<div id="dbWriterBlock_'+containerId+'"></div></div>';
    A.ajax('/api/mqtt/workers', function(d) {
        A.renderWorkerCards('wkGrid_'+containerId, d.workers || {});
        renderDbWriter('dbWriterBlock_'+containerId, d);
    });
};

A.refreshBlock_workers = function(containerId, d) {
    if (!d) return;
    var gridEl = document.getElementById('wkGrid_'+containerId);
    if (gridEl && d.workers) A.renderWorkerCards('wkGrid_'+containerId, d.workers);
};

function buildUI() {
    var el = A.$('page-workers');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">🔌 Воркеры MQTT</h2>'+
        '<div class="workers-panel"><h3>Воркеры MQTT <span id="watchdogStatus" style="font-weight:normal;font-size:11px"></span></h3>'+
        '<div class="workers-grid" id="workersGrid"></div>'+
        '<div id="dbWriterBlock"></div>'+
        '<div style="margin-top:8px"><button class="btn btn-go btn-sm" id="btnCrashLog">Журнал срабатываний</button><span id="crashCount" class="c-orange" style="font-size:11px;margin-left:8px"></span></div>'+
        '<div id="crashLog" class="crash-log" style="display:none"></div></div>';
    A.$('btnCrashLog').addEventListener('click', toggleCrashLog);
    loadWorkers();
}

function loadWorkers() {
    A.ajax('/api/mqtt/workers', function(d) {
        var w = d.workers || {};
        A.renderWorkerCards('workersGrid', w);
        renderDbWriter('dbWriterBlock', d);
        window._lastWorkers = w;
        var anyAlive = false, anyDead = false;
        for (var i=0;i<A.WORKER_NAMES.length;i++) {
            var s = w[A.WORKER_NAMES[i]] || {};
            if (s.alive) anyAlive = true;
            if (s.status==='dead') anyDead = true;
        }
        var info = A.$('watchdogInfo');
        if (info) {
            if (anyDead) info.textContent = '⚠ есть падения';
            else if (anyAlive) info.textContent = '✓ процессы работают';
            else info.textContent = '';
        }
    });
}

function toggleCrashLog() {
    _crashVisible = !_crashVisible;
    var el = A.$('crashLog');
    var btn = A.$('btnCrashLog');
    if (_crashVisible) {
        el.style.display = 'block';
        btn.textContent = 'Скрыть журнал';
        loadCrashes();
    } else {
        el.style.display = 'none';
        btn.textContent = 'Журнал срабатываний';
    }
}

function loadCrashes() {
    A.ajax('/api/watchdog/crashes', function(d) {
        var crashes = d.crashes || [];
        var countEl = A.$('crashCount');
        var statusEl = A.$('watchdogStatus');
        if (crashes.length>0) countEl.textContent = crashes.length+' срабатываний';
        else countEl.textContent = '';

        // Watchdog dot
        if (!A.$('watchdogDot')) {
            var dot = document.createElement('span');
            dot.id = 'watchdogDot';
            dot.className = 'wcard-dot';
            dot.style.marginRight = '4px';
            statusEl.parentNode.insertBefore(dot, statusEl);
        }
        var dotEl = A.$('watchdogDot');
        var mode = d.mode||'active';
        if (mode==='sleeping') {
            dotEl.className = 'wcard-dot sleeping';
            statusEl.innerHTML = '<span class="c-muted">🐶 Сторожевой пёс: </span><b class="c-warn">дремлет</b>';
        } else {
            dotEl.className = 'wcard-dot alive';
            statusEl.innerHTML = '<span class="c-muted">🐶 Сторожевой пёс: </span><b class="c-ok">активен</b>';
        }

        if (_crashVisible) {
            var el = A.$('crashLog');
            if (crashes.length===0) {
                el.innerHTML = '<span class="c-dim">Срабатываний нет — все процессы работают штатно</span>';
            } else {
                el.innerHTML = crashes.map(function(c) {
                    var t = A.esc(c);
                    var m = t.match(/^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
                    if (m) {
                        var d2 = new Date(m[1]+'Z');
                        if (!isNaN(d2.getTime())) {
                            var pad = function(n){return n<10?'0'+n:n;};
                            var local = d2.getFullYear()+'-'+pad(d2.getMonth()+1)+'-'+pad(d2.getDate())+' '+pad(d2.getHours())+':'+pad(d2.getMinutes())+':'+pad(d2.getSeconds());
                            t = t.replace(m[1], local);
                        }
                    }
                    if (t.indexOf('LWT DEAD')>=0) return '<span class="c-err">'+t+'</span>';
                    if (t.indexOf('RESTART')>=0) return '<span class="c-warn">'+t+'</span>';
                    if (t.indexOf('RECOVERY')>=0) return '<span class="c-ok">'+t+'</span>';
                    if (t.indexOf('STALE')>=0) return '<span class="c-orange">'+t+'</span>';
                    return t;
                }).join('<br>');
            }
        }
    });
}

function renderDbWriter(containerId, d) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var workers = d.workers || {};
    var p = workers.pipeline || {};
    var isAlive = p.alive || false;
    var dotCls = isAlive ? 'alive' : 'idle';
    var subTopic = 'gailray/db/cmd';
    var resTopic = 'gailray/db/result/{id}';
    var statusText = isAlive ? 'подписан на ' + subTopic : 'не запущен — запись через fallback';
    var statusCls = isAlive ? 'c-ok' : 'c-warn';
    el.innerHTML =
        '<div style="margin-top:12px;border-top:1px solid var(--border);padding-top:10px">'+
        '<div class="wcard" style="max-width:340px">'+
        '<div class="wcard-name"><span>🗄 DB Writer (pipeline)</span><span class="wcard-dot '+dotCls+'"></span></div>'+
        '<div class="wcard-row">Подписка: <b class="'+statusCls+'">'+esc(statusText)+'</b></div>'+
        '<div class="wcard-row c-dim" style="font-size:11px">Команды: insert_system_metric, control_reset, set_setting, update_photo, set_gps, set_date, mark_deleted, undelete, update_persona, merge_personas, add_catalog_root, vacuum, dedup_embeddings</div>'+
        '<div class="wcard-row c-dim" style="font-size:11px">Ответ: '+esc(resTopic)+'</div>'+
        '</div></div>';
}

A.on('navigate', function(page) {
    if (page==='workers') { buildUI(); loadWorkers(); loadCrashes(); }
});

// Periodic refresh for topbar info and in-page if visible
setInterval(function() {
    if (document.getElementById('page-workers') && document.getElementById('page-workers').classList.contains('active')) {
        loadWorkers(); loadCrashes();
    }
}, 5000);
setInterval(loadCrashes, 15000);

})(window.Admin);

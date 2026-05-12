// Gailery Admin Core
(function() {
var API = '/api';
var st = {};
var _events = {};
var _activePage = localStorage.getItem('admin-page') || 'dashboard';
var _isLightTheme = localStorage.getItem('gallery-theme') === 'light';

var WORKER_NAMES = ['ingest','describe','faces','exif','embed','pipeline','thumbnails','scan_catalog','enrich'];
var WORKER_LABELS = {ingest:'Наполнение',describe:'Описание',faces:'Лица',exif:'EXIF',embed:'Семантическая индексация',pipeline:'Пайплайн',thumbnails:'Превью',scan_catalog:'Каталог',enrich:'Обогащение'};

var DUAL_TASKS = [
    {id:'embed', name:'Семантическая индексация', modelId:'qwen3-embed', ollamaModel:'qwen3-embedding:0.6b', backendKey:'embed_backend'},
    {id:'semantic_search', name:'Семантический поиск', modelId:'qwen3-embed', ollamaModel:'qwen3-embedding:0.6b', backendKey:'search_backend'},
    {id:'describe', name:'Описание фото', modelId:'qwen3-vlm', ollamaModel:'qwen3.5:4b', backendKey:'describe_backend'},
];

function byId(id) { return document.getElementById(id); }
function qsa(sel) { return document.querySelectorAll(sel); }
function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function fmtPct(v) {
    if (!v) return '0%';
    if (v < 1) return v.toFixed(2)+'%';
    return v.toFixed(1)+'%';
}
function fmtTime(iso) { if (!iso) return '\u2014'; return iso.substring(11,19); }
function fmtDur(ms) {
    var s = Math.floor(ms/1000), m = Math.floor(s/60), h = Math.floor(m/60);
    if (h > 0) return h + 'ч ' + (m % 60) + 'м';
    if (m > 0) return m + 'м ' + (s % 60) + 'с';
    return s + 'с';
}
function fmtBytes(b) {
    if (!b) return '0';
    if (b < 1024) return b + 'B';
    if (b < 1048576) return (b/1024).toFixed(1) + 'KB';
    if (b < 1073741824) return (b/1048576).toFixed(1) + 'MB';
    return (b/1073741824).toFixed(1) + 'GB';
}

function ajax(url, ok, fail) {
    fetch(url).then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    }).then(ok).catch(function(e) {
        if (fail) fail(e);
    });
}
function apiPost(url, data, ok, fail) {
    fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: data ? JSON.stringify(data) : '{}'
    }).then(function(r) {
        if (!r.ok) return r.json().then(function(d) { throw new Error(d.detail||'HTTP '+r.status); });
        return r.json();
    }).then(ok).catch(function(e) {
        if (fail) fail(e);
    });
}
function apiPut(url, data, ok, fail) {
    fetch(url, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: data ? JSON.stringify(data) : '{}'
    }).then(function(r) {
        if (!r.ok) return r.json().then(function(d) { throw new Error(d.detail||'HTTP '+r.status); });
        return r.json();
    }).then(ok).catch(function(e) {
        if (fail) fail(e);
    });
}

function on(event, fn) {
    if (!_events[event]) _events[event] = [];
    _events[event].push(fn);
}
function emit(event, data) {
    var fns = _events[event] || [];
    for (var i = 0; i < fns.length; i++) fns[i](data);
}

function navigate(page) {
    _activePage = page;
    qsa('.sidebar a').forEach(function(a) { a.classList.remove('active'); });
    qsa('.page').forEach(function(p) { p.classList.remove('active'); });
    A.page = page;
    var l = document.querySelector('.sidebar a[data-page="' + page + '"]');
    if (l) l.classList.add('active');
    var p = byId('page-' + page);
    if (p) p.classList.add('active');
    localStorage.setItem('admin-page', page);
    emit('navigate', page);
    if (window.innerWidth <= 768) {
        var sb = byId('sidebar');
        if (sb) sb.classList.remove('open');
    }
}

function toggleSidebar() {
    var sb = byId('sidebar');
    if (sb) sb.classList.toggle('open');
}

function toggleTheme() {
    _isLightTheme = !_isLightTheme;
    document.body.classList.toggle('light-theme', _isLightTheme);
    localStorage.setItem('gallery-theme', _isLightTheme ? 'light' : 'dark');
    updateLogo();
    updateThemeBtn();
}

function updateLogo() {
    var logo = document.querySelector('.topbar .logo');
    if (!logo) return;
    logo.src = _isLightTheme ? (logo.getAttribute('data-light') || logo.getAttribute('data-dark')) : (logo.getAttribute('data-dark') || logo.getAttribute('data-light'));
}

function updateThemeBtn() {
    var btn = byId('themeBtn');
    if (!btn) return;
    btn.textContent = _isLightTheme ? '🌙' : '☀️';
    btn.title = _isLightTheme ? 'Ночная тема' : 'Дневная тема';
}

document.addEventListener('DOMContentLoaded', function() {
    qsa('.sidebar a').forEach(function(a) {
        a.addEventListener('click', function(e) {
            e.preventDefault();
            var p = a.getAttribute('data-page');
            if (p) navigate(p);
        });
    });
    var burger = document.querySelector('.burger');
    if (burger) burger.addEventListener('click', toggleSidebar);
    var themeBtn = byId('themeBtn');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
    if (_isLightTheme) document.body.classList.add('light-theme');
    updateLogo();
    updateThemeBtn();
    navigate(_activePage);
});

var A = {
    API: API,
    $: byId,
    $$: qsa,
    esc: esc,
    fmtPct: fmtPct,
    fmtTime: fmtTime,
    fmtDur: fmtDur,
    fmtBytes: fmtBytes,
    ajax: ajax,
    post: apiPost,
    put: apiPut,
    on: on,
    emit: emit,
    navigate: navigate,
    toggleSidebar: toggleSidebar,
    toggleTheme: toggleTheme,
    get st() { return st; },
    set st(v) { st = v; },
    WORKER_NAMES: WORKER_NAMES,
    WORKER_LABELS: WORKER_LABELS,
    DUAL_TASKS: DUAL_TASKS,
    renderWorkerCards: renderWorkerCards,
    registerBlock: registerBlock,
    getBlocks: function() { return _blocks; },
    getBlock: getBlock,
    getDashBlocks: getDashBlocks,
    setDashBlocks: setDashBlocks,
};

var _blocks = [];
var DEFAULT_DASH_BLOCKS = ['pipeline_status', 'workers'];

function registerBlock(id, name, icon, renderFn, refreshFn) {
    _blocks.push({id: id, name: name, icon: icon, render: renderFn, refresh: refreshFn || null});
}

function getDashBlocks() {
    var saved = localStorage.getItem('admin-dash-blocks');
    if (!saved) return DEFAULT_DASH_BLOCKS.slice();
    try { return JSON.parse(saved); } catch(e) { return DEFAULT_DASH_BLOCKS.slice(); }
}

function setDashBlocks(ids) {
    localStorage.setItem('admin-dash-blocks', JSON.stringify(ids));
}

function getBlock(id) {
    for (var i = 0; i < _blocks.length; i++) {
        if (_blocks[i].id === id) return _blocks[i];
    }
    return null;
}

function renderWorkerCards(containerId, workers) {
    var el = byId(containerId);
    if (!el) return;
    var h = '';
    for (var i=0;i<WORKER_NAMES.length;i++) {
        var name = WORKER_NAMES[i];
        var s = workers[name] || {status:'idle',alive:false,gpu_held:false};
        var dotCls = s.alive ? 'alive' : (s.status==='dead'?'dead':(s.status==='done'?'done':'idle'));
        var label = WORKER_LABELS[name]||name;
        h += '<div class="wcard">';
        h += '<div class="wcard-name"><span>'+esc(label)+'</span><span class="wcard-dot '+dotCls+'" title="'+esc(s.status)+'"></span></div>';
        h += '<div class="wcard-row">Статус: <b>'+esc(s.status||'idle')+'</b></div>';
        if (s.pid) h += '<div class="wcard-row">PID: <b>'+s.pid+'</b></div>';
        if (s.progress&&s.progress.total>0) h += '<div class="wcard-row">'+s.progress.done+'/'+s.progress.total+' ('+s.progress.pct.toFixed(1)+'%)</div>';
        if (s.gpu_held) h += '<div class="wcard-row wcard-gpu">GPU</div>';
        h += '</div>';
    }
    el.innerHTML = h;
}

window.Admin = A;

document.addEventListener('DOMContentLoaded', function() {
    var vi = document.getElementById('versionInfo');
    if (vi) {
        A.ajax('/api/status', function(d) {
            var c = (d.git_commit || '').substring(0,7);
            var dt = d.git_date || '';
            vi.innerHTML = '<div class="ver">Gailery · '+c+' · '+dt+'<br><a href="#" id="checkUpdate">Проверить обновления</a></div>';
            document.getElementById('checkUpdate').addEventListener('click', function(e) {
                e.preventDefault();
                var self = this;
                self.textContent = 'Проверяем…';
                A.post('/api/control/update', null, function(r) {
                    if (r && r.ok) {
                        if (r.updated) {
                            self.textContent = 'Обновлено → перезапуск';
                            setTimeout(function() { location.reload(); }, 3000);
                        } else {
                            self.textContent = 'Уже актуально';
                        }
                    } else {
                        self.textContent = 'Ошибка';
                    }
                });
            });
        });
    }
});
})();

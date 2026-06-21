// Logs module
(function(A) {

var _logFilter = '';
var _logFilterMap = {};
var _logTimer = null;
var _logAutoRefresh = {};
var _logRefreshCid = null;

function startLogRefresh(cid) {
    _logRefreshCid = cid;
    if (_logTimer) clearInterval(_logTimer);
    _logTimer = setInterval(function() { if (_logAutoRefresh[cid] !== false) loadLogInto(cid); }, 3000);
}
function stopLogRefresh() {
    if (_logTimer) { clearInterval(_logTimer); _logTimer = null; }
}

A.registerBlock('logs', 'Логи', '📋', function(cid) { A.renderBlock_logs(cid); }, function(cid) { if (_logAutoRefresh[cid] !== false) loadLogInto(cid); });

function buildUI() {
    var el = A.$('page-logs');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">📋 Логи</h2>'+
        '<div id="logsBlock"></div>';
    A.renderBlock_logs('logsBlock');
}

A.renderBlock_logs = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var fId = 'logFilter_'+containerId;
    var cId = 'logC_'+containerId;
    var iId = 'logInfo_'+containerId;
    var arId = 'logAutoRefresh_'+containerId;
    _logAutoRefresh[containerId] = true;
    el.innerHTML =
        '<div class="log-sec"><h3 style="display:flex;align-items:center;gap:8px">Лог <span id="'+iId+'"></span><label style="font-size:12px;font-weight:400;cursor:pointer;display:flex;align-items:center;gap:4px;margin-left:auto"><input type="checkbox" id="'+arId+'" checked> автообновление</label></h3>'+
        '<div style="display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap;align-items:center">'+
        '<input id="'+fId+'" type="text" placeholder="Фильтр..." class="log-filter-input">'+
        '<button class="fbtn" data-f="DESCRIBE" data-cid="'+containerId+'">VLM</button>'+
        '<button class="fbtn" data-f="FACES" data-cid="'+containerId+'">Лица</button>'+
        '<button class="fbtn" data-f="EMBED" data-cid="'+containerId+'">Индекс</button>'+
        '<button class="fbtn" data-f="PIPELINE" data-cid="'+containerId+'">Пайплайн</button>'+
        '<button class="fbtn" data-f="ENRICH" data-cid="'+containerId+'">Обогащ.</button>'+
        '<button class="fbtn fbtn-err" data-f="ERROR,FAILED" data-cid="'+containerId+'">Ошибки</button>'+
        '<button class="fbtn fbtn-all" data-f="" data-cid="'+containerId+'">Все</button></div>'+
        '<div id="'+cId+'"></div></div>';

    el.querySelectorAll('.fbtn[data-cid="'+containerId+'"]').forEach(function(b) {
        b.addEventListener('click', function() {
            setFilter(containerId, this.getAttribute('data-f'));
        });
    });

    var arCb = document.getElementById(arId);
    if (arCb) arCb.addEventListener('change', function() {
        _logAutoRefresh[containerId] = this.checked;
    });

    var inp = document.getElementById(fId);
    if (inp) inp.addEventListener('input', function() {
        var v = this.value.trim();
        if (!v) { _logFilterMap[containerId] = ''; el.querySelectorAll('.fbtn').forEach(function(b){b.classList.remove('active');}); }
        else { _logFilterMap[containerId] = v; el.querySelectorAll('.fbtn').forEach(function(b){b.classList.remove('active');}); }
        loadLogInto(containerId);
    });

    loadLogInto(containerId);
    if (containerId === 'logsBlock') startLogRefresh(containerId);
};

var _logActiveFilters = {};

function setFilter(cid, f) {
    if (!_logActiveFilters[cid]) _logActiveFilters[cid] = {};
    var active = _logActiveFilters[cid];
    if (!f) {
        active = {};
        _logActiveFilters[cid] = active;
    } else {
        if (active[f]) delete active[f];
        else active[f] = true;
    }
    var filterStr = Object.keys(active).join(',');
    _logFilterMap[cid] = filterStr;
    var el = document.getElementById(cid);
    var fId = 'logFilter_'+cid;
    var inp = document.getElementById(fId);
    if (inp) inp.value = '';
    if (el) el.querySelectorAll('.fbtn').forEach(function(b) {
        var bf = b.getAttribute('data-f');
        b.classList.toggle('active', !bf ? Object.keys(active).length === 0 : !!active[bf]);
    });
    applyFilter(cid);
}

A._setLogFilter = function(f) {
    _logFilter = f;
    var inp = A.$('logFilter');
    if (inp) inp.value = f.indexOf(',')>=0 ? '' : f;
    A.$$('.fbtn').forEach(function(b) { b.classList.toggle('active', b.getAttribute('data-f')===f); });
    applyFilter('');
};

function applyFilter(cid) {
    var cId = cid ? 'logC_'+cid : 'logC';
    var iId = cid ? 'logInfo_'+cid : 'logInfo';
    var filter = cid ? (_logFilterMap[cid]||'') : _logFilter;
    var el = document.getElementById(cId);
    if (!el) return;
    if (!filter) {
        el.querySelectorAll('.ll').forEach(function(s){s.style.display='';});
        updateInfo(cid, el);
        return;
    }
    var terms = filter.toUpperCase().split(',');
    el.querySelectorAll('.ll').forEach(function(s) {
        var txt = s.textContent.toUpperCase();
        var show = terms.some(function(t) { return t && txt.indexOf(t)>=0; });
        s.style.display = show ? '' : 'none';
    });
    updateInfo(cid, el);
}

function updateInfo(cid, el) {
    var iId = cid ? 'logInfo_'+cid : 'logInfo';
    var filter = cid ? (_logFilterMap[cid]||'') : _logFilter;
    var total = el ? (el.getAttribute('data-total')||'0') : '0';
    var shown = el ? el.querySelectorAll('.ll').length : 0;
    var visible = filter ? (el?el.querySelectorAll('.ll:not([style*="display: none"])').length:0) : shown;
    var info = document.getElementById(iId);
    if (info) info.textContent = filter ? visible+'/'+shown+'/'+total : shown+'/'+total;
}

function loadLogInto(cid) {
    var cId = 'logC_'+cid;
    var iId = 'logInfo_'+cid;
    A.ajax('/api/log?lines=2000', function(d) {
        var el = document.getElementById(cId);
        if (!el) return;
        var wasBot = el.scrollTop+el.clientHeight >= el.scrollHeight-20;
        var h = '';
        for (var i=0;i<d.lines.length;i++) {
            var t = d.lines[i].replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\r/g,'');
            var m = t.match(/^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
            if (m) {
                var d2 = new Date(m[1]+'Z');
                if (!isNaN(d2.getTime())) {
                    var pad = function(n){return n<10?'0'+n:n;};
                    var local = d2.getFullYear()+'-'+pad(d2.getMonth()+1)+'-'+pad(d2.getDate())+' '+pad(d2.getHours())+':'+pad(d2.getMinutes())+':'+pad(d2.getSeconds());
                    t = t.replace(m[1], local);
                }
            }
            var cls = 'll';
            if (t.indexOf('[DESCRIBE]')>=0) cls += ' l-DESCRIBE';
            else if (t.indexOf('[FACES]')>=0) cls += ' l-FACES';
            else if (t.indexOf('[EXIF]')>=0) cls += ' l-EXIF';
            else if (t.indexOf('[EMBED]')>=0) cls += ' l-EMBED';
            else if (t.indexOf('[PIPELINE]')>=0) cls += ' l-PIPELINE';
            else if (t.indexOf('[INGEST]')>=0) cls += ' l-INGEST';
            else if (t.indexOf('[ENRICH]')>=0) cls += ' l-ENRICH';
            else if (t.indexOf('[WATCHDOG]')>=0) cls += ' l-WATCHDOG';
            if (t.indexOf('FAILED')>=0||t.indexOf('ERROR')>=0) cls += ' l-error';
            if (t.indexOf('DONE')>=0||t.indexOf('START')>=0) cls += ' l-DONE';
            h += '<div class="'+cls+'">'+t+'</div>';
        }
        el.innerHTML = h;
        el.setAttribute('data-total', d.total);
        var filter = _logFilterMap[cid]||'';
        var info = document.getElementById(iId);
        if (info) info.textContent = filter ? '?/'+d.lines.length+'/'+d.total : d.lines.length+'/'+d.total;
        if (wasBot) el.scrollTop = el.scrollHeight;
        applyFilter(cid);
        updateInfo(cid, el);
    });
}

A.on('navigate', function(page) {
    if (page==='logs') { buildUI(); }
    else { stopLogRefresh(); }
});

})(window.Admin);
// Audit log module — клиентские действия
(function(A) {

var _timer = null;
var _autoRefresh = true;
var _filterIp = '';
var _filterMethod = '';
var _filterPath = '';

function startRefresh() {
    if (_timer) clearInterval(_timer);
    _timer = setInterval(function() { if (_autoRefresh) loadAudit(); }, 5000);
}
function stopRefresh() {
    if (_timer) { clearInterval(_timer); _timer = null; }
}

function buildUI() {
    var el = A.$('page-audit');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">🛡️ Аудит клиентских действий</h2>' +
        '<div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;align-items:center">' +
            '<input id="auditIp" type="text" placeholder="IP..." class="log-filter-input" style="width:140px">' +
            '<select id="auditMethod" class="log-filter-input" style="width:90px">' +
                '<option value="">Все методы</option>' +
                '<option value="GET">GET</option>' +
                '<option value="POST">POST</option>' +
                '<option value="PUT">PUT</option>' +
                '<option value="DELETE">DELETE</option>' +
                '<option value="PATCH">PATCH</option>' +
            '</select>' +
            '<input id="auditPath" type="text" placeholder="Путь..." class="log-filter-input" style="width:240px">' +
            '<button class="fbtn fbtn-all" id="auditSearch">Найти</button>' +
            '<button class="fbtn" id="auditClear">Сброс</button>' +
            '<label style="font-size:12px;cursor:pointer;display:flex;align-items:center;gap:4px;margin-left:auto">' +
                '<input type="checkbox" id="auditAuto" checked> автообновление</label>' +
        '</div>' +
        '<div id="auditInfo" style="font-size:12px;color:var(--c-dim);margin-bottom:4px"></div>' +
        '<div id="auditContainer" class="log-container"></div>';

    var searchBtn = document.getElementById('auditSearch');
    if (searchBtn) searchBtn.addEventListener('click', function() {
        _filterIp = (document.getElementById('auditIp').value || '').trim();
        _filterMethod = (document.getElementById('auditMethod').value || '').trim();
        _filterPath = (document.getElementById('auditPath').value || '').trim();
        loadAudit();
    });
    var clearBtn = document.getElementById('auditClear');
    if (clearBtn) clearBtn.addEventListener('click', function() {
        document.getElementById('auditIp').value = '';
        document.getElementById('auditMethod').value = '';
        document.getElementById('auditPath').value = '';
        _filterIp = ''; _filterMethod = ''; _filterPath = '';
        loadAudit();
    });
    var autoCb = document.getElementById('auditAuto');
    if (autoCb) autoCb.addEventListener('change', function() { _autoRefresh = this.checked; });

    var pathInp = document.getElementById('auditPath');
    if (pathInp) pathInp.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { if (searchBtn) searchBtn.click(); }
    });
    var ipInp = document.getElementById('auditIp');
    if (ipInp) ipInp.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { if (searchBtn) searchBtn.click(); }
    });

    loadAudit();
    startRefresh();
}

function loadAudit() {
    var params = ['limit=300'];
    if (_filterIp) params.push('ip=' + encodeURIComponent(_filterIp));
    if (_filterMethod) params.push('method=' + encodeURIComponent(_filterMethod));
    if (_filterPath) params.push('path=' + encodeURIComponent(_filterPath));
    A.ajax('/api/audit/log?' + params.join('&'), function(d) {
        var el = document.getElementById('auditContainer');
        if (!el) return;
        var info = document.getElementById('auditInfo');
        if (info) info.textContent = 'Записей: ' + d.entries.length + ' / ' + d.total;
        var h = '';
        for (var i = 0; i < d.entries.length; i++) {
            var e = d.entries[i];
            var ts = e.ts || '';
            var m = ts.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})/);
            if (m) {
                var d2 = new Date(m[1] + 'T' + m[2] + 'Z');
                if (!isNaN(d2.getTime())) {
                    var pad = function(n) { return n < 10 ? '0' + n : n; };
                    ts = d2.getFullYear() + '-' + pad(d2.getMonth() + 1) + '-' + pad(d2.getDate()) +
                         ' ' + pad(d2.getHours()) + ':' + pad(d2.getMinutes()) + ':' + pad(d2.getSeconds());
                } else {
                    ts = m[1] + ' ' + m[2];
                }
            }
            var cls = 'll';
            var mc = (e.method || '').toUpperCase();
            if (mc === 'POST' || mc === 'PUT' || mc === 'DELETE' || mc === 'PATCH') cls += ' l-mut';
            else if (mc === 'GET') cls += ' l-get';
            var sc = e.status || 0;
            if (sc >= 400) cls += ' l-error';
            else if (sc >= 300) cls += ' l-warn';
            var scopeTag = e.scope ? ' <span class="c-dim" style="font-size:10px">[' + escHtml(e.scope) + ']</span>' : '';
            var uaTag = e.user_agent ? ' <span class="c-dim" style="font-size:10px">' + escHtml(e.user_agent.substring(0, 40)) + '</span>' : '';
            var stCls = sc >= 400 ? 'st-err' : (sc >= 300 ? 'st-warn' : 'st-ok');
            h += '<div class="' + cls + '"><span class="c-dim">' + escHtml(ts) + '</span> ' +
                 '<b>' + escHtml(e.ip || '') + '</b> ' +
                 '<span class="' + (mc === 'GET' ? 'c-info' : 'c-err') + '">' + escHtml(mc) + '</span> ' +
                 '<span class="c-info">' + escHtml(e.path || '') + '</span> ' +
                 '<span class="' + stCls + '">' + sc + '</span>' +
                 scopeTag + uaTag + '</div>';
        }
        el.innerHTML = h || '<div class="c-dim" style="padding:20px">Нет записей</div>';
        el.scrollTop = 0;
    });
}

function escHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

A.on('navigate', function(page) {
    if (page === 'audit') { buildUI(); }
    else { stopRefresh(); }
});

})(window.Admin);

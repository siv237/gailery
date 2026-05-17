(function(A) {

var _timer = null;

A.registerBlock('services', 'Службы', '🔌', function(cid) { A.renderBlock_services(cid); }, function(cid, d) { A.refreshBlock_services(cid, d); });

function buildUI() {
    var el = A.$('page-services');
    if (!el) return;
    el.innerHTML = '<h2 class="page-h2">🔌 Службы</h2><div id="svcBlock"></div>';
    A.renderBlock_services('svcBlock');
}

A.renderBlock_services = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div style="color:var(--c-text-muted);padding:12px">⏳ Загрузка...</div>';
    loadServices(containerId);
};

A.refreshBlock_services = function(containerId, d) {
    loadServices(containerId);
};

function loadServices(containerId) {
    A.ajax('/api/services', function(d) {
        var svcs = d.services || [];
        var groups = {};
        for (var i = 0; i < svcs.length; i++) {
            var g = svcs[i].group || 'other';
            if (!groups[g]) groups[g] = [];
            groups[g].push(svcs[i]);
        }
        var h = '';
        var groupNames = {gailery: 'Gailery', system: 'Системные'};
        for (var gKey in groups) {
            h += '<div class="workers-panel" style="margin-bottom:12px">';
            h += '<h3>' + A.esc(groupNames[gKey] || gKey) + '</h3>';
            h += '<table class="svc-table">';
            h += '<thead><tr><th>Служба</th><th>Статус</th><th>Автозапуск</th><th></th></tr></thead>';
            h += '<tbody>';
            for (var j = 0; j < groups[gKey].length; j++) {
                var s = groups[gKey][j];
                var statusCls = s.status === 'active' ? 'c-ok' : (s.status === 'failed' ? 'c-err' : 'c-warn');
                var statusIcon = s.status === 'active' ? '●' : (s.status === 'failed' ? '✗' : '○');
                var enabledCls = s.enabled === 'enabled' ? 'c-ok' : (s.enabled === 'disabled' ? 'c-err' : 'c-dim');
                var enabledText = s.enabled === 'enabled' ? 'вкл' : (s.enabled === 'disabled' ? 'выкл' : s.enabled);
                h += '<tr data-svc="' + A.esc(s.id) + '">';
                h += '<td class="svc-name">' + A.esc(s.label) + '<div class="c-dim" style="font-size:10px">' + A.esc(s.id) + '</div></td>';
                h += '<td class="svc-status"><span class="' + statusCls + '">' + statusIcon + ' ' + A.esc(s.status) + '</span></td>';
                h += '<td class="svc-enabled"><span class="' + enabledCls + '">' + A.esc(enabledText) + '</span></td>';
                h += '<td class="svc-action"><button class="btn btn-sec btn-sm svc-restart" data-svc="' + A.esc(s.id) + '">🔄 Перезапуск</button><span class="svc-restart-st"></span></td>';
                h += '</tr>';
            }
            h += '</tbody></table></div>';
        }
        var el = document.getElementById(containerId);
        if (el) el.innerHTML = h;
        el.querySelectorAll('.svc-restart').forEach(function(btn) {
            btn.addEventListener('click', function() { restartService(this); });
        });
    });
}

function restartService(btn) {
    var svc = btn.getAttribute('data-svc');
    var row = btn.closest('tr');
    var st = row.querySelector('.svc-restart-st');
    btn.disabled = true;
    if (st) { st.textContent = '⏳'; st.className = 'svc-restart-st c-info'; }
    A.post('/api/services/' + encodeURIComponent(svc) + '/restart', null, function(d) {
        if (d.ok) {
            if (st) { st.textContent = '✓'; st.className = 'svc-restart-st c-ok'; }
        } else {
            if (st) { st.textContent = '✗ ' + (d.error || ''); st.className = 'svc-restart-st c-err'; }
        }
        setTimeout(function() { loadServices(btn.closest('[id]').id); }, 2000);
    }, function() {
        if (st) { st.textContent = '✗ Ошибка'; st.className = 'svc-restart-st c-err'; }
        btn.disabled = false;
    });
}

A.on('navigate', function(page) {
    if (_timer) { clearInterval(_timer); _timer = null; }
    if (page === 'services') {
        buildUI();
        _timer = setInterval(function() { loadServices('svcBlock'); }, 10000);
    }
});

})(window.Admin);

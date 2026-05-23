// Dashboard module — popup selector, close buttons, single-poll, theme-aware
(function(A) {

var _timer = null;
var _lastStatus = null;
var _lastWorkers = null;
var _ddDocHandler = null;

function buildUI() {
    var el = A.$('page-dashboard');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">📊 Дашборд</h2>'+
        '<div style="margin-bottom:16px;display:flex;align-items:center;gap:8px">'+
        '<div class="dash-pick" id="dashPick">'+
        '<button class="dash-pick-btn" id="dashPickBtn">＋ Добавить блок</button>'+
        '<div class="dash-pick-dd" id="dashPickDd"></div>'+
        '</div></div>'+
        '<div id="dashBlocks"></div>';
    setupPicker();
    renderDashBlocks();
    startPolling();
}

function setupPicker() {
    var btn = A.$('dashPickBtn');
    var dd = A.$('dashPickDd');
    var pick = A.$('dashPick');
    if (!btn || !dd || !pick) return;
    var blocks = A.getBlocks();
    var selected = A.getDashBlocks();
    var h = '';
    for (var i = 0; i < blocks.length; i++) {
        var b = blocks[i];
        var checked = selected.indexOf(b.id) >= 0;
        h += '<label><input type="checkbox" class="dpick-cb" data-bid="'+b.id+'"'+(checked?' checked':'')+'> '+b.icon+' '+A.esc(b.name)+'</label>';
    }
    dd.innerHTML = h;

    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
        dd.classList.toggle('open');
        if (dd.classList.contains('open')) {
            if (_ddDocHandler) document.removeEventListener('click', _ddDocHandler);
            _ddDocHandler = function(ev) {
                if (!pick.contains(ev.target)) dd.classList.remove('open');
            };
            setTimeout(function() { document.addEventListener('click', _ddDocHandler); }, 0);
        }
    });

    dd.querySelectorAll('.dpick-cb').forEach(function(cb) {
        cb.addEventListener('click', function(e) {
            e.stopPropagation();
        });
        cb.addEventListener('change', function() {
            var bid = this.getAttribute('data-bid');
            var selected = A.getDashBlocks();
            if (this.checked) {
                if (selected.indexOf(bid) < 0) selected.push(bid);
            } else {
                var idx = selected.indexOf(bid);
                if (idx >= 0) selected.splice(idx, 1);
            }
            A.setDashBlocks(selected);
            renderDashBlocks();
        });
    });
}

function renderDashBlocks() {
    var el = A.$('dashBlocks');
    if (!el) return;
    var selected = A.getDashBlocks();
    el.innerHTML = '';
    if (selected.length === 0) {
        el.innerHTML = '<div class="c-dim" style="padding:40px 0;text-align:center;font-size:14px">Добавьте блоки кнопкой «＋ Добавить блок» выше</div>';
        return;
    }
    for (var i = 0; i < selected.length; i++) {
        var bid = selected[i];
        var block = A.getBlock(bid);
        if (!block) continue;
        var wrap = document.createElement('div');
        wrap.className = 'card';
        wrap.style.marginBottom = '16px';
        wrap.id = 'dash_blk_'+bid;
        var closeBtn = document.createElement('button');
        closeBtn.className = 'card-close';
        closeBtn.textContent = '×';
        closeBtn.setAttribute('data-bid', bid);
        closeBtn.addEventListener('click', function() {
            removeBlock(this.getAttribute('data-bid'));
        });
        wrap.appendChild(closeBtn);
        el.appendChild(wrap);
        block.render('dash_blk_'+bid);
    }
    if (_lastStatus) refreshBlocks(_lastStatus);
}

function removeBlock(bid) {
    var selected = A.getDashBlocks();
    var idx = selected.indexOf(bid);
    if (idx >= 0) {
        selected.splice(idx, 1);
        A.setDashBlocks(selected);
    }
    var dd = A.$('dashPickDd');
    if (dd) {
        var cb = dd.querySelector('.dpick-cb[data-bid="'+bid+'"]');
        if (cb) cb.checked = false;
    }
    var wrap = document.getElementById('dash_blk_'+bid);
    if (wrap) wrap.remove();
    var selected2 = A.getDashBlocks();
    if (selected2.length === 0) {
        var el = A.$('dashBlocks');
        if (el) el.innerHTML = '<div class="c-dim" style="padding:40px 0;text-align:center;font-size:14px">Добавьте блоки кнопкой «＋ Добавить блок» выше</div>';
    }
}

function refreshBlocks(d) {
    var selected = A.getDashBlocks();
    for (var i = 0; i < selected.length; i++) {
        var bid = selected[i];
        var block = A.getBlock(bid);
        if (!block || !block.refresh) continue;
        var payload = (bid === 'workers') ? _lastWorkers : d;
        try { block.refresh('dash_blk_'+bid, payload); } catch(e) {}
    }
}

function startPolling() {
    stopPolling();
    loadStatus();
    _timer = setInterval(loadStatus, 5000);
}

function stopPolling() {
    if (_timer) { clearInterval(_timer); _timer = null; }
}

function loadStatus() {
    A.ajax('/api/status', function(d) {
        _lastStatus = d;
        A.st = d;
        refreshBlocks(d);
    });
    A.ajax('/api/mqtt/workers', function(d) {
        _lastWorkers = d;
        A.workers = d.workers || {};
        if (_lastStatus) refreshBlocks(_lastStatus);
    });
}

A.on('navigate', function(page) {
    if (page === 'dashboard') { buildUI(); }
    else { stopPolling(); }
});

})(window.Admin);

// Tools module: hashes, duplicates, backup, maintenance
(function(A) {

var hashWorkerPid = 0, _hashPollTimer = null;

A.registerBlock('hashes', 'Хеши и дубликаты', '🔗', function(cid) { A.renderBlock_hashes(cid); });
A.registerBlock('maintenance', 'Обслуживание БД', '🛠️', function(cid) { A.renderBlock_maintenance(cid); });

// ═══════ HASHES ═══════
function buildHashes() {
    var el = A.$('page-hashes');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">🔗 Хеши и дубликаты</h2>'+
        '<div id="hashesBlock"></div>';
    A.renderBlock_hashes('hashesBlock');
}

A.renderBlock_hashes = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var pfx = 'hs_'+containerId+'_';
    el.innerHTML =
        '<div class="maint-sec"><h3>🔗 Контроль хешей файлов</h3>'+
        '<div id="'+pfx+'stats" style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px"></div>'+
        '<div class="maint-row"><button class="btn btn-go" id="'+pfx+'start">Запустить расчёт хешей</button><button class="btn btn-stop" id="'+pfx+'stop" disabled>Остановить</button><span class="maint-info">xxHash128 для всех файлов без хеша</span></div>'+
        '<div class="maint-row"><button class="btn btn-go" id="'+pfx+'dups">Найти дубликаты файлов</button><span class="maint-info">Бит-в-бит совпадения по content_hash</span></div>'+
        '<div id="'+pfx+'status" class="backup-status"></div>'+
        '<div id="'+pfx+'dupList" style="max-height:300px;overflow:auto;margin-top:8px;font-size:12px"></div></div>';

    document.getElementById(pfx+'start').addEventListener('click', function() { hashBackfill(containerId); });
    document.getElementById(pfx+'stop').addEventListener('click', function() { hashBackfillStop(containerId); });
    document.getElementById(pfx+'dups').addEventListener('click', function() { hashFindDuplicates(containerId); });
    loadHashStats(containerId);
};

function loadHashStats(cid) {
    var pfx = 'hs_'+cid+'_';
    A.ajax('/api/catalog/hash_status', function(d) {
        var total = d.total_files||0, withH = d.with_hash||0, withoutH = d.without_hash||0;
        var zeroByte = d.zero_byte||0, pendingH = d.pending_hash||0;
        var dupGroups = d.duplicate_groups||0, dupFiles = d.duplicate_files||0;
        var pct = total>0 ? Math.round(withH/total*100) : 0;
        var h = '';
        h += '<div class="maint-sbox"><div class="sv">'+withH+' / '+total+'</div><div class="sl">С хешем ('+pct+'%)</div></div>';
        if (pendingH>0) h += '<div class="maint-sbox"><div class="sv c-orange">'+pendingH+'</div><div class="sl">Ждут хеширования</div></div>';
        if (zeroByte>0) h += '<div class="maint-sbox bd-err"><div class="sv c-err">'+zeroByte+'</div><div class="sl">Повреждены (0 байт)</div></div>';
        if (dupGroups>0) h += '<div class="maint-sbox bd-err"><div class="sv c-err">'+dupGroups+'</div><div class="sl">Групп дублей ('+dupFiles+' файлов)</div></div>';
        var statsEl = document.getElementById(pfx+'stats');
        if (statsEl) statsEl.innerHTML = h;
        var startBtn = document.getElementById(pfx+'start');
        if (withoutH===0 && startBtn) startBtn.disabled = true;
    });
    A.ajax('/api/catalog/hash_backfill_status', function(d) {
        if (d.running && d.pids && d.pids.length>0) {
            hashWorkerPid = d.pids[0];
            var startBtn = document.getElementById(pfx+'start');
            var stopBtn = document.getElementById(pfx+'stop');
            var statusEl = document.getElementById(pfx+'status');
            if (startBtn) startBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = false;
            if (statusEl) { statusEl.className = 'backup-status ok'; statusEl.textContent = 'Воркер работает (PID '+hashWorkerPid+')'; }
            pollHashWorker(cid);
        }
    });
}

function hashBackfill(cid) {
    var pfx = 'hs_'+cid+'_';
    var el = document.getElementById(pfx+'status');
    if (!el) return;
    el.className = 'backup-status'; el.textContent = 'Запуск расчёта хешей...';
    A.post('/api/catalog/hash_backfill', null, function(d) {
        hashWorkerPid = d.pid;
        el.className = 'backup-status ok';
        el.textContent = 'Воркер запущен (PID '+d.pid+')';
        var startBtn = document.getElementById(pfx+'start');
        var stopBtn = document.getElementById(pfx+'stop');
        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = false;
        pollHashWorker(cid);
    }, function(e) {
        el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message;
    });
}

function hashBackfillStop(cid) {
    if (!hashWorkerPid) return;
    var pfx = 'hs_'+cid+'_';
    var el = document.getElementById(pfx+'status');
    A.post('/api/catalog/hash_backfill_stop', null, function(d) {
        if (el) { el.className = 'backup-status ok'; el.textContent = 'Воркер остановлен (killed PIDs: '+(d.killed||[]).join(', ')+')'; }
        hashWorkerPid = 0;
        var startBtn = document.getElementById(pfx+'start');
        var stopBtn = document.getElementById(pfx+'stop');
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
        if (_hashPollTimer) { clearTimeout(_hashPollTimer); _hashPollTimer = null; }
        loadHashStats(cid);
    }, function(e) {
        if (el) { el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message; }
    });
}

function pollHashWorker(cid) {
    var pfx = 'hs_'+cid+'_';
    A.ajax('/api/catalog/hash_backfill_status', function(d) {
        var el = document.getElementById(pfx+'status');
        var startBtn = document.getElementById(pfx+'start');
        var stopBtn = document.getElementById(pfx+'stop');
        if (!d.running) {
            if (el) { el.className = 'backup-status ok'; el.textContent = 'Расчёт хешей завершён'; }
            hashWorkerPid = 0;
            if (startBtn) startBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = true;
            loadHashStats(cid);
            return;
        }
        if (d.pids && d.pids.length>0) hashWorkerPid = d.pids[0];
        loadHashStats(cid);
        _hashPollTimer = setTimeout(function() { pollHashWorker(cid); }, 5000);
    }, function() {
        _hashPollTimer = setTimeout(function() { pollHashWorker(cid); }, 10000);
    });
}

function hashFindDuplicates(cid) {
    var pfx = 'hs_'+cid+'_';
    var el = document.getElementById(pfx+'status');
    var dl = document.getElementById(pfx+'dupList');
    if (el) { el.className = 'backup-status'; el.textContent = 'Поиск дубликатов...'; }
    if (dl) dl.innerHTML = '';
    A.ajax('/api/catalog/duplicates?limit=100', function(d) {
        var groups = d.duplicates||[];
        if (groups.length===0) {
            if (el) { el.className = 'backup-status ok'; el.textContent = 'Дубликатов не найдено'; }
            return;
        }
        if (el) { el.className = 'backup-status ok'; el.textContent = 'Найдено '+groups.length+' групп дубликатов'; }
        var h = '';
        for (var i=0;i<groups.length;i++) {
            var g = groups[i];
            h += '<div class="bg-deep bd-strong" style="margin-bottom:8px;padding:6px;border-width:1px;border-style:solid;border-radius:4px">';
            h += '<b class="c-orange">'+g.count+' копий</b> <span class="c-dim">'+A.esc(g.hash)+'</span>';
            for (var j=0;j<g.paths.length;j++) {
                var p = g.paths[j].replace(/\\\\/g,'/');
                var short = p.split('/').slice(-2).join('/');
                h += '<div class="c-muted" style="padding-left:12px;word-break:break-all" title="'+A.esc(p)+'">'+A.esc(short)+'</div>';
            }
            h += '</div>';
        }
        if (dl) dl.innerHTML = h;
        loadHashStats(cid);
    }, function(e) {
        if (el) { el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message; }
    });
}

// ═══════ MAINTENANCE + BACKUP ═══════
function buildMaint() {
    var el = A.$('page-maint');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">🛠️ Обслуживание БД</h2>'+
        '<div id="maintBlock"></div>';
    A.renderBlock_maintenance('maintBlock');
}

A.renderBlock_maintenance = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var pfx = 'mt_'+containerId+'_';
    el.innerHTML =
        '<div class="backup-sec"><h3>💾 Бекап базы данных</h3>'+
        '<div class="backup-row"><button class="btn btn-go" id="'+pfx+'dl">⬇ Скачать бекап</button>'+
        '<label class="btn btn-go" style="cursor:pointer">⬆ Загрузить бекап <input type="file" accept=".gz,.db" id="'+pfx+'ul" style="display:none"></label>'+
        '<span class="backup-info" id="'+pfx+'info"></span></div>'+
        '<div id="'+pfx+'bkStatus" class="backup-status"></div></div>'+
        '<div class="maint-sec"><h3>🔧 Обслуживание базы данных</h3>'+
        '<div id="'+pfx+'sizes" class="maint-sizes"></div>'+
        '<div class="maint-row"><button class="btn btn-go" id="'+pfx+'vacuum">VACUUM SQLite</button><span class="maint-info">Сжать SQLite, удалить мусор</span></div>'+
        '<div class="maint-row"><button class="btn btn-go" id="'+pfx+'dedup">Удалить дубли семантических индексов</button><span class="maint-info">LanceDB: убрать повторные записи</span></div>'+
        '<div id="'+pfx+'mtStatus" class="backup-status"></div></div>'+
        '<div class="maint-sec"><h3>📋 Оптимизация логов</h3>'+
        '<div id="'+pfx+'logSizes" class="maint-sizes"></div>'+
        '<div class="maint-row"><button class="btn btn-go" id="'+pfx+'logRotate">Ротация всех логов</button><span class="maint-info">Архив в logs/archive/*.gz + обнуление; меньше 512КБ — пропускаются</span></div>'+
        '<div class="maint-row"><label>AI-лог: удалить записи старше</label>'+
        '<select id="'+pfx+'aiDays" style="margin:0 8px 0 4px"><option value="30">30 дней</option><option value="90" selected>90 дней</option><option value="180">180 дней</option><option value="365">год</option></select>'+
        '<button class="btn btn-go" id="'+pfx+'aiPrune">Очистить и сжать</button><span class="maint-info">ai_log.db — журнал AI-вызовов</span></div>'+
        '<div id="'+pfx+'logStatus" class="backup-status"></div></div>';

    document.getElementById(pfx+'dl').addEventListener('click', function() { backupDownload(containerId); });
    document.getElementById(pfx+'ul').addEventListener('change', function() { backupUpload(containerId, this); });
    document.getElementById(pfx+'vacuum').addEventListener('click', function() { maintVacuum(containerId); });
    document.getElementById(pfx+'dedup').addEventListener('click', function() { maintDedup(containerId); });
    document.getElementById(pfx+'logRotate').addEventListener('click', function() { maintLogRotate(containerId); });
    document.getElementById(pfx+'aiPrune').addEventListener('click', function() { maintAiLogPrune(containerId); });
    loadMaintStats(containerId);
    loadLogStats(containerId);
};

function loadMaintStats(cid) {
    var pfx = 'mt_'+cid+'_';
    A.ajax('/api/maintenance/stats', function(d) {
        var h = '';
        var sqliteMain = d['gallery.db']||0, sqliteWAL = d['gallery.db-wal']||0;
        h += '<div class="maint-sbox"><div class="sv">'+A.fmtBytes(sqliteMain)+'</div><div class="sl">gallery.db</div></div>';
        if (sqliteWAL>1048576) h += '<div class="maint-sbox"><div class="sv">'+A.fmtBytes(sqliteWAL)+'</div><div class="sl">gallery.db-wal</div></div>';
        var legacyDb = d['gailray.db']||0, legacyWAL = d['gailray.db-wal']||0;
        if (legacyDb>0) h += '<div class="maint-sbox legacy"><div class="sv">'+A.fmtBytes(legacyDb+legacyWAL)+'</div><div class="sl">gailray.db (устарела)</div></div>';

        var lanceNames = {
            'photo_embeddings':'Семантические индексы','face_vectors':'Векторы лиц',
            'faces':'Лица (legacy)','personas':'Персоны','photos':'Фото (legacy)',
            'catalog_files':'Каталог файлов','catalog_roots':'Каталог корней'
        };
        var lt = d.lance_tables||{};
        var lanceOrder = ['photo_embeddings','face_vectors','personas','faces','photos','catalog_files','catalog_roots'];
        for (var i=0;i<lanceOrder.length;i++) {
            var k = lanceOrder[i];
            if (lt[k]!==undefined && lt[k]>0) {
                var cls = (k==='faces'||k==='photos')?' legacy':'';
                h += '<div class="maint-sbox'+cls+'"><div class="sv">'+A.fmtBytes(lt[k])+'</div><div class="sl">'+(lanceNames[k]||k)+'</div></div>';
            }
        }
        h += '<div class="maint-sbox total"><div class="sv">'+A.fmtBytes(d.data_total)+'</div><div class="sl">Всего данных</div></div>';
        var sizesEl = document.getElementById(pfx+'sizes');
        if (sizesEl) sizesEl.innerHTML = h;
    });
}

function backupDownload(cid) {
    var pfx = 'mt_'+cid+'_';
    var el = document.getElementById(pfx+'bkStatus');
    if (!el) return;
    el.className = 'backup-status'; el.textContent = 'Создание бекапа...';
    fetch('/api/backup/download').then(function(r) {
        if (!r.ok) throw new Error('HTTP '+r.status);
        var sz = r.headers.get('content-length');
        var mb = sz ? (parseInt(sz)/1048576).toFixed(1)+'MB' : '';
        el.className = 'backup-status ok'; el.textContent = 'Скачивание... '+mb;
        return r.blob();
    }).then(function(blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = 'gallery_backup.db.gz'; a.click();
        URL.revokeObjectURL(url);
        el.className = 'backup-status ok'; el.textContent = 'Бекап скачан ('+(blob.size/1048576).toFixed(1)+'MB)';
    }).catch(function(e) {
        el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message;
    });
}

function backupUpload(cid, input) {
    if (!input.files || !input.files[0]) return;
    var file = input.files[0];
    var pfx = 'mt_'+cid+'_';
    var el = document.getElementById(pfx+'bkStatus');
    if (!el) return;
    el.className = 'backup-status'; el.textContent = 'Загрузка '+file.name+' ('+(file.size/1048576).toFixed(1)+'MB)...';
    var fd = new FormData(); fd.append('file', file);
    fetch('/api/backup/upload', {method:'POST', body:fd}).then(function(r) {
        if (!r.ok) return r.json().then(function(d) { throw new Error(d.detail||'HTTP '+r.status); });
        return r.json();
    }).then(function() {
        el.className = 'backup-status ok'; el.textContent = 'БД восстановлена! Перезапустите сервис для применения.';
    }).catch(function(e) {
        el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message;
    });
    input.value = '';
}

function maintVacuum(cid) {
    var pfx = 'mt_'+cid+'_';
    var el = document.getElementById(pfx+'mtStatus');
    if (!el) return;
    el.className = 'backup-status'; el.textContent = 'VACUUM...';
    A.post('/api/maintenance/vacuum', null, function(d) {
        el.className = 'backup-status ok';
        el.textContent = 'VACUUM: '+A.fmtBytes(d.before)+' → '+A.fmtBytes(d.after)+' (освобождено '+A.fmtBytes(d.freed)+')';
        loadMaintStats(cid);
    }, function(e) {
        el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message;
    });
}

function maintDedup(cid) {
    var pfx = 'mt_'+cid+'_';
    var el = document.getElementById(pfx+'mtStatus');
    if (!el) return;
    el.className = 'backup-status'; el.textContent = 'Дедупликация семантических индексов... (может занять минуту)';
    A.post('/api/maintenance/dedup_embeddings', null, function(d) {
        el.className = 'backup-status ok';
        el.textContent = 'Было '+d.before+' → стало '+d.after+' (удалено '+d.removed+' дублей)';
        loadMaintStats(cid);
    }, function(e) {
        el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message;
    });
}

// ═══════ LOGS ═══════
function loadLogStats(cid) {
    var pfx = 'mt_'+cid+'_';
    A.ajax('/api/maintenance/logs', function(d) {
        var h = '';
        var files = d.files||[];
        var top = files.slice(0, 6);
        for (var i=0;i<top.length;i++) {
            var f = top[i];
            h += '<div class="maint-sbox"><div class="sv">'+A.fmtBytes(f.size)+'</div><div class="sl" title="'+A.esc(f.name)+'">'+A.esc(f.name)+'</div>'+
                 '<div style="margin-top:4px"><button class="btn btn-stop" style="font-size:10px;padding:2px 8px" data-log="'+A.esc(f.name)+'">обнулить</button></div></div>';
        }
        if (d.ai_log_db > 0) {
            h += '<div class="maint-sbox"><div class="sv">'+A.fmtBytes(d.ai_log_db)+'</div><div class="sl">ai_log.db ('+(d.ai_log_rows>=0?d.ai_log_rows:'?')+' вызовов)</div></div>';
        }
        if (files.length > 6) {
            h += '<div class="maint-sbox"><div class="sv">'+files.length+'</div><div class="sl">всего файлов</div></div>';
        }
        h += '<div class="maint-sbox total"><div class="sv">'+A.fmtBytes(d.total + (d.ai_log_db||0))+'</div><div class="sl">логи всего</div></div>';
        var sizesEl = document.getElementById(pfx+'logSizes');
        if (sizesEl) sizesEl.innerHTML = h;
        sizesEl.querySelectorAll('button[data-log]').forEach(function(btn) {
            btn.addEventListener('click', function() { maintLogClear(cid, btn.getAttribute('data-log')); });
        });
    });
}

function maintLogRotate(cid) {
    var pfx = 'mt_'+cid+'_';
    var el = document.getElementById(pfx+'logStatus');
    if (!confirm('Ротировать все логи?\nКаждый лог будет заархивирован в logs/archive/ и обнулён.')) return;
    if (!el) return;
    el.className = 'backup-status'; el.textContent = 'Ротация (архивация может занять время на больших файлах)...';
    A.post('/api/maintenance/logs/rotate', null, function(d) {
        var rotated = d.rotated||[];
        var names = rotated.map(function(r) { return r.name+' ('+A.fmtBytes(r.size)+')'; }).join(', ');
        el.className = 'backup-status ok';
        el.textContent = 'Освобождено '+A.fmtBytes(d.freed)+'.'+(names?' Ротированы: '+names+'.':' Файлы <512КБ — пропущены.');
        loadLogStats(cid);
    }, function(e) {
        el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message;
    });
}

function maintLogClear(cid, name) {
    var pfx = 'mt_'+cid+'_';
    var el = document.getElementById(pfx+'logStatus');
    if (!confirm('Обнулить лог «'+name+'»?\nСодержимое будет удалено без архива.')) return;
    A.post('/api/maintenance/logs/clear', {name: name}, function(d) {
        if (el) { el.className = 'backup-status ok'; el.textContent = '«'+name+'» обнулён, освобождено '+A.fmtBytes(d.freed); }
        loadLogStats(cid);
    }, function(e) {
        if (el) { el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message; }
    });
}

function maintAiLogPrune(cid) {
    var pfx = 'mt_'+cid+'_';
    var el = document.getElementById(pfx+'logStatus');
    var days = document.getElementById(pfx+'aiDays') ? document.getElementById(pfx+'aiDays').value : 90;
    if (!confirm('Удалить AI-вызовы старше '+days+' дней и сжать ai_log.db?')) return;
    if (!el) return;
    el.className = 'backup-status'; el.textContent = 'Очистка AI-лога... (VACUUM может занять минуту)';
    A.post('/api/maintenance/ai_log/prune', {days: parseInt(days, 10)}, function(d) {
        el.className = 'backup-status ok';
        el.textContent = 'Удалено '+d.deleted+' записей: '+A.fmtBytes(d.before)+' → '+A.fmtBytes(d.after)+' (освобождено '+A.fmtBytes(d.freed)+')';
        loadLogStats(cid);
    }, function(e) {
        el.className = 'backup-status err'; el.textContent = 'Ошибка: '+e.message;
    });
}

A.on('navigate', function(page) {
    if (page==='hashes') { buildHashes(); }
    if (page==='maint') { buildMaint(); }
});

})(window.Admin);

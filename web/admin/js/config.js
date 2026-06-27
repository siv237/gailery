// Config module: config, models, family
(function(A) {

A.registerBlock('config', 'Конфигурация', '⚙️', function(cid) { A.renderBlock_config(cid); });
A.registerBlock('models', 'Модели', '💻', function(cid) { A.renderBlock_models(cid); });
A.registerBlock('prompts', 'Промты', '💬', function(cid) { A.renderBlock_prompts(cid); });
A.registerBlock('family', 'Семейные данные', '👨‍👩‍👧‍👦', function(cid) { A.renderBlock_family(cid); });

// ═══════ CONFIG ═══════
function buildConfig() {
    var el = A.$('page-config');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">⚙️ Конфигурация</h2>'+
        '<div id="configBlock"></div>';
    A.renderBlock_config('configBlock');
}

A.renderBlock_config = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div id="cfgContent_'+containerId+'">⏳ Загрузка...</div>';
    A.ajax('/api/config', function(cfg) {
        var groups = cfg.groups||[];
        var h = '';
        for (var i=0;i<groups.length;i++) {
            var g = groups[i];
            if (g.name === 'Промты') continue;
            h += '<div class="cfg-group"><div class="cfg-group-head">'+(g.icon||'')+' '+A.esc(g.name)+'</div>';
            for (var j=0;j<g.params.length;j++) {
                var p = g.params[j];
                var isPrompt = p.k.indexOf('SYSTEM_PROMPT')!==-1||p.k.indexOf('tool:')!==-1;
                var pathCol = '<div class="cfg-path"></div>';
                if (p.path) {
                    var cls = p.exists ? 'c-ok' : 'c-err';
                    var sym = p.exists ? '✓' : '✗';
                    var ttl = p.exists ? 'Путь существует' : 'Путь НЕ найден!';
                    pathCol = '<div class="cfg-path '+cls+'" title="'+ttl+'">'+sym+'</div>';
                }
                h += '<div class="cfg-row';
                if (p.editable) h += ' cfg-editable';
                h += '" data-env="'+A.esc(p.env_key||'')+'">';
                h += '<div class="cfg-key">'+A.esc(p.k)+'</div>';
                if (isPrompt) {
                    h += '<div class="cfg-val cfg-prompt"><pre>'+A.esc(p.v)+'</pre></div>';
                } else if (p.editable) {
                    h += '<div class="cfg-val cfg-edit-val" data-original="'+A.esc(p.v)+'" data-env="'+A.esc(p.env_key||'')+'">'+A.esc(p.v)+'</div>';
                } else {
                    h += '<div class="cfg-val">'+A.esc(p.v)+'</div>';
                }
                h += '<div class="cfg-desc">'+A.esc(p.d)+'</div>'+pathCol+'</div>';
            }
            h += '</div>';
        }
        var content = document.getElementById('cfgContent_'+containerId);
        if (content) content.innerHTML = h;
        var editVals = content.querySelectorAll('.cfg-edit-val');
        for (var k=0;k<editVals.length;k++) {
            editVals[k].addEventListener('click', function(e) { startCfgEdit(this); });
        }
    });
};

function startCfgEdit(valEl) {
    if (valEl.classList.contains('cfg-editing')) return;
    var original = valEl.getAttribute('data-original');
    var envKey = valEl.getAttribute('data-env');
    valEl.classList.add('cfg-editing');
    valEl.innerHTML = '<input class="cfg-input" value="'+A.esc(original)+'" />'+
        '<button class="btn btn-go btn-sm cfg-save" title="Сохранить">✓</button>'+
        '<button class="btn btn-sec btn-sm cfg-cancel" title="Отмена">✗</button>'+
        '<span class="cfg-save-st"></span>';
    var inp = valEl.querySelector('.cfg-input');
    var saveBtn = valEl.querySelector('.cfg-save');
    var cancelBtn = valEl.querySelector('.cfg-cancel');
    inp.focus();
    inp.select();
    inp.addEventListener('keydown', function(e) {
        if (e.key==='Enter') saveCfgEdit(valEl, envKey);
        if (e.key==='Escape') cancelCfgEdit(valEl, original);
    });
    saveBtn.addEventListener('click', function(e) { e.stopPropagation(); saveCfgEdit(valEl, envKey); });
    cancelBtn.addEventListener('click', function(e) { e.stopPropagation(); cancelCfgEdit(valEl, original); });
    inp.addEventListener('click', function(e) { e.stopPropagation(); });
}

function saveCfgEdit(valEl, envKey) {
    var inp = valEl.querySelector('.cfg-input');
    var st = valEl.querySelector('.cfg-save-st');
    var newVal = inp ? inp.value.trim() : '';
    var original = valEl.getAttribute('data-original');
    if (!envKey) { cancelCfgEdit(valEl, original); return; }
    if (st) { st.textContent = '⏳'; st.className = 'cfg-save-st c-info'; }
    A.post('/api/config/update', {env_key: envKey, value: newVal}, function(d) {
        if (d.ok) {
            valEl.setAttribute('data-original', newVal);
            finishCfgEdit(valEl, newVal, '✓ Сохранено', 'c-ok');
        } else {
            finishCfgEdit(valEl, original, '✗ '+(d.error||''), 'c-err');
        }
    }, function(e) {
        finishCfgEdit(valEl, original, '✗ Ошибка сети', 'c-err');
    });
}

function finishCfgEdit(valEl, value, msg, msgCls) {
    valEl.classList.remove('cfg-editing');
    valEl.innerHTML = '<span>'+A.esc(value)+'</span> <span class="cfg-save-st '+msgCls+'">'+msg+'</span>';
    setTimeout(function() {
        valEl.textContent = value;
        valEl.addEventListener('click', function(e) { startCfgEdit(this); });
    }, 2000);
}

function cancelCfgEdit(valEl, original) {
    valEl.classList.remove('cfg-editing');
    valEl.textContent = original;
    valEl.addEventListener('click', function(e) { startCfgEdit(this); });
}

// ═══════ PROMPTS ═══════
function buildPrompts() {
    var el = A.$('page-prompts');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">💬 Промты</h2>'+
        '<div id="promptsBlock"></div>';
    A.renderBlock_prompts('promptsBlock');
}

A.renderBlock_prompts = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var pfx = 'prm_'+containerId+'_';
    el.innerHTML = '<div id="prmContent_'+containerId+'">⏳ Загрузка...</div>';
    A.ajax('/api/config', function(cfg) {
        var groups = cfg.groups||[];
        var pg = null;
        for (var i=0;i<groups.length;i++) {
            if (groups[i].name === 'Промты') { pg = groups[i]; break; }
        }
        if (!pg) { el.innerHTML = '<div class="c-muted">Промты не найдены</div>'; return; }
        var promptDefaults = {};
        var h = '';
        for (var j=0;j<pg.params.length;j++) {
            var p = pg.params[j];
            var isTool = p.k.indexOf('tool:')!==-1;
            var isSystem = p.k.indexOf('SYSTEM_PROMPT')!==-1;
            if (p.default) promptDefaults[p.env_key] = p.default;
            h += '<div class="cfg-group" style="margin-bottom:16px">';
            if (isSystem) {
                h += '<div class="cfg-group-head" style="margin-bottom:8px">'+A.esc(p.k)+'</div>';
                h += '<div class="c-muted" style="font-size:12px;margin-bottom:6px">'+A.esc(p.d)+'</div>';
                h += '<textarea class="prm-ta" id="'+pfx+'ta_'+j+'" data-env="'+A.esc(p.env_key||"")+'" data-original="'+A.esc(p.v)+'" rows="12" style="width:100%;min-height:200px;font-family:monospace;font-size:13px;line-height:1.6;resize:vertical;border:1px solid var(--bd);border-radius:6px;padding:10px;background:var(--bg-deep);color:var(--fg)">'+A.esc(p.v)+'</textarea>';
                h += '<div style="margin-top:6px;display:flex;gap:8px;align-items:center"><button class="btn btn-go btn-sm" data-prm-idx="'+j+'" data-prm-env="'+A.esc(p.env_key||"")+'">Сохранить</button><button class="btn btn-sec btn-sm prm-reset" data-prm-idx="'+j+'" data-prm-env="'+A.esc(p.env_key||"")+'" title="Сбросить к умолчанию">↺ Сброс</button><span class="prm-st" id="'+pfx+'st_'+j+'"></span></div>';
            } else if (isTool) {
                h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">';
                h += '<span style="font-weight:600;font-size:13px">🔧 '+A.esc(p.k.replace('Enrich tool: ',''))+'</span></div>';
                h += '<div class="c-muted" style="font-size:12px;margin-bottom:6px">'+A.esc(p.d)+'</div>';
                h += '<textarea class="prm-ta" id="'+pfx+'ta_'+j+'" data-env="'+A.esc(p.env_key||"")+'" data-original="'+A.esc(p.v)+'" rows="4" style="width:100%;min-height:60px;font-family:monospace;font-size:13px;line-height:1.5;resize:vertical;border:1px solid var(--bd);border-radius:6px;padding:10px;background:var(--bg-deep);color:var(--fg)">'+A.esc(p.v)+'</textarea>';
                h += '<div style="margin-top:6px;display:flex;gap:8px;align-items:center"><button class="btn btn-go btn-sm" data-prm-idx="'+j+'" data-prm-env="'+A.esc(p.env_key||"")+'">Сохранить</button><button class="btn btn-sec btn-sm prm-reset" data-prm-idx="'+j+'" data-prm-env="'+A.esc(p.env_key||"")+'" title="Сбросить к умолчанию">↺ Сброс</button><span class="prm-st" id="'+pfx+'st_'+j+'"></span></div>';
            }
            h += '</div>';
        }
        var content = document.getElementById('prmContent_'+containerId);
        if (content) content.innerHTML = h;
        content.querySelectorAll('button[data-prm-idx]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var idx = this.getAttribute('data-prm-idx');
                var envKey = this.getAttribute('data-prm-env');
                var ta = document.getElementById(pfx+'ta_'+idx);
                var stEl = document.getElementById(pfx+'st_'+idx);
                if (!ta || !envKey) return;
                var newVal = ta.value;
                if (stEl) { stEl.textContent = '⏳'; stEl.className = 'prm-st c-info'; }
                A.post('/api/config/update', {env_key: envKey, value: newVal}, function(d) {
                    if (d.ok) {
                        ta.setAttribute('data-original', newVal);
                        if (stEl) { stEl.textContent = '✓ Сохранено'; stEl.className = 'prm-st c-ok'; }
                    } else {
                        if (stEl) { stEl.textContent = '✗ '+(d.error||''); stEl.className = 'prm-st c-err'; }
                    }
                }, function() {
                    if (stEl) { stEl.textContent = '✗ Ошибка сети'; stEl.className = 'prm-st c-err'; }
                });
                setTimeout(function() { if (stEl) stEl.textContent = ''; }, 3000);
            });
        });
        content.querySelectorAll('.prm-reset').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var envKey = this.getAttribute('data-prm-env');
                var idx = this.getAttribute('data-prm-idx');
                var defaultVal = promptDefaults[envKey] || '';
                var stEl = document.getElementById(pfx+'st_'+idx);
                var ta = document.getElementById(pfx+'ta_'+idx);
                if (!envKey) return;
                if (ta) ta.value = defaultVal;
                A.post('/api/config/update', {env_key: envKey, value: defaultVal}, function(d) {
                    if (d.ok) {
                        if (ta) ta.setAttribute('data-original', defaultVal);
                        if (stEl) { stEl.textContent = '✓ Сброшено к умолчанию'; stEl.className = 'prm-st c-ok'; }
                    } else {
                        if (stEl) { stEl.textContent = '✗ '+(d.error||''); stEl.className = 'prm-st c-err'; }
                    }
                });
            });
        });
    });
};

// ═══════ MODELS ═══════
function buildModels() {
    var el = A.$('page-models');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">💻 Модели</h2>'+
        '<div id="modelsBlock"></div>';
    A.renderBlock_models('modelsBlock');
}

A.renderBlock_models = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var pfx = 'mdl_'+containerId+'_';
    el.innerHTML =
        '<div class="mdl-token-box">'+
        '<div style="margin-bottom:12px"><div style="font-weight:600;font-size:13px;margin-bottom:4px">📁 Папка моделей</div>'+
        '<div class="c-muted" style="font-size:11px;margin-bottom:6px">Все модели должны быть внутри этой директории</div>'+
        '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'+
        '<input id="'+pfx+'dir" class="mdl-input" style="min-width:280px" placeholder="/opt/gailery/models/gguf">'+
        '<button class="btn btn-go btn-sm" id="'+pfx+'saveDir">Сохранить</button>'+
        '<span id="'+pfx+'dirSt" style="font-size:11px"></span></div></div>'+
        '<div style="margin-bottom:12px"><div style="font-weight:600;font-size:13px;margin-bottom:4px">🔑 HuggingFace API Token</div>'+
        '<div class="c-muted" style="font-size:11px;margin-bottom:6px">Нужен для скачивания моделей с HuggingFace</div>'+
        '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'+
        '<input id="'+pfx+'hfToken" class="mdl-input" style="min-width:280px" type="password" placeholder="hf_token...">'+
        '<button class="btn btn-sec btn-sm" id="'+pfx+'showToken">👁</button>'+
        '<button class="btn btn-go btn-sm" id="'+pfx+'saveToken">Сохранить</button>'+
        '<span id="'+pfx+'hfSt" style="font-size:11px"></span></div></div>'+
        '<div id="'+pfx+'status" class="mdl-status"></div></div>'+
        '<div id="'+pfx+'list">⏳ Загрузка моделей...</div>';

    document.getElementById(pfx+'saveDir').addEventListener('click', function() { saveModelsDir(containerId); });
    document.getElementById(pfx+'saveToken').addEventListener('click', function() { saveHfToken(containerId); });
    document.getElementById(pfx+'showToken').addEventListener('click', function() {
        var inp = document.getElementById(pfx+'hfToken');
        if (inp) inp.type = inp.type==='password'?'text':'password';
    });
    loadModels(containerId);
};

function saveModelsDir(cid) {
    var pfx = 'mdl_'+cid+'_';
    var dir = document.getElementById(pfx+'dir').value.trim();
    var el = document.getElementById(pfx+'dirSt');
    if (!dir) { if (el) { el.textContent = 'Путь пуст'; el.className = 'c-err'; } return; }
    A.put('/api/models/dir', {path:dir}, function(d) {
        if (el) { el.textContent = '✓ Сохранено: '+d.models_dir; el.className = 'c-ok'; }
        if (d.note) setTimeout(function() { if (el) { el.textContent = d.note; el.className = 'c-warn'; } }, 2000);
        loadModels(cid);
    }, function(e) {
        if (el) { el.textContent = 'Ошибка: '+e.message; el.className = 'c-err'; }
    });
    setTimeout(function() { if (el) el.textContent = ''; }, 5000);
}

function saveHfToken(cid) {
    var pfx = 'mdl_'+cid+'_';
    var token = document.getElementById(pfx+'hfToken').value.trim();
    var el = document.getElementById(pfx+'hfSt');
    A.put('/api/settings/hf_token', {value:token}, function() {
        if (el) { el.textContent = '✓ Сохранено'; el.className = 'c-ok'; }
        loadModels(cid);
    }, function() {
        if (el) { el.textContent = 'Ошибка'; el.className = 'c-err'; }
    });
    setTimeout(function() { if (el) el.textContent = ''; }, 3000);
}

function loadModels(cid) {
    var pfx = 'mdl_'+cid+'_';
    var listEl = document.getElementById(pfx+'list');
    if (!listEl) return;
    listEl.innerHTML = '⏳ Загрузка моделей...';
    A.ajax('/api/models', function(d) {
        var html = '';
        var models = d.models||[];
        for (var i=0;i<models.length;i++) {
            var m = models[i];
            var statusCls = m.present?'c-ok':'c-err';
            var statusText = m.present?'OK':'ОТСУТСТВУЕТ';
            if (m.present && m.size_ok===false) { statusCls='c-err'; statusText='РАЗМЕР НЕ СОВПАДАЕТ'; }
            else if (m.present && m.verified) { statusCls='c-ok'; statusText='ВЕРИФИЦИРОВАН'; }
            else if (m.present && m.size_ok) { statusCls='c-info'; statusText='OK (размер совпадает)'; }
            var sizeText = m.total_size_mb>0?(m.total_size_mb>1024?(m.total_size_mb/1024).toFixed(1)+' GB':m.total_size_mb.toFixed(0)+' MB'):'';
            html += '<div class="mdl-card">';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">';
            html += '<div><span style="font-weight:600;font-size:14px">'+A.esc(m.name)+'</span> <span class="'+statusCls+'" style="font-size:12px;font-weight:600">['+statusText+']</span></div>';
            html += '<div style="display:flex;gap:6px;align-items:center">';
            if (sizeText) html += '<span class="mdl-size">'+sizeText+'</span>';
            html += '<button class="btn btn-sec btn-sm" data-action="check" data-model="'+m.id+'" data-cid="'+cid+'" style="font-size:11px;padding:3px 10px">🔍 Проверить</button>';
            if (!m.present) html += '<button class="btn btn-go btn-sm" data-action="download" data-model="'+m.id+'" data-cid="'+cid+'" style="font-size:11px;padding:3px 10px">⬇ Скачать</button>';
            html += '</div></div>';
            html += '<div class="mdl-role">'+A.esc(m.role)+'</div>';
            if (m.note) html += '<div class="c-info" style="font-size:11px;margin-top:2px">'+A.esc(m.note)+'</div>';
            html += '<div class="mdl-sub">Репо: '+A.esc(m.repo)+' | Тип: '+m.type+' | Использует: '+A.esc(m.used_by||'')+'</div>';
            if (m.files && m.files.length) {
                html += '<div class="mdl-file-list">';
                for (var j=0;j<m.files.length;j++) {
                    var f = m.files[j];
                    var fc = f.exists?'c-ok':'c-err';
                    var fs = f.size_mb>0?' ('+f.size_mb.toFixed(0)+' MB)':'';
                    var hashIcon = '';
                    if (f.exists && f.sha256_ok===true) hashIcon = ' <span class="c-ok" title="SHA256 совпадает">🔒</span>';
                    else if (f.exists && f.sha256_ok===false) hashIcon = ' <span class="c-err" title="SHA256 НЕ совпадает!">🔓</span>';
                    else if (f.exists && f.size_ok===false) hashIcon = ' <span class="c-err" title="Размер не совпадает!">⚠</span>';
                    else if (f.exists && f.size_ok && f.sha256_ok===undefined) hashIcon = ' <span class="c-info" title="Размер совпадает, SHA256 не проверен">🔍</span>';
                    html += '<div class="mdl-file-item"><span class="'+fc+'">'+(f.exists?'✓':'✗')+'</span> '+A.esc(f.name)+fs+hashIcon+'</div>';
                }
                html += '</div>';
            }
            html += '</div>';
        }
        listEl.innerHTML = html;
        listEl.querySelectorAll('button[data-action="check"]').forEach(function(btn) {
            btn.addEventListener('click', function() { checkModel(cid, this.getAttribute('data-model')); });
        });
        listEl.querySelectorAll('button[data-action="download"]').forEach(function(btn) {
            btn.addEventListener('click', function() { downloadModel(cid, this.getAttribute('data-model')); });
        });
        var statusEl = document.getElementById(pfx+'status');
        if (d.hf_token_set) {
            if (statusEl) statusEl.innerHTML = '';
        } else {
            if (statusEl) statusEl.innerHTML = '<span class="c-warn">⚠ HF token не задан — скачивание моделей невозможно</span>';
        }
        if (d.models_dir) {
            var dirInput = document.getElementById(pfx+'dir');
            if (dirInput) dirInput.value = d.models_dir;
        }
    }, function(e) {
        listEl.innerHTML = '<div class="c-err">Ошибка загрузки: '+e+'</div>';
    });
    A.ajax('/api/settings/hf_token', function(d) {
        var hfInput = document.getElementById(pfx+'hfToken');
        if (hfInput && d.value) hfInput.value = d.value;
    });
}

function checkModel(cid, modelId) {
    var pfx = 'mdl_'+cid+'_';
    var el = document.getElementById(pfx+'status');
    if (el) el.innerHTML = '<span class="c-info">🔍 Проверка SHA256 '+modelId+'... (может занять ~30с)</span>';
    fetch('/api/models/check/'+modelId).then(function(r){return r.json()}).then(function(d) {
        if (d.verified) { if (el) el.innerHTML = '<span class="c-ok">✓ '+modelId+': SHA256 верифицирован</span>'; }
        else if (d.present) { if (el) el.innerHTML = '<span class="c-err">✗ '+modelId+': файл есть, но SHA256 НЕ совпадает!</span>'; }
        else { if (el) el.innerHTML = '<span class="c-err">✗ '+modelId+': файл отсутствует</span>'; }
        loadModels(cid);
    }).catch(function(e) { if (el) el.innerHTML = '<span class="c-err">✗ Ошибка: '+e+'</span>'; });
}

function downloadModel(cid, modelId) {
    var pfx = 'mdl_'+cid+'_';
    var el = document.getElementById(pfx+'status');
    if (el) el.innerHTML = '<span class="c-info">⬇ Скачивание '+modelId+'...</span>';
    A.post('/api/models/download/'+modelId, null, function(d) {
        if (d.status==='ok') {
            if (el) el.innerHTML = '<span class="c-ok">✓ Модель '+modelId+' скачана</span>';
            loadModels(cid);
        } else {
            if (el) el.innerHTML = '<span class="c-err">✗ Ошибка: '+A.esc(d.error||'unknown')+'</span>';
        }
    }, function(e) {
        if (el) el.innerHTML = '<span class="c-err">✗ Ошибка сети: '+e+'</span>';
    });
}

A._checkModel = function(modelId) { checkModel('modelsBlock', modelId); };
A._downloadModel = function(modelId) { downloadModel('modelsBlock', modelId); };

// ═══════ FAMILY ═══════
function buildFamily() {
    var el = A.$('page-family');
    if (!el) return;
    el.innerHTML =
        '<h2 class="page-h2">👨‍👩‍👧‍👦 Семейные данные</h2>'+
        '<div id="familyBlock"></div>';
    A.renderBlock_family('familyBlock');
}

A.renderBlock_family = function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var pfx = 'fm_'+containerId+'_';
    el.innerHTML =
        '<div class="backup-sec"><h3>Факты о семье и связях</h3>'+
        '<p class="c-muted" style="font-size:12px;margin:4px 0 8px">Имена, родственные связи, даты, события. Модель обогащения описаний будет использовать этот текст для подстановки имён и контекста.</p>'+
        '<textarea class="c-text bg-deep bd-strong" style="width:100%;min-height:400px;border-width:1px;border-style:solid;border-radius:6px;padding:10px;font-family:monospace;font-size:13px;line-height:1.6;resize:vertical" id="'+pfx+'facts"></textarea>'+
        '<div class="maint-row"><button class="btn btn-go btn-sm" id="'+pfx+'save">Сохранить</button><button class="btn btn-sec btn-sm" id="'+pfx+'fill">Заполнить топ-10 персон</button><span id="'+pfx+'status" style="font-size:12px"></span></div></div>';

    document.getElementById(pfx+'save').addEventListener('click', function() { saveFamilyFacts(containerId); });
    document.getElementById(pfx+'fill').addEventListener('click', function() { fillTopPersonas(containerId); });
    A.ajax('/api/settings/family_facts', function(d) {
        var ta = document.getElementById(pfx+'facts');
        if (ta) ta.value = d.value||'';
    });
};

function saveFamilyFacts(cid) {
    var pfx = 'fm_'+cid+'_';
    var ta = document.getElementById(pfx+'facts');
    var el = document.getElementById(pfx+'status');
    var text = ta ? ta.value : '';
    A.put('/api/settings/family_facts', {value:text}, function() {
        if (el) { el.textContent = '✓ Сохранено'; el.className = 'c-ok'; }
    }, function() {
        if (el) { el.textContent = 'Ошибка'; el.className = 'c-err'; }
    });
    setTimeout(function() { if (el) el.textContent = ''; }, 3000);
}

function fillTopPersonas(cid) {
    var pfx = 'fm_'+cid+'_';
    var ta = document.getElementById(pfx+'facts');
    var el = document.getElementById(pfx+'status');
    A.ajax('/api/settings/family_facts/top_personas', function(d) {
        var existing = ta ? ta.value.trim() : '';
        var add = d.text||'';
        if (ta) {
            if (existing) ta.value = existing + '\n\n' + add;
            else ta.value = add;
        }
        if (el) { el.textContent = '✓ Добавлено'; el.className = 'c-info'; }
        setTimeout(function() { if (el) el.textContent = ''; }, 2000);
    }, function() {
        if (el) { el.textContent = 'Ошибка'; el.className = 'c-err'; }
    });
}

A.on('navigate', function(page) {
    if (page==='config') buildConfig();
    if (page==='models') buildModels();
    if (page==='prompts') buildPrompts();
    if (page==='family') buildFamily();
});

})(window.Admin);
